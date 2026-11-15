"""Escena "pm25-latest": la visualización diaria del EIC "Particulate Matter (PM) 2.5".

La NASA vuelve a generar cada día los fotogramas de https://svs.gsfc.nasa.gov/5151/
(modelo GEOS-CF, un mapa equirrectangular por hora). Aquí se toman los más recientes,
espaciados unas horas, y se convierten de colores a valores con la barra de color de la
propia página, para que el front los dibuje (en secuencia) y los sonifique como
cualquier otra escena.
"""

from datetime import timedelta
from io import BytesIO

import numpy as np
from PIL import Image

from app.schemas import Scale
from app.services.colour_scale import (
    FloatArray,
    Ramp,
    downsample,
    drop_islands,
    fill_small_gaps,
    gradient_from_colour_bar,
    invert_gradient,
    reject_thin_features,
)
from app.services.scenes import (
    Scene,
    build_manifest,
    encode_species,
    time_axis,
    version_of,
    whole_globe_grid,
)
from app.services.svs import Page, SvsClient

PAGE_ID = 5151
# Extremos de la barra de color, en µg/m³. La escala es logarítmica (cada marca es x4).
SCALE_MIN, SCALE_MAX = 0.4, 409.6
RAMP_STOPS = 17
MIN_READABLE = 0.5  # si se lee menos de la mitad del mapa, algo ha cambiado en origen
FRAME_MINUTES = 60  # la página publica un fotograma por hora


class Pm25Source:
    """Fuente de la escena de PM2.5 leída de la visualización diaria del EIC."""

    scene_id = "pm25-latest"

    def __init__(self, client: SvsClient, steps: int = 8, frame_spacing: int = 3, factor: int = 4) -> None:
        """Prepara la fuente.

        Args:
            client: Cliente de SVS.
            steps: Cuántos fotogramas lleva la escena, acabando en el más reciente.
            frame_spacing: Se toma un fotograma de cada tantos (son horarios: 3 = cada 3 h).
            factor: Lado del bloque de píxeles que se promedia. Con 4, los 2048 x 1024
                píxeles quedan en una malla de 512 x 256 (~0,7°), para que la serie pese poco.
        """
        self._client = client
        self._steps = steps
        self._spacing = frame_spacing
        self._factor = factor

    def check(self) -> tuple[str, Page]:
        """Versión = fecha en que la NASA regeneró la página; contexto = la página."""
        page = self._client.page(PAGE_ID)
        return version_of(page.updated), page

    def _decode(self, frame_bytes: bytes, gradient: Ramp) -> tuple[FloatArray, float]:
        """Convierte un fotograma en valores.

        Returns:
            Los µg/m³ en una malla de sur a norte y la fracción del mapa que se pudo leer.

        Raises:
            ValueError: Si el fotograma no es un mapa 2:1 o apenas se puede leer.
        """
        frame = Image.open(BytesIO(frame_bytes))
        if frame.width != 2 * frame.height:
            raise ValueError(f"El fotograma mide {frame.size}: no es un mapa equirrectangular 2:1.")

        # Posición 0..1 en la barra de color; la fila 0 de la imagen es el norte
        position = reject_thin_features(invert_gradient(frame, gradient))
        readable = float(np.isfinite(position).mean())
        if readable < MIN_READABLE:
            raise ValueError(f"Solo se pudo leer el {readable:.0%} del fotograma.")

        # Se promedia en la escala de la barra (logarítmica) y después se pasa a µg/m³
        position = fill_small_gaps(drop_islands(downsample(position, self._factor)))[::-1]
        return (SCALE_MIN * (SCALE_MAX / SCALE_MIN) ** position).astype(np.float32), readable

    def build(self, version: str, page: Page) -> Scene:
        """Descarga los fotogramas y la barra de color y monta la escena."""
        # Del más antiguo al más reciente: el último paso es siempre el último fotograma
        urls = self._client.frame_urls(page.find("Frames"))
        frame_urls = urls[:: -self._spacing][: self._steps][::-1]
        bar_url = page.find("Image", "colorbar_plain").url
        gradient = gradient_from_colour_bar(Image.open(BytesIO(self._client.download(bar_url))))
        # Paradas de la rampa, para que el front pinte con los colores de la propia NASA
        stops = gradient[np.linspace(0, len(gradient) - 1, RAMP_STOPS).round().astype(int)]
        ramp = [f"#{r:02x}{g:02x}{b:02x}" for r, g, b in stops.tolist()]

        decoded = [self._decode(self._client.download(url), gradient) for url in frame_urls]
        values = np.stack([grid for grid, _ in decoded])
        readable = min(fraction for _, fraction in decoded)
        n_steps, n_lat, n_lon = values.shape
        step = timedelta(minutes=FRAME_MINUTES * self._spacing)

        data, entry = encode_species(
            version,
            "pm25",
            values,
            source_variable="frame colour",
            long_name="near-surface PM2.5 concentration",
            unit="ug/m3",
            missing="NaN where the frame shows a logo or caption instead of data",
            scale=Scale(kind="log", min=SCALE_MIN, max=SCALE_MAX, ramp=ramp),
            display_scale_max=SCALE_MAX,
            display_scale_method="ends of NASA's colour bar",
        )
        manifest = build_manifest(
            scene_id=self.scene_id,
            version=version,
            layer="aerosols",
            provenance={
                "provider": "NASA Scientific Visualization Studio / GMAO",
                "product": f"EIC daily visualization: {page.title} (GEOS-CF model)",
                "source_page": page.url,
                "source_frames": frame_urls,
                "colour_bar": bar_url,
                "decoding": "nearest colour on the page's colour bar; bright features thinner than "
                "3 pixels (coastlines, borders) removed and filled from their neighbours; "
                f"{self._factor}x{self._factor} pixel blocks averaged on the log scale",
                "readable_fraction": round(readable, 4),
                "data_kind": "values read back from a published image, not the model output",
            },
            # El intervalo entre pasos es exacto; la hora absoluta, no (ver la nota)
            time=time_axis(
                [page.updated - step * (n_steps - 1 - index) for index in range(n_steps)],
                step_minutes=FRAME_MINUTES * self._spacing,
                note="The last stamp is the publication time of the daily render. Each frame's "
                "own hour is printed on the image (US Eastern time) and is typically several "
                "hours earlier; the spacing between steps is exact.",
            ),
            grid=whole_globe_grid(n_lat, n_lon),
            species={"pm25": entry},
        )
        return Scene(version=version, manifest=manifest, files={"pm25.f32": data})
