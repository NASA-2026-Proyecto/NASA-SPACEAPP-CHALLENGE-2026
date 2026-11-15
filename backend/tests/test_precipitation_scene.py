import hashlib
from io import BytesIO

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.factory import create_app
from app.services.colour_scale import classes_from_colour_bar
from app.services.precipitation_scene import (
    RAMP_STOPS,
    PrecipitationSource,
    class_colours,
    class_rates,
    class_table,
    decode_frame,
    ramp_stops,
)
from app.services.scenes import SceneStore
from tests.conftest import make_settings
from tests.fake_precipitation import (
    DRIZZLE,
    HEIGHT,
    RAIN,
    SNOW,
    SNOWFALL,
    STORM,
    UNDER,
    FakePrecipitationSvs,
    bar_png,
    frame_png,
)


def bar(colours) -> Image.Image:
    return Image.open(BytesIO(bar_png(colours)))


@pytest.fixture
def svs() -> FakePrecipitationSvs:
    return FakePrecipitationSvs(frames=20)


@pytest.fixture
def store(svs) -> SceneStore:
    # 4 pasos, uno de cada 2 fotogramas (cada hora), en bloques de 2 x 2 píxeles
    return SceneStore(PrecipitationSource(svs.client(), steps=4, frame_spacing=2, factor=2))


# --- Piezas ------------------------------------------------------------------------


def test_stepped_colour_bar_gives_one_colour_per_class():
    # Flecha gris, 10 tramos y la flecha alta; ni separadores negros ni la raya de 1 píxel
    assert classes_from_colour_bar(bar(RAIN)).tolist() == [list(UNDER), *map(list, RAIN)]
    # En la nieve la flecha alta repite el último tramo: cuenta una sola vez
    assert classes_from_colour_bar(bar(SNOW)).tolist() == [list(UNDER), *map(list, SNOW)]


def test_class_colours_leave_out_the_below_scale_arrow():
    assert class_colours(bar(RAIN)).tolist() == [list(colour) for colour in RAIN]
    assert len(class_colours(bar(SNOW))) == 10


def test_each_class_counts_as_the_geometric_middle_of_its_interval():
    rates = class_rates(11)
    assert rates[:3].tolist() == pytest.approx([0.1414, 0.2449, 0.3873], abs=1e-4)
    assert rates[9] == pytest.approx(31.62, abs=0.01)  # de 20 a 50
    assert rates[10] == 50.0  # "más de 50" vale la última marca
    assert len(class_rates(10)) == 10


def test_ramp_stops_follow_the_uneven_marks():
    rain = np.array(RAIN, dtype="uint8")
    stops = ramp_stops(rain)
    assert len(stops) == RAMP_STOPS
    assert (stops[0], stops[-1]) == ("#008114", "#910000")
    # De 1 a 2 mm/h (clase 4) ocupa más escala que de 2 a 3 (clase 5)
    assert stops.count("#b4e700") > stops.count("#fffb00")
    # Sin clase "más de 50", el final de la rampa es el último tramo
    assert ramp_stops(np.array(SNOW, dtype="uint8"))[-1] == "#8c149c"


def test_frame_is_decoded_into_one_grid_per_phase():
    table = class_table([np.array(RAIN, dtype="uint8"), np.array(SNOW, dtype="uint8")])
    rain, snow = decode_frame(frame_png(index=6), table, factor=2)
    assert rain.shape == snow.shape == (10, 20)
    assert rain.dtype == np.float32
    assert np.count_nonzero(rain) == 2 and np.count_nonzero(snow) == 1
    assert not np.isnan(rain).any()


# --- Escena ------------------------------------------------------------------------


def test_scene_matches_the_frontend_format(store):
    store.refresh()
    scene = store.get()
    manifest = scene.manifest.model_dump(exclude_none=True)

    assert (manifest["schema_version"], manifest["kind"], manifest["scene_id"], manifest["layer"]) == (
        2,
        "grid-series",
        "precipitation-latest",
        "precipitation",
    )
    grid = manifest["grid"]  # 40 x 20 píxeles en bloques de 2
    assert (grid["n_lat"], grid["n_lon"], grid["lon_periodic"]) == (10, 20, True)
    assert (grid["lat_min"], grid["lat_step"]) == (-81.0, 18.0)

    assert list(manifest["species"]) == ["rain", "snow"]
    for key in ("rain", "snow"):
        entry = manifest["species"][key]
        data = scene.files[f"{key}.f32"]
        assert len(data) == 4 * 10 * 20 * 4
        assert entry["sha256"] == hashlib.sha256(data).hexdigest()
        assert entry["unit"] == "mm/h"
        assert (entry["scale"]["kind"], entry["scale"]["min"], entry["scale"]["max"]) == ("log", 0.1, 50.0)
        assert len(entry["scale"]["ramp"]) == RAMP_STOPS
    assert manifest["species"]["rain"]["scale"]["ramp"][0] == "#008114"
    assert manifest["species"]["snow"]["scale"]["ramp"][0] == "#45ffff"


def test_stamps_are_the_times_in_the_file_names(store):
    store.refresh()
    scene = store.get()
    manifest = scene.manifest.model_dump(exclude_none=True)

    # 20 fotogramas de media hora desde las 12:00: el último es el de las 21:30
    time = manifest["time"]
    assert (time["steps"], time["step_minutes"]) == (4, 60)
    assert time["stamps_utc"] == [f"2026-11-14T{hour}:30Z" for hour in (18, 19, 20, 21)]
    assert scene.version == "20261114T2130Z"

    frames = manifest["provenance"]["source_frames"]
    assert [url.rsplit("imergert_alpha.", 1)[1] for url in frames] == [
        f"2026-11-14T{hour}:30:00Z.png" for hour in (18, 19, 20, 21)
    ]
    assert all(url.startswith("https://") and "/flatalpha/" in url for url in frames)
    assert [url.rsplit("/", 1)[1] for url in manifest["provenance"]["colour_bars"]] == [
        "rainbarblack2.png",
        "snowbarblack2.png",
    ]


def test_values_are_millimetres_per_hour_from_south_to_north(store):
    store.refresh()
    files = store.get().files
    rain = np.frombuffer(files["rain.f32"], dtype="<f4").reshape(4, 10, 20)
    snow = np.frombuffer(files["snow.f32"], dtype="<f4").reshape(4, 10, 20)

    # La tormenta está en las filas 12-13 de 20 (hemisferio sur): celda de latitud 3 de 10
    storm = rain[:, (HEIGHT - 1 - STORM[0].start) // 2, STORM[1].start // 2]
    # Fotogramas 13, 15, 17 y 19 -> clases 6, 7, 8 y 9: orden cronológico
    assert storm.tolist() == pytest.approx(class_rates(11)[6:10].tolist())

    # Un solo píxel de 1-2 mm/h en un bloque de 4: la celda es su media
    drizzle = rain[0, (HEIGHT - 1 - DRIZZLE[0]) // 2, DRIZZLE[1] // 2]
    assert drizzle == pytest.approx(2**0.5 / 4, abs=1e-4)

    # La nieve va en su propia especie y no cuenta como lluvia
    row, col = (HEIGHT - 1 - SNOWFALL[0].start) // 2, SNOWFALL[1].start // 2
    assert snow[0, row, col] == pytest.approx(0.1414, abs=1e-4)
    assert rain[0, row, col] == 0.0
    assert np.count_nonzero(snow[0]) == 1 and np.count_nonzero(rain[0]) == 2


def test_scene_is_rebuilt_only_when_a_newer_frame_appears(store, svs):
    store.refresh()
    first = store.get()
    svs.requests.clear()

    store.refresh()  # mismo listado: solo la página y el listado, ningún fotograma
    assert [url.rsplit("/", 1)[1] for url in svs.requests] == ["4285", ""]
    assert store.get() is first

    svs.frames += 1
    store.refresh()
    assert store.get().version == "20261114T2200Z"
    assert store.get().manifest.model_dump(exclude_none=True)["time"]["stamps_utc"][-1] == "2026-11-14T22:00Z"


def test_failure_keeps_the_last_good_scene(store, svs):
    store.refresh()
    good = store.get()
    svs.fail = True
    store.refresh()
    assert store.get() is good
    assert "SVS no responde" in store.error


def test_scene_is_served_by_the_same_endpoints(store):
    store.refresh()
    api = TestClient(create_app(make_settings(), scenes={"precipitation-latest": store}))
    manifest = api.get("/api/scenes/precipitation-latest/manifest.json").json()
    for entry in manifest["species"].values():
        file = api.get(f"/api/scenes/precipitation-latest/{entry['file']}")
        assert file.status_code == 200
        assert hashlib.sha256(file.content).hexdigest() == entry["sha256"]
