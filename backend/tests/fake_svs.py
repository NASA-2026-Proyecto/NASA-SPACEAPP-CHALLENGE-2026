"""Una página de SVS de mentira, con un fotograma y una barra de color sintéticos."""

import json
from io import BytesIO

import numpy as np
from PIL import Image

from app.services.svs import SvsClient

BASE = "http://svs.gsfc.nasa.gov/vis/a000000/a005100/a005151"  # la API real devuelve http://
WIDTH, HEIGHT = 64, 32
LOGO = (slice(0, 8), slice(0, 12))  # filas, columnas: esquina superior izquierda
COAST_COLUMN = 40

# Rampa de 256 colores, de claro a oscuro
_T = np.linspace(0.0, 1.0, 256)[:, None]
RAMP = np.round((1 - _T) * np.array([255, 245, 215]) + _T * np.array([110, 25, 5])).astype("uint8")


def true_position() -> np.ndarray:
    """Posición 0..1 en la barra que "pinta" el fotograma: crece hacia el este y hacia el sur."""
    cols = np.linspace(0.0, 1.0, WIDTH)[None, :]
    rows = np.linspace(0.0, 1.0, HEIGHT)[:, None]
    return 0.7 * cols + 0.3 * rows


def _png(array: np.ndarray, mode: str) -> bytes:
    buffer = BytesIO()
    Image.fromarray(array, mode).save(buffer, format="PNG")
    return buffer.getvalue()


FRAME_DRIFT = 0.02  # cada fotograma sube esto en la escala respecto al anterior


def frame_png(number: int = 3) -> bytes:
    """Fotograma `number` (1 = el más antiguo). El 3 es exactamente `true_position()`."""
    position = np.clip(true_position() + FRAME_DRIFT * (number - 3), 0.0, 1.0)
    pixels = RAMP[np.round(position * 255).astype(int)]
    pixels[LOGO] = (90, 90, 90)  # logotipo: un gris que no está en la rampa
    pixels[:, COAST_COLUMN] = (0, 0, 0)  # una "costa" de un píxel
    return _png(pixels, "RGB")


def colour_bar_png() -> bytes:
    bar = np.zeros((20, 300, 4), dtype="uint8")  # fondo transparente
    bar[5:15, 20:278, :3] = (0, 0, 0)  # borde negro...
    bar[5:15, 21:277, :3] = RAMP[None, :, :]  # ...alrededor de la rampa
    bar[5:15, 20:278, 3] = 255
    return _png(bar, "RGBA")


class FakeSvs:
    def __init__(self, updated: str = "2026-11-14T02:00:58.490675-05:00", frames: int = 3) -> None:
        self.updated = updated
        self.frames = frames
        self.fail = False
        self.broken_frame: bytes | None = None  # si se pone, sustituye a todos los fotogramas
        self.requests: list[str] = []

    def get(self, url: str) -> bytes:
        self.requests.append(url)
        if self.fail:
            raise TimeoutError("SVS no responde")
        if url.endswith("/api/5151"):
            return json.dumps(self._page()).encode()
        if url.endswith("/frames/"):
            # Desordenado a propósito: el más reciente es el de número más alto
            numbers = [*range(2, self.frames + 1), 1]
            return " ".join(f'<a href="{n:08d}.png">{n}</a>' for n in numbers).encode()
        if "/frames/" in url and url.endswith(".png"):
            number = int(url.rsplit("/", 1)[1].removesuffix(".png"))
            return self.broken_frame or frame_png(number)
        if url.endswith("PM2.5_colorbar_plain.png"):
            return colour_bar_png()
        raise AssertionError(f"petición inesperada: {url}")

    def _page(self) -> dict:
        def item(kind: str, name: str) -> dict:
            return {"instance": {"media_type": kind, "url": f"{BASE}/{name}"}}

        return {
            "id": 5151,
            "title": "Particulate Matter (PM) 2.5",
            "release_date": "2023-09-26T17:00:00-04:00",
            "update_date": self.updated,
            "media_groups": [
                {"items": [item("Image", "preview.jpg"), item("Frames", "frames/")]},
                {"items": [item("Image", "PM2.5_colorbar.png")]},
                {"items": [item("Image", "PM2.5_colorbar_plain.png")]},
            ],
        }

    def client(self) -> SvsClient:
        return SvsClient(get=self.get)
