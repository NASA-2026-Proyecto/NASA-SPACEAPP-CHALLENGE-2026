import hashlib
from datetime import UTC, datetime

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.factory import create_app
from app.services.colour_scale import max_pool
from app.services.exr import read_rgb
from app.services.fire_scene import RAMP_DISPLAY, FireSource, frp_from_rgb
from app.services.scenes import SceneStore
from app.services.svs import parse_frame_listing
from tests.conftest import make_settings
from tests.fake_fires import FIRES, HEIGHT, OCEAN, STRONG_FIRE, WIDTH, FakeFireSvs, frame_exr


@pytest.fixture
def svs() -> FakeFireSvs:
    return FakeFireSvs(frames=14, empty=3, partial=1)


@pytest.fixture
def store(svs) -> SceneStore:
    return SceneStore(FireSource(svs.client(), steps=4, factor=4))


# --- Piezas ------------------------------------------------------------------------


def test_exr_is_read_as_linear_rgb():
    rgb = read_rgb(frame_exr(fires=1))
    assert rgb.shape == (HEIGHT, WIDTH, 3)
    assert rgb.dtype == np.float32
    assert rgb[0, 0] == pytest.approx(OCEAN, abs=1e-3)
    assert rgb[FIRES[0]] == pytest.approx((0.446, 0.196, 0.027), abs=1e-3)


def test_red_channel_converts_to_megawatts():
    rgb = np.array(
        [
            [OCEAN, (0.446, 0.196, 0.027), (0.59, 0.4, 0.06)],
            [(0.25, 0.1, 0.0), (0.947, 0.92, 0.72), (1.0, 1.0, 1.0)],
        ]
    )
    power = frp_from_rgb(rgb.astype("float32"))
    assert power[0].tolist() == pytest.approx([0.0, 2.11, 3.79], abs=0.01)  # fondo, medio, alto
    # un borde suavizado cuenta como el fuego más débil; por encima de la barra, su máximo
    assert power[1].tolist() == pytest.approx([0.42, 8.0, 8.0], abs=0.01)


def test_max_pool_keeps_the_strongest_value_of_each_block():
    values = np.zeros((4, 8), dtype="float32")
    values[1, 1], values[3, 6], values[3, 7] = 5.0, 2.0, 3.0
    assert max_pool(values, 2).tolist() == [[5.0, 0.0, 0.0, 0.0], [0.0, 0.0, 0.0, 3.0]]
    with pytest.raises(ValueError, match="no es divisible"):
        max_pool(values, 3)


def test_frames_are_ordered_by_number_not_by_text():
    html = '<a href="f.1000.exr">a</a> <a href="f.999.exr">b</a> <a href="f.0998.exr">c</a>'
    urls = parse_frame_listing(html, "https://example.test/frames")
    assert [url.rsplit("/", 1)[1] for url in urls] == ["f.0998.exr", "f.999.exr", "f.1000.exr"]


def test_frame_links_given_as_absolute_paths_are_resolved():
    base = "https://svs.gsfc.nasa.gov/vis/a005113/frames/SoaS/"
    html = (
        "<link href=https://nasa.gov/favicons/favicon-16x16.png rel=icon>"
        '<a href="/vis/a005113/frames/SoaS/f.002.exr">f.002.exr</a>'
        '<a href="/vis/a005113/frames/SoaS/f.001.exr">f.001.exr</a>'
        '<a href="/vis/a005113/other/logo.png">logo</a>'
    )
    assert parse_frame_listing(html, base) == [f"{base}f.001.exr", f"{base}f.002.exr"]


# --- Escena ------------------------------------------------------------------------


def test_scene_skips_the_empty_newest_frames(store):
    store.refresh()
    scene = store.get()
    manifest = scene.manifest.model_dump(exclude_none=True)

    # De 14 fotogramas, los 3 últimos están vacíos y el 11 a medias: se usan del 7 al 10
    used = [url.rsplit("/", 1)[1] for url in manifest["provenance"]["source_frames"]]
    assert used == [f"fires_eq_nl.{n:03d}.exr" for n in (7, 8, 9, 10)]
    assert manifest["provenance"]["skipped_newest_frames"] == 4
    assert all(
        url.startswith("https://") and "/SoaS/" in url for url in manifest["provenance"]["source_frames"]
    )

    # Render del 14 de noviembre -> el fotograma 14 es el día 13; el 10, el día 9
    time = manifest["time"]
    assert (time["steps"], time["step_minutes"]) == (4, 1440)
    assert time["stamps_utc"] == [f"2026-11-0{day}T00:00Z" for day in (6, 7, 8, 9)]
    assert scene.version == "20261114T1129Z"


def test_scene_matches_the_frontend_format(store):
    store.refresh()
    scene = store.get()
    manifest = scene.manifest.model_dump(exclude_none=True)

    assert (manifest["schema_version"], manifest["kind"], manifest["scene_id"]) == (
        2,
        "grid-series",
        "fires-latest",
    )
    grid = manifest["grid"]  # 64 x 32 píxeles en bloques de 4
    assert (grid["n_lat"], grid["n_lon"], grid["lon_periodic"]) == (8, 16, True)
    assert (grid["lat_min"], grid["lat_step"]) == (-78.75, 22.5)

    entry = manifest["species"]["frp"]
    data = scene.files["frp.f32"]
    assert len(data) == 4 * 8 * 16 * 4
    assert entry["sha256"] == hashlib.sha256(data).hexdigest()
    assert entry["unit"] == "MW"
    assert entry["scale"] == {"kind": "linear", "min": 0.0, "max": 8.0, "ramp": list(RAMP_DISPLAY)}


def test_values_are_megawatts_from_south_to_north(store):
    store.refresh()
    values = np.frombuffer(store.get().files["frp.f32"], dtype="<f4").reshape(4, 8, 16)

    # El incendio fuerte está en la fila 20 de 32 (hemisferio sur): celda de latitud 2 de 8
    row, col = (HEIGHT - 1 - STRONG_FIRE[0]) // 4, STRONG_FIRE[1] // 4
    strong = values[:, row, col]
    assert np.all(np.diff(strong) > 0)  # crece de un día al siguiente: orden cronológico
    assert strong[-1] == pytest.approx(np.interp(0.517 + 0.02 * 10, [0.701, 0.768], [5.47, 6.32]), abs=0.02)

    # Un incendio fijo (2,11 MW) y una celda sin fuego
    fixed_row, fixed_col = (HEIGHT - 1 - FIRES[0][0]) // 4, FIRES[0][1] // 4
    assert values[0, fixed_row, fixed_col] == pytest.approx(2.11, abs=0.01)
    assert values[0, 0, 0] == 0.0
    assert not np.isnan(values).any()


def test_scene_is_rebuilt_only_when_nasa_renders_again(store, svs):
    store.refresh()
    first = store.get()
    svs.requests.clear()

    store.refresh()  # mismo render: página, listado y una petición HEAD; ningún fotograma
    assert not [url for url in svs.requests if url.endswith(".exr") and not url.startswith("HEAD")]
    assert store.get() is first

    svs.rendered = datetime(2026, 11, 15, 11, 30, tzinfo=UTC)
    store.refresh()
    assert store.get().version == "20261115T1130Z"
    assert store.get().manifest.model_dump(exclude_none=True)["time"]["stamps_utc"][-1] == "2026-11-10T00:00Z"


def test_nothing_is_published_when_no_frame_has_fires():
    store = SceneStore(FireSource(FakeFireSvs(frames=6, empty=6, partial=0).client(), steps=4, factor=4))
    store.refresh()
    assert store.get() is None
    assert "Ningún fotograma" in store.error


def test_failure_keeps_the_last_good_scene(store, svs):
    store.refresh()
    good = store.get()
    svs.fail = True
    store.refresh()
    assert store.get() is good
    assert "SVS no responde" in store.error


def test_scene_is_served_by_the_same_endpoints(store):
    store.refresh()
    api = TestClient(create_app(make_settings(), scenes={"fires-latest": store}))
    manifest = api.get("/api/scenes/fires-latest/manifest.json").json()
    entry = manifest["species"]["frp"]
    file = api.get(f"/api/scenes/fires-latest/{entry['file']}")
    assert file.status_code == 200
    assert hashlib.sha256(file.content).hexdigest() == entry["sha256"]
