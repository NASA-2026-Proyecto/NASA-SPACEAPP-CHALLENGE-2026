"""Escena "pm25-latest": la visualización diaria del EIC "Particulate Matter (PM) 2.5".

La NASA vuelve a generar cada día los fotogramas de https://svs.gsfc.nasa.gov/5151/
(modelo GEOS-CF, un mapa equirrectangular por hora). Aquí se toma el más reciente y se
convierte de colores a valores con la barra de color de la propia página, para que el
front lo dibuje y lo sonifique como cualquier otra escena.
"""

from datetime import UTC, datetime
from io import BytesIO

import numpy as np
from PIL import Image

from app.services.colour_scale import (
    downsample,
    drop_islands,
    fill_small_gaps,
    gradient_from_colour_bar,
    invert_gradient,
    reject_thin_features,
)
from app.services.scenes import Scene, grid_block, species_entry, stamp, version_of
from app.services.svs import Page, SvsClient

PAGE_ID = 5151
# Extremos de la barra de color, en µg/m³. La escala es logarítmica (cada marca es x4).
SCALE_MIN, SCALE_MAX = 0.4, 409.6
FACTOR = 2  # de 2048 x 1024 píxeles a una malla de 1024 x 512 (~0,35°)
RAMP_STOPS = 17
MIN_READABLE = 0.5  # si se lee menos de la mitad del mapa, algo ha cambiado en origen


class Pm25Source:
    scene_id = "pm25-latest"

    def __init__(self, client: SvsClient) -> None:
        self._client = client

    def check(self) -> tuple[str, Page]:
        page = self._client.page(PAGE_ID)
        return version_of(page.updated), page

    def build(self, version: str, page: Page) -> Scene:
        frame_url = self._client.frame_urls(page.find("Frames"))[-1]
        bar_url = page.find("Image", "colorbar_plain").url
        frame = Image.open(BytesIO(self._client.download(frame_url)))
        bar = Image.open(BytesIO(self._client.download(bar_url)))
        if frame.width != 2 * frame.height:
            raise ValueError(f"El fotograma mide {frame.size}: no es un mapa equirrectangular 2:1.")

        # Posición 0..1 en la barra de color; la fila 0 de la imagen es el norte
        gradient = gradient_from_colour_bar(bar)
        # Paradas de la rampa, para que el front pinte con los colores de la propia NASA
        stops = gradient[np.linspace(0, len(gradient) - 1, RAMP_STOPS).round().astype(int)]
        ramp = [f"#{r:02x}{g:02x}{b:02x}" for r, g, b in stops.tolist()]
        position = reject_thin_features(invert_gradient(frame, gradient))
        readable = float(np.isfinite(position).mean())
        if readable < MIN_READABLE:
            raise ValueError(f"Solo se pudo leer el {readable:.0%} del fotograma.")

        # Se promedia en la escala de la barra (logarítmica) y después se pasa a µg/m³
        position = fill_small_gaps(drop_islands(downsample(position, FACTOR)))[::-1]  # de sur a norte
        values = (SCALE_MIN * (SCALE_MAX / SCALE_MIN) ** position).astype("float32")
        n_lat, n_lon = values.shape
        lat_step, lon_step = 180.0 / n_lat, 360.0 / n_lon

        data, entry = species_entry(
            version,
            "pm25",
            values[None, :, :],
            source_variable="frame colour",
            long_name="near-surface PM2.5 concentration",
            unit="ug/m3",
            missing="NaN where the frame shows a logo or caption instead of data",
            scale={"kind": "log", "min": SCALE_MIN, "max": SCALE_MAX, "ramp": ramp},
            display_scale_max=SCALE_MAX,
            display_scale_method="ends of NASA's colour bar",
        )
        manifest = {
            "schema_version": 2,
            "scene_id": self.scene_id,
            "version": version,
            "generated_utc": stamp(datetime.now(UTC)),
            "layer": "aerosols",
            "kind": "grid-series",
            "provenance": {
                "provider": "NASA Scientific Visualization Studio / GMAO",
                "product": f"EIC daily visualization: {page.title} (GEOS-CF model)",
                "source_page": page.url,
                "source_frame": frame_url,
                "colour_bar": bar_url,
                "decoding": "nearest colour on the page's colour bar; bright features thinner than "
                "3 pixels (coastlines, borders) removed and filled from their neighbours; "
                f"{FACTOR}x{FACTOR} pixel blocks averaged on the log scale",
                "readable_fraction": round(readable, 4),
                "data_kind": "values read back from a published image, not the model output",
            },
            "time": {
                "steps": 1,
                "step_minutes": 60,
                "stamps_utc": [stamp(page.updated)],
                "note": "Publication time of the daily render. The frame's own hour is printed "
                "on the image (US Eastern time) and is typically several hours earlier.",
            },
            # Centros de celda: la imagen cubre de -180 a 180 y de -90 a 90
            "grid": grid_block(-90.0 + lat_step / 2, lat_step, -180.0 + lon_step / 2, lon_step, values.shape),
            "species": {"pm25": entry},
        }
        return Scene(version=version, manifest=manifest, files={"pm25.f32": data})
