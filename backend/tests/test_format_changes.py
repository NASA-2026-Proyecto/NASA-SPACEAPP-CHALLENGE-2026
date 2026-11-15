"""Qué pasa si la NASA cambia el formato de lo que publica: debe fallar con un mensaje claro.

Ninguno de estos casos debe publicar una escena con datos mal leídos.
"""

import struct
from io import BytesIO

import numpy as np
import pytest
from PIL import Image

from app.services.colour_scale import gradient_from_colour_bar
from app.services.exr import read_rgb
from app.services.fire_scene import FireSource, frames_with_data
from app.services.geosfp import parse_das, parse_dods
from app.services.http import http_get
from app.services.pm25_scene import Pm25Source
from app.services.scenes import SceneStore
from app.services.svs import Page
from tests.fake_fires import FakeFireSvs, exr_bytes
from tests.fake_svs import RAMP, FakeSvs
from tests.fakes import DAS
from tests.test_http import FakeResponse, server_error


def png(image: Image.Image) -> bytes:
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


# --- GEOS-FP -----------------------------------------------------------------------


def test_das_without_a_time_block_is_rejected():
    das = (DAS % {"n_times": 3}).replace("time {", "tiempo {")
    with pytest.raises(ValueError, match="no tiene el bloque 'time'"):
        parse_das(das)


def test_das_with_an_unknown_time_step_is_rejected():
    das = (DAS % {"n_times": 3}).replace('"180mn"', '"3weeks"')
    with pytest.raises(ValueError, match="Paso de tiempo desconocido"):
        parse_das(das)


@pytest.mark.parametrize("step, minutes", [("90mn", 90), ("6hr", 360), ("1dy", 1440)])
def test_das_time_step_units(step, minutes):
    grid = parse_das((DAS % {"n_times": 3}).replace('"180mn"', f'"{step}"'))
    assert grid.time_step.total_seconds() == minutes * 60


def test_dods_without_a_data_section_is_rejected():
    with pytest.raises(ValueError, match="sin sección de datos"):
        parse_dods(b"Dataset { ... };\n" + struct.pack(">II", 4, 4), (2, 2))


# --- SVS ---------------------------------------------------------------------------


def test_page_without_the_expected_media_is_an_error():
    page = Page(id=5151, title="x", updated=None, media=())
    with pytest.raises(LookupError, match="no tiene Frames"):
        page.find("Frames")


def test_page_date_without_time_zone_is_taken_as_utc():
    from app.services.svs import parse_page

    page = parse_page({"id": 1, "title": "x", "release_date": "2026-11-14T02:00:00"})
    assert page.updated.isoformat() == "2026-11-14T02:00:00+00:00"
    assert page.media == ()


# --- Barra de color y fotogramas de PM2.5 ------------------------------------------


def test_colour_bar_without_an_opaque_band_is_rejected():
    transparent = Image.new("RGBA", (300, 20), (255, 255, 255, 0))
    with pytest.raises(ValueError, match="no tiene una franja opaca"):
        gradient_from_colour_bar(transparent)


def test_colour_bar_too_short_to_be_a_ramp_is_rejected():
    bar = np.zeros((20, 12, 4), dtype="uint8")
    bar[5:15, :, :3] = RAMP[None, :12, :]
    bar[5:15, :, 3] = 255
    with pytest.raises(ValueError, match="demasiado corta"):
        gradient_from_colour_bar(Image.fromarray(bar, "RGBA"))


def test_pm25_frame_that_is_not_a_2_to_1_map_is_not_published():
    svs = FakeSvs()
    svs.broken_frame = png(Image.new("RGB", (64, 64), tuple(int(c) for c in RAMP[100])))
    store = SceneStore(Pm25Source(svs.client(), steps=1, factor=2))
    store.refresh()
    assert store.get() is None
    assert "no es un mapa equirrectangular 2:1" in store.error


# --- Fotogramas de incendios -------------------------------------------------------


def test_exr_without_colour_channels_is_rejected(tmp_path):
    import OpenEXR

    path = tmp_path / "depth.exr"
    header = {"compression": OpenEXR.ZIP_COMPRESSION, "type": OpenEXR.scanlineimage}
    with OpenEXR.File(header, {"Z": np.zeros((4, 8), dtype="float32")}) as exr:
        exr.write(str(path))
    with pytest.raises(ValueError, match="no tiene canales RGB"):
        read_rgb(path.read_bytes())


def test_fires_page_without_frames_is_not_published():
    svs = FakeFireSvs()
    original = svs.get
    svs.get = lambda url: b"<html>sin enlaces</html>" if url.endswith("/SoaS/") else original(url)
    store = SceneStore(FireSource(svs.client(), steps=4, factor=4))
    store.refresh()
    assert store.get() is None
    assert "no lista fotogramas" in store.error


def test_fire_frame_that_is_not_a_2_to_1_map_is_not_published():
    svs = FakeFireSvs()
    square = exr_bytes(np.zeros((32, 32, 3), dtype="float32"))
    original = svs.get
    svs.get = lambda url: square if url.endswith(".exr") else original(url)
    store = SceneStore(FireSource(svs.client(), steps=4, factor=4))
    store.refresh()
    assert store.get() is None
    assert "no es un mapa 2:1" in store.error


@pytest.mark.parametrize(
    "fire_pixels, steps, expected",
    [
        ([20, 20, 20, 20, 20, 5, 0, 0, 0], 4, range(1, 5)),  # cola vacía y un fotograma a medias
        ([20, 21, 19, 20], 8, range(0, 4)),  # todos válidos y menos de los pedidos
        ([20, 20, 20, 13], 2, range(2, 4)),  # 13 es más del 60 % de lo habitual: se queda
        ([20, 20, 0, 0, 0, 0], 1, range(1, 2)),  # un solo paso y la cola vacía más larga que los datos
        ([20, 20, 20, 0, 0, 0, 0], 2, range(1, 3)),
        ([20, 20, 5, 0, 0, 0], 1, range(1, 2)),  # el fotograma a medias tampoco cuenta
        ([0, 0, 0], 4, range(0)),  # ningún incendio
        ([], 4, range(0)),
    ],
)
def test_frames_with_data(fire_pixels, steps, expected):
    assert frames_with_data(fire_pixels, steps) == expected


# --- HTTP --------------------------------------------------------------------------


def test_get_can_succeed_on_its_last_attempt(monkeypatch):
    outcomes = [server_error(502), FakeResponse(b"justo a tiempo")]

    def fake_open(request, timeout):
        outcome = outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    monkeypatch.setattr("app.services.http._open", fake_open)
    body = http_get("https://svs.gsfc.nasa.gov/x", attempts=2, sleep=lambda seconds: None)
    assert body == b"justo a tiempo"
