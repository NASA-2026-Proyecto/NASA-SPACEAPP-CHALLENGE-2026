"""Escena "fires-latest": la visualización diaria del EIC "Active Fires As Observed by VIIRS".

https://svs.gsfc.nasa.gov/5113/ publica un fotograma por día (cada uno resume una ventana
móvil de 5 días de detecciones de VIIRS), coloreado por potencia radiativa del fuego
(FRP). Se usa la versión equirrectangular sin rótulos ("SoaS"), en formato EXR. Aquí se
toman los últimos fotogramas con datos y se convierten de color a megavatios.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import numpy as np
import numpy.typing as npt

from app.schemas import Scale
from app.services.colour_scale import FloatArray, max_pool
from app.services.exr import read_rgb
from app.services.scenes import (
    Scene,
    build_manifest,
    encode_species,
    time_axis,
    version_of,
    whole_globe_grid,
)
from app.services.svs import Page, SvsClient

PAGE_ID = 5113
SCALE_MAX_MW = 8.0

# Barra de color de la visualización, leída de su leyenda (fotograma del 13-11-2026):
# rojo lineal del EXR -> FRP en MW. El rojo crece a lo largo de toda la barra, así que
# basta ese canal para invertirla.
RAMP_RED = (0.323, 0.376, 0.446, 0.517, 0.590, 0.646, 0.701, 0.768, 0.846, 0.947)
RAMP_MW = (0.42, 1.26, 2.11, 2.95, 3.79, 4.63, 5.47, 6.32, 7.16, 8.0)
# Los mismos puntos tal como se ven en pantalla, para que el front pinte con ellos
RAMP_DISPLAY = (
    "#9a2d00",
    "#a55922",
    "#b27a2e",
    "#bf963b",
    "#caaa44",
    "#d2b94a",
    "#dac64e",
    "#e3d43f",
    "#ede46a",
    "#f9f6dd",
)
# El fondo (océano, tierra, costas) no pasa de 0,02 de rojo; un fuego, aun suavizado, sí
FIRE_MIN_RED = 0.2

# Los fotogramas más recientes llegan vacíos o a medias (la ventana de 5 días aún no
# tiene datos): se piden algunos de más y se descartan del final los que tengan menos
# de TAPER veces los píxeles de fuego habituales.
EXTRA_FRAMES = 5
TAPER = 0.6
DAY = timedelta(days=1)


@dataclass(frozen=True)
class FireFrames:
    """Lo que hace falta para construir la escena: fotogramas y fecha del render."""

    page: Page
    urls: list[str]
    rendered: datetime  # cuándo generó la NASA los fotogramas (UTC)


def frp_from_rgb(rgb: npt.NDArray[np.float32]) -> FloatArray:
    """FRP en MW por píxel a partir del color lineal; 0 donde no hay fuego."""
    red = rgb[..., 0]
    power = np.interp(red, RAMP_RED, RAMP_MW).astype(np.float32)
    return np.where(red > FIRE_MIN_RED, power, np.float32(0.0))


def frames_with_data(fire_pixels: list[int], steps: int) -> range:
    """Índices de los fotogramas que se usan: los `steps` últimos antes de la cola vacía.

    Args:
        fire_pixels: Píxeles con fuego de cada fotograma candidato, del más antiguo al
            más reciente.
        steps: Cuántos fotogramas se quieren como máximo.

    Returns:
        Un rango de índices consecutivos; vacío si ningún fotograma tiene incendios.
    """
    # Lo habitual se mide solo entre los fotogramas con algún incendio: si se contaran los
    # vacíos, con pocos candidatos la mediana sería cero y no se usaría ninguno
    with_fires = [count for count in fire_pixels if count > 0]
    if not with_fires:
        return range(0)
    usual = float(np.median(with_fires))
    last = len(fire_pixels)
    while last > 0 and fire_pixels[last - 1] < TAPER * usual:
        last -= 1
    return range(max(0, last - steps), last)


class FireSource:
    """Fuente de la escena de incendios leída de la visualización diaria del EIC."""

    scene_id = "fires-latest"

    def __init__(self, client: SvsClient, steps: int = 8, factor: int = 8) -> None:
        """Prepara la fuente.

        Args:
            client: Cliente de SVS.
            steps: Cuántos fotogramas diarios lleva la escena, acabando en el último con datos.
            factor: Lado del bloque de píxeles que se resume con su máximo. Con 8, los
                4096 x 2048 píxeles quedan en una malla de 512 x 256 (~0,7°).
        """
        self._client = client
        self._steps = steps
        self._factor = factor

    def check(self) -> tuple[str, FireFrames]:
        """Versión = fecha de modificación del último fotograma; contexto = los fotogramas.

        La fecha de la página no cambia con cada render diario; la del archivo, sí.

        Raises:
            LookupError: Si la página no lista fotogramas.
        """
        page = self._client.page(PAGE_ID)
        urls = self._client.frame_urls(page.find("Frames", "SoaS"))
        if not urls:
            raise LookupError("La página de incendios no lista fotogramas.")
        rendered = self._client.last_modified(urls[-1])
        return version_of(rendered), FireFrames(page, urls, rendered)

    def build(self, version: str, frames: FireFrames) -> Scene:
        """Descarga los últimos fotogramas, descarta los vacíos y monta la escena.

        Raises:
            ValueError: Si un fotograma no es un mapa 2:1 o ninguno tiene incendios.
        """
        candidates = frames.urls[-(self._steps + EXTRA_FRAMES) :]
        grids: list[FloatArray] = []
        fire_pixels: list[int] = []
        for url in candidates:
            power = frp_from_rgb(read_rgb(self._client.download(url)))
            if power.shape[1] != 2 * power.shape[0]:
                raise ValueError(f"El fotograma mide {power.shape}: no es un mapa 2:1.")
            fire_pixels.append(int((power > 0).sum()))
            grids.append(max_pool(power, self._factor)[::-1])  # de sur a norte

        used = frames_with_data(fire_pixels, self._steps)
        if not used:
            raise ValueError("Ningún fotograma reciente tiene incendios.")
        values = np.stack([grids[index] for index in used])
        _, n_lat, n_lon = values.shape

        # El último fotograma publicado lleva la fecha del día anterior al render, y hay
        # uno por día (comprobado en los rótulos de la versión con fecha)
        rendered = frames.rendered
        newest_day = datetime(rendered.year, rendered.month, rendered.day, tzinfo=UTC) - DAY

        data, entry = encode_species(
            version,
            "frp",
            values,
            source_variable="frame colour",
            long_name="fire radiative power of VIIRS active fire detections (5-day moving window)",
            unit="MW",
            scale=Scale(kind="linear", min=0.0, max=SCALE_MAX_MW, ramp=list(RAMP_DISPLAY)),
            display_scale_max=SCALE_MAX_MW,
            display_scale_method="ends of NASA's colour bar",
        )
        manifest = build_manifest(
            scene_id=self.scene_id,
            version=version,
            layer="fires",
            provenance={
                "provider": "NASA Scientific Visualization Studio",
                "product": f"EIC daily visualization: {frames.page.title} (VIIRS)",
                "source_page": frames.page.url,
                "source_frames": [candidates[index] for index in used],
                "skipped_newest_frames": len(candidates) - used.stop,
                "decoding": "red channel mapped to FRP with the visualization's colour bar; "
                f"each cell keeps the strongest fire of its {self._factor}x{self._factor} pixel block",
                "data_kind": "values read back from a published image, not the satellite product",
            },
            time=time_axis(
                [newest_day - DAY * (len(candidates) - 1 - index) for index in used],
                step_minutes=24 * 60,
                note="One frame per day; each shows a 5-day moving window. Dates are inferred "
                "from the render date (newest published frame = the day before). The newest "
                "frames are skipped while they are still empty.",
            ),
            grid=whole_globe_grid(n_lat, n_lon),
            species={"frp": entry},
        )
        return Scene(version=version, manifest=manifest, files={"frp.f32": data})
