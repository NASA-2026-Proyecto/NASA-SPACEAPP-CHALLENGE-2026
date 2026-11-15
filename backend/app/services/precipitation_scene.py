"""Escena "precipitation-latest": la visualización del EIC de precipitación casi en tiempo real.

https://svs.gsfc.nasa.gov/4285/ publica un fotograma cada media hora con la precipitación
de IMERG (la constelación de satélites GPM). Se usa la versión "flatalpha": un mapa
equirrectangular con fondo transparente y sin rótulos, cuyo nombre de archivo lleva la
hora exacta (UTC). La lluvia y la nieve tienen cada una su barra de color, por tramos:
cada color es un intervalo de intensidad, así que se leen por coincidencia exacta.
"""

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from io import BytesIO

import numpy as np
import numpy.typing as npt
from PIL import Image

from app.schemas import Scale, SpeciesEntry
from app.services.colour_scale import FloatArray, Ramp, classes_from_colour_bar, downsample
from app.services.scenes import (
    Scene,
    build_manifest,
    encode_species,
    stamp,
    time_axis,
    version_of,
    whole_globe_grid,
)
from app.services.svs import Page, SvsClient

PAGE_ID = 4285
FRAME_MINUTES = 30  # la página publica un fotograma cada media hora
# Marcas de las dos barras de color, en mm/h: cada tramo va de una marca a la siguiente.
# Están rotuladas en la imagen de la barra, así que aquí son constantes.
EDGES = (0.1, 0.2, 0.3, 0.5, 1.0, 2.0, 3.0, 5.0, 10.0, 20.0, 50.0)
RAMP_STOPS = 33

_FRAME_TIME = re.compile(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})Z\.png$")


@dataclass(frozen=True)
class Phase:
    """Una fase de la precipitación: es una especie de la escena y tiene su barra de color."""

    key: str
    colour_bar: str  # texto que identifica su barra entre las imágenes de la página
    long_name: str


PHASES = (
    Phase("rain", "rainbarblack", "liquid precipitation rate"),
    Phase("snow", "snowbarblack", "frozen precipitation rate"),
)


@dataclass(frozen=True)
class PrecipitationFrames:
    """Lo que hace falta para construir la escena: la página y sus fotogramas por hora."""

    page: Page
    urls: dict[datetime, str]

    @property
    def newest(self) -> datetime:
        """Hora del fotograma más reciente."""
        return max(self.urls)


@dataclass(frozen=True)
class ClassTable:
    """Los colores de todas las clases, para buscar el de cada píxel."""

    colours: npt.NDArray[np.int64]  # color empaquetado (r, g, b), en orden creciente
    rates: FloatArray  # mm/h de cada color
    phases: npt.NDArray[np.int8]  # posición en PHASES de cada color


def _pack(rgb: npt.NDArray[np.uint8]) -> npt.NDArray[np.int64]:
    """Empaqueta colores (..., 3) en un entero por color."""
    wide = rgb.astype(np.int64)
    packed: npt.NDArray[np.int64] = (wide[..., 0] << 16) | (wide[..., 1] << 8) | wide[..., 2]
    return packed


def class_colours(colour_bar: Image.Image) -> Ramp:
    """Colores de las clases de una barra, de menor a mayor intensidad.

    La barra tiene una flecha gris ("menos de 0,1", que en los fotogramas es transparente),
    un tramo por intervalo y, si tiene color propio, la flecha de "más de 50".

    Raises:
        ValueError: Si la barra no tiene los tramos que corresponden a las marcas.
    """
    colours = classes_from_colour_bar(colour_bar)[1:]
    intervals = len(EDGES) - 1
    if len(colours) not in (intervals, intervals + 1):
        raise ValueError(f"La barra de color tiene {len(colours)} clases y se esperaban {intervals}.")
    return colours


def class_rates(classes: int) -> FloatArray:
    """Intensidad (mm/h) que representa cada clase: el punto medio geométrico de su tramo.

    La clase de más, si la hay, es "por encima de la última marca" y vale esa marca.
    """
    edges = np.array(EDGES)
    rates = [*np.sqrt(edges[:-1] * edges[1:]), edges[-1]]
    return np.array(rates[:classes], dtype=np.float32)


def class_table(bars: list[Ramp]) -> ClassTable:
    """Reúne las clases de todas las fases en una tabla de búsqueda.

    Args:
        bars: Colores de las clases de cada fase, en el orden de `PHASES`.

    Raises:
        ValueError: Si dos clases comparten color: no se podrían distinguir.
    """
    colours = np.concatenate([_pack(bar) for bar in bars])
    rates = np.concatenate([class_rates(len(bar)) for bar in bars])
    phases = np.concatenate([np.full(len(bar), index, dtype=np.int8) for index, bar in enumerate(bars)])
    if len(np.unique(colours)) != len(colours):
        raise ValueError("Dos clases de las barras de color comparten color.")
    order = np.argsort(colours)
    return ClassTable(colours[order], rates[order], phases[order])


def ramp_stops(colours: Ramp) -> list[str]:
    """Paradas de la rampa para el front, repartidas por igual en la escala logarítmica.

    Las marcas no están a distancias iguales, así que cada parada lleva el color de la
    clase a la que pertenece su valor.
    """
    values = EDGES[0] * (EDGES[-1] / EDGES[0]) ** np.linspace(0.0, 1.0, RAMP_STOPS)
    classes = np.clip(np.searchsorted(EDGES, values, side="right") - 1, 0, len(colours) - 1)
    return [f"#{r:02x}{g:02x}{b:02x}" for r, g, b in colours[classes].tolist()]


def decode_frame(frame_bytes: bytes, table: ClassTable, factor: int) -> list[FloatArray]:
    """Convierte un fotograma en una malla de mm/h por fase, de sur a norte.

    Cada celda es la media de su bloque de píxeles; donde no hay precipitación vale 0.

    Raises:
        ValueError: Si el fotograma no es un mapa 2:1, no es divisible por `factor` o
            tiene un color que no es de ninguna clase.
    """
    rgba = np.asarray(Image.open(BytesIO(frame_bytes)).convert("RGBA"))
    height, width = rgba.shape[:2]
    if width != 2 * height:
        raise ValueError(f"El fotograma mide {width} x {height}: no es un mapa equirrectangular 2:1.")

    drawn = rgba[..., 3] > 0  # el fondo es transparente
    colours = _pack(rgba[drawn][:, :3])
    found = np.minimum(np.searchsorted(table.colours, colours), len(table.colours) - 1)
    unknown = table.colours[found] != colours
    if unknown.any():
        raise ValueError(
            f"El fotograma tiene {int(unknown.sum())} píxeles de un color que no es de la barra."
        )

    grids = []
    for index in range(len(PHASES)):
        rate = np.zeros((height, width), dtype=np.float32)
        rate[drawn] = np.where(table.phases[found] == index, table.rates[found], np.float32(0.0))
        grids.append(downsample(rate, factor)[::-1])
    return grids


class PrecipitationSource:
    """Fuente de la escena de precipitación leída de la visualización del EIC."""

    scene_id = "precipitation-latest"

    def __init__(self, client: SvsClient, steps: int = 8, frame_spacing: int = 6, factor: int = 5) -> None:
        """Prepara la fuente.

        Args:
            client: Cliente de SVS.
            steps: Cuántos fotogramas lleva la escena, acabando en el más reciente.
            frame_spacing: Se toma un fotograma de cada tantos (son de media hora: 6 = cada 3 h).
            factor: Lado del bloque de píxeles que se promedia. Con 5, los 3600 x 1800
                píxeles quedan en una malla de 720 x 360 (0,5°), para que la serie pese poco.
        """
        self._client = client
        self._steps = steps
        self._step = timedelta(minutes=FRAME_MINUTES * frame_spacing)
        self._factor = factor

    def check(self) -> tuple[str, PrecipitationFrames]:
        """Versión = hora del fotograma más reciente; contexto = los fotogramas.

        Raises:
            LookupError: Si la página no lista fotogramas con la hora en el nombre.
        """
        page = self._client.page(PAGE_ID)
        urls = {}
        for url in self._client.frame_urls(page.find("Frames", "flatalpha")):
            if match := _FRAME_TIME.search(url):
                urls[datetime.fromisoformat(match[1]).replace(tzinfo=UTC)] = url
        if not urls:
            raise LookupError("La página de precipitación no lista fotogramas con su hora.")
        frames = PrecipitationFrames(page, urls)
        return version_of(frames.newest), frames

    def build(self, version: str, frames: PrecipitationFrames) -> Scene:
        """Descarga las barras de color y los fotogramas y monta la escena.

        Raises:
            ValueError: Si falta un fotograma de la serie o alguno no se puede leer.
        """
        moments = [frames.newest - self._step * back for back in reversed(range(self._steps))]
        missing = [stamp(moment) for moment in moments if moment not in frames.urls]
        if missing:
            raise ValueError(f"La página no tiene los fotogramas de {', '.join(missing)}.")
        frame_urls = [frames.urls[moment] for moment in moments]

        bar_urls = [frames.page.find("Image", phase.colour_bar).url for phase in PHASES]
        bars = [class_colours(Image.open(BytesIO(self._client.download(url)))) for url in bar_urls]
        table = class_table(bars)

        decoded = [decode_frame(self._client.download(url), table, self._factor) for url in frame_urls]
        files: dict[str, bytes] = {}
        species: dict[str, SpeciesEntry] = {}
        for index, (phase, bar) in enumerate(zip(PHASES, bars, strict=True)):
            values = np.stack([grids[index] for grids in decoded])
            data, species[phase.key] = encode_species(
                version,
                phase.key,
                values,
                source_variable="frame colour",
                long_name=phase.long_name,
                unit="mm/h",
                scale=Scale(kind="log", min=EDGES[0], max=EDGES[-1], ramp=ramp_stops(bar)),
                display_scale_max=EDGES[-1],
                display_scale_method="ends of NASA's colour bar",
            )
            files[f"{phase.key}.f32"] = data
        n_lat, n_lon = decoded[0][0].shape

        manifest = build_manifest(
            scene_id=self.scene_id,
            version=version,
            layer="precipitation",
            provenance={
                "provider": "NASA Scientific Visualization Studio / GPM",
                "product": f"EIC visualization: {frames.page.title} (IMERG)",
                "source_page": frames.page.url,
                "source_frames": frame_urls,
                "colour_bars": bar_urls,
                "decoding": "exact match of each pixel's colour with the classes of the page's colour "
                "bars; each class counts as the geometric midpoint of its interval and the class "
                f"above the last mark as that mark; {self._factor}x{self._factor} pixel blocks averaged",
                "class_edges_mm_per_hour": ", ".join(str(edge) for edge in EDGES),
                "data_kind": "values read back from a published image, not the satellite product",
            },
            time=time_axis(
                moments,
                step_minutes=int(self._step.total_seconds() // 60),
                note="Stamps are the times in the frame file names (UTC), half-hourly at the source.",
            ),
            grid=whole_globe_grid(n_lat, n_lon),
            species=species,
        )
        return Scene(version=version, manifest=manifest, files=files)
