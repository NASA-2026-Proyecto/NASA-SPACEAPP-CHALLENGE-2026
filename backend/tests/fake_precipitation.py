"""La página de precipitación de SVS de mentira, con fotogramas y barras sintéticos."""

import json
from datetime import UTC, datetime, timedelta
from io import BytesIO

import numpy as np
from PIL import Image

from app.services.svs import SvsClient

BASE = "http://svs.gsfc.nasa.gov/vis/a000000/a004200/a004285"
FRAMES_PATH = "/vis/a000000/a004200/a004285/frames/3600x1800_2x1_30p/flatalpha/"
WIDTH, HEIGHT = 40, 20
FIRST_FRAME = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)
HALF_HOUR = timedelta(minutes=30)

# Los colores reales de las dos barras (leídos el 15-11-2026); el último de la lluvia es
# el de la flecha "más de 50", que la nieve no tiene (repite el de su último tramo)
RAIN = [
    (0, 129, 20),
    (0, 139, 82),
    (0, 179, 48),
    (96, 211, 0),
    (180, 231, 0),
    (255, 251, 0),
    (255, 196, 0),
    (255, 147, 0),
    (255, 0, 0),
    (200, 0, 0),
    (145, 0, 0),
]
SNOW = [
    (69, 255, 255),
    (73, 221, 255),
    (77, 187, 255),
    (79, 154, 255),
    (81, 122, 255),
    (82, 93, 255),
    (83, 70, 255),
    (90, 47, 217),
    (115, 33, 187),
    (140, 20, 156),
]
UNDER = (58, 61, 72)  # flecha gris de "menos de 0,1"

# Qué pinta cada fotograma (filas y columnas de la imagen, con la fila 0 en el norte)
STORM = (slice(12, 14), slice(4, 6))  # un bloque entero cuya clase sube con el tiempo
DRIZZLE = (2, 30)  # un solo píxel de lluvia de la clase 4 (1-2 mm/h)
SNOWFALL = (slice(0, 2), slice(20, 22))  # un bloque entero de nieve de la clase 0


def png(array: np.ndarray) -> bytes:
    buffer = BytesIO()
    Image.fromarray(array, "RGBA").save(buffer, format="PNG")
    return buffer.getvalue()


def bar_png(colours: list[tuple[int, int, int]], blocks: int = 10) -> bytes:
    """Barra por tramos como las reales: flecha gris, `blocks` tramos y flecha alta."""
    runs = [((0, 0, 0), 3), ((255, 255, 255), 1), (UNDER, 14), ((0, 0, 0), 3)]
    runs += [(colour, 12) for colour in colours[:blocks]]
    runs += [((0, 0, 0), 3), (colours[-1], 14), ((0, 0, 0), 3)]
    row = np.array([(*colour, 255) for colour, width in runs for _ in range(width)], dtype="uint8")
    bar = np.zeros((20, len(row) + 10, 4), dtype="uint8")  # fondo transparente
    bar[5:15, 5:-5] = row
    return png(bar)


def storm_class(index: int) -> int:
    """Clase de lluvia de la tormenta en el fotograma `index` (0 = el más antiguo)."""
    return min(index // 2, len(RAIN) - 1)


def frame_png(index: int) -> bytes:
    frame = np.zeros((HEIGHT, WIDTH, 4), dtype="uint8")
    frame[STORM] = (*RAIN[storm_class(index)], 255)
    frame[DRIZZLE] = (*RAIN[4], 255)
    frame[SNOWFALL] = (*SNOW[0], 255)
    return png(frame)


class FakePrecipitationSvs:
    """`frames` fotogramas de media hora a partir de `FIRST_FRAME`."""

    def __init__(self, frames: int = 20) -> None:
        self.frames = frames
        self.missing: set[int] = set()  # fotogramas que el listado no trae
        self.fail = False
        self.requests: list[str] = []

    def time_of(self, index: int) -> datetime:
        return FIRST_FRAME + HALF_HOUR * index

    def get(self, url: str) -> bytes:
        self.requests.append(url)
        if self.fail:
            raise TimeoutError("SVS no responde")
        if url.endswith("/api/4285"):
            return json.dumps(self._page()).encode()
        if url.endswith("/flatalpha/"):
            return self._listing().encode()
        if "/flatalpha/" in url:
            moment = datetime.fromisoformat(url.rsplit("imergert_alpha.", 1)[1].removesuffix(".png"))
            return frame_png((moment - FIRST_FRAME) // HALF_HOUR)
        if url.endswith("rainbarblack2.png"):
            return bar_png(RAIN)
        if url.endswith("snowbarblack2.png"):
            return bar_png(SNOW)
        raise AssertionError(f"petición inesperada: {url}")

    def _listing(self) -> str:
        # Como el real: rutas absolutas, una subcarpeta y, aquí, un archivo sin hora
        indices = [index for index in range(self.frames) if index not in self.missing]
        names = [f"imergert_alpha.{self.time_of(index):%Y-%m-%dT%H:%M:%S}Z.png" for index in indices[::-1]]
        links = [f'<a href="{FRAMES_PATH}{name}">{name}</a>' for name in ["legend.png", *names]]
        return f'<a href="{FRAMES_PATH}hurricane2022">hurricane2022</a>' + " ".join(links)

    def _page(self) -> dict:
        def item(kind: str, name: str) -> dict:
            return {"instance": {"media_type": kind, "url": f"{BASE}/{name}"}}

        return {
            "id": 4285,
            "title": "Near Real-Time Global Precipitation from the GPM Constellation",
            "release_date": "2015-03-31T12:00:00-04:00",
            "update_date": "2026-11-14T21:50:49.906332-05:00",
            "media_groups": [
                {
                    "items": [
                        item("Frames", "frames/1920x1080_16x9_30p/flatcomposite/"),
                        item("Frames", "frames/3600x1800_2x1_30p/flatalpha/"),
                        item("Frames", "frames/3600x1800_2x1_30p/flatcomposite/"),
                    ]
                },
                {"items": [item("Image", "snowbarwhite2.png"), item("Image", "snowbarblack2.png")]},
                {"items": [item("Image", "rainbarwhite2.png"), item("Image", "rainbarblack2.png")]},
            ],
        }

    def client(self) -> SvsClient:
        return SvsClient(get=self.get)
