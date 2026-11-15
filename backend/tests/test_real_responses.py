"""Los analizadores frente a respuestas reales de la NASA, guardadas el 14-11-2026.

Los falsos de los demás tests están escritos a mano; estos archivos son lo que los
servidores devolvieron de verdad, para que un cambio de formato no pase desapercibido.
"""

import json
from datetime import UTC, datetime, timedelta

from app.services.geosfp import parse_das
from app.services.svs import parse_page


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
