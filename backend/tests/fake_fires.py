"""La página de incendios de SVS de mentira, con fotogramas EXR sintéticos."""

import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import OpenEXR

from app.services.svs import SvsClient

BASE = "http://svs.gsfc.nasa.gov/vis/a000000/a005100/a005113"
WIDTH, HEIGHT = 64, 32
OCEAN = (0.016, 0.031, 0.063)  # el fondo real: azul marino muy oscuro

# Incendios fijos: (fila, columna) en la imagen, con la fila 0 en el norte
FIRES = [(4 + 2 * i, 6 + 5 * i) for i in range(10)]
STRONG_FIRE = (20, 50)  # un incendio cuya potencia sube con el número de fotograma


def exr_bytes(rgb: np.ndarray) -> bytes:
    rgba = np.concatenate([rgb, np.ones((*rgb.shape[:2], 1))], axis=-1).astype("float16")
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "frame.exr"
        header = {"compression": OpenEXR.ZIP_COMPRESSION, "type": OpenEXR.scanlineimage}
        with OpenEXR.File(header, {"RGBA": rgba}) as exr:
            exr.write(str(path))
        return path.read_bytes()


def frame_exr(fires: int, strong_red: float = 0.59) -> bytes:
    """Fotograma con `fires` incendios de los fijos (rojo 0,446) y, si hay alguno, el fuerte."""
    rgb = np.empty((HEIGHT, WIDTH, 3), dtype="float32")
    rgb[:] = OCEAN
    for row, col in FIRES[:fires]:
        rgb[row, col] = (0.446, 0.196, 0.027)
    if fires:
        rgb[STRONG_FIRE] = (strong_red, 0.4, 0.06)
    return exr_bytes(rgb)


class FakeFireSvs:
    """`frames` fotogramas diarios; los `empty` últimos vacíos y el anterior, a medias."""

    def __init__(self, frames: int = 14, empty: int = 3, partial: int = 1) -> None:
        self.frames = frames
        self.empty = empty
        self.partial = partial
        self.rendered = datetime(2026, 11, 14, 11, 29, 21, tzinfo=UTC)
        self.fail = False
        self.requests: list[str] = []

    def fires_in(self, number: int) -> int:
        if number > self.frames - self.empty:
            return 0
        if number > self.frames - self.empty - self.partial:
            return 2
        return len(FIRES)

    def get(self, url: str) -> bytes:
        self.requests.append(url)
        if self.fail:
            raise TimeoutError("SVS no responde")
        if url.endswith("/api/5113"):
            return json.dumps(self._page()).encode()
        if url.endswith("/SoaS/"):
            numbers = [*range(2, self.frames + 1), 1]  # desordenado a propósito
            return " ".join(f'<a href="fires_eq_nl.{n:03d}.exr">{n}</a>' for n in numbers).encode()
        if url.endswith(".exr"):
            number = int(url.rsplit(".", 2)[1])
            # el incendio fuerte sube un punto de la barra de color cada dos fotogramas
            return frame_exr(self.fires_in(number), strong_red=0.517 + 0.02 * number)
        raise AssertionError(f"petición inesperada: {url}")

    def last_modified(self, url: str) -> datetime:
        self.requests.append(f"HEAD {url}")
        return self.rendered

    def _page(self) -> dict:
        def item(kind: str, name: str) -> dict:
            return {"instance": {"media_type": kind, "url": f"{BASE}/{name}"}}

        return {
            "id": 5113,
            "title": "Active Fires As Observed by VIIRS, 2024-Present",
            "release_date": "2024-03-01T14:00:00-05:00",
            "update_date": "2026-10-24T19:30:10-04:00",
            "media_groups": [
                {"items": [item("Image", "print.jpg"), item("Frames", "frames/4096x2048_2x1_30p/EIC/")]},
                {"items": [item("Frames", "frames/4096x2048_2x1_30p/SoaS/"), item("Movie", "eq.mp4")]},
            ],
        }

    def client(self) -> SvsClient:
        return SvsClient(get=self.get, last_modified=self.last_modified)
