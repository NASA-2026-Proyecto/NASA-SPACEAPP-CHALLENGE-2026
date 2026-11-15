"""Los analizadores frente a respuestas reales de la NASA, guardadas el 14 y 15-11-2026.

Los falsos de los demás tests están escritos a mano; estos archivos son lo que los
servidores devolvieron de verdad, para que un cambio de formato no pase desapercibido.
"""

import json
from datetime import UTC, datetime, timedelta
from io import BytesIO

from PIL import Image

from app.services.geosfp import parse_das
from app.services.precipitation_scene import PrecipitationSource, class_colours, class_table
from app.services.svs import SvsClient, parse_page
from tests.fake_precipitation import RAIN, SNOW


def test_real_geosfp_das(fixture_text):
    grid = parse_das(fixture_text("geosfp_tavg3_2d_aer_Nx.das"))
    assert (grid.lat_min, grid.lat_step, grid.n_lat) == (-90.0, 0.25, 721)
    assert (grid.lon_min, grid.lon_step, grid.n_lon) == (-180.0, 0.3125, 1152)
    assert grid.time_step == timedelta(hours=3)
    assert grid.time_at(0) == datetime(2026, 2, 27, 1, 30, tzinfo=UTC)
    assert grid.time_at(grid.n_times - 1) == datetime(2026, 11, 14, 13, 30, tzinfo=UTC)


def test_real_svs_pm25_page(fixture_text):
    page = parse_page(json.loads(fixture_text("svs_5151.json")))
    assert (page.id, page.title) == (5151, "Particulate Matter (PM) 2.5")
    assert page.updated == datetime(2026, 11, 14, 7, 0, 58, 490675, tzinfo=UTC)  # 02:00 -05:00
    assert page.url == "https://svs.gsfc.nasa.gov/5151/"

    frames = page.find("Frames")
    assert frames.url.startswith("https://svs.gsfc.nasa.gov/") and frames.url.endswith("/")
    assert page.find("Image", "colorbar_plain").url.endswith("PM2.5_colorbar_plain.png")
    assert all(item.url.startswith("https://") for item in page.media)


def test_real_svs_fires_page(fixture_text):
    page = parse_page(json.loads(fixture_text("svs_5113.json")))
    assert page.id == 5113
    assert page.title.startswith("Active Fires As Observed by VIIRS")
    # La versión para proyectar en esfera (sin rótulos) es la que usa la escena de incendios
    assert page.find("Frames", "SoaS").url.endswith("/frames/4096x2048_2x1_30p/SoaS/")


def test_real_svs_precipitation_page_and_frame_listing(fixture_text):
    responses = {"4285": fixture_text("svs_4285.json"), "": fixture_text("svs_4285_flatalpha.html")}
    client = SvsClient(get=lambda url: responses[url.rsplit("/", 1)[1]].encode())

    page = client.page(4285)
    assert page.title.startswith("Near Real-Time Global Precipitation")
    # La versión con fondo transparente y sin rótulos es la que usa la escena
    assert page.find("Frames", "flatalpha").url.endswith("/frames/3600x1800_2x1_30p/flatalpha/")
    assert page.find("Image", "rainbarblack").url.endswith("/rainbarblack2.png")
    assert page.find("Image", "snowbarblack").url.endswith("/snowbarblack2.png")

    # 380 fotogramas de media hora, cada uno con su hora en el nombre
    version, frames = PrecipitationSource(client).check()
    assert version == "20261114T2130Z"
    assert len(frames.urls) == 380
    assert min(frames.urls) == datetime(2026, 11, 7, 0, 0, tzinfo=UTC)
    assert max(frames.urls) - min(frames.urls) == timedelta(minutes=30) * 379
    assert frames.urls[frames.newest].endswith("/flatalpha/imergert_alpha.2026-11-14T21:30:00Z.png")


def test_real_svs_precipitation_colour_bars(fixture_bytes):
    rain = class_colours(Image.open(BytesIO(fixture_bytes("svs_4285_rainbar.png"))))
    snow = class_colours(Image.open(BytesIO(fixture_bytes("svs_4285_snowbar.png"))))
    assert rain.tolist() == [list(colour) for colour in RAIN]  # 10 tramos y "más de 50"
    assert snow.tolist() == [list(colour) for colour in SNOW]  # 10 tramos
    assert len(class_table([rain, snow]).colours) == 21
