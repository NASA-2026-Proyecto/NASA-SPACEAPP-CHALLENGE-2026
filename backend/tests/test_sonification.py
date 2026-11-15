"""Del punto de una escena al sonido: qué se lee, qué se dice y cuándo hay audio."""

import io
import threading
import wave

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.factory import create_app
from app.services.sonification import (
    SOUNDS,
    BusyError,
    NoAudioError,
    SceneNotReadyError,
    Sonifier,
    UnknownSoundError,
    cell_of,
    sample_point,
    survey,
)
from tests.conftest import make_settings
from tests.fake_scenes import N_LAT, N_LON, cell, scene_of, store_of

FIRE = (-8.5, 20.5)  # un incendio de 6 MW en esta celda
RAIN = (5.5, -75.5)  # llueve aquí y cada vez más hacia el este
WEST_OF_FIRE = (FIRE[0], FIRE[1] - 2)  # sin fuego en sus 3 x 3 celdas: en estéreo no suena
VERSION = "20261114T2130Z"


def fire_field() -> np.ndarray:
    field = np.zeros((N_LAT, N_LON), dtype="float32")
    field[cell(*FIRE)] = 6.0
    field[cell(-8.5, 23.5)] = 2.0  # otro más débil, 330 km al este
    return field


def rain_field() -> np.ndarray:
    field = np.zeros((N_LAT, N_LON), dtype="float32")
    row, col = cell(*RAIN)
    field[row - 6 : row + 7, col - 6 : col + 1] = 2.0
    field[row - 6 : row + 7, col + 1 : col + 7] = 12.0
    return field


def pm25_field() -> np.ndarray:
    field = np.full((N_LAT, N_LON), 8.0, dtype="float32")
    field[cell(60.5, -150.5)] = np.nan  # un logotipo
    return field


@pytest.fixture(scope="module")
def stores() -> dict:
    return {
        "fires-latest": store_of("fires-latest", scene_of("fires-latest", {"frp": fire_field()})),
        "precipitation-latest": store_of(
            "precipitation-latest",
            scene_of("precipitation-latest", {"rain": rain_field(), "snow": np.zeros((N_LAT, N_LON))}),
        ),
        "pm25-latest": store_of("pm25-latest", scene_of("pm25-latest", {"pm25": pm25_field()})),
    }


@pytest.fixture
def sonifier(stores) -> Sonifier:
    return Sonifier(stores)


@pytest.fixture
def api(stores) -> TestClient:
    return TestClient(create_app(make_settings(), scenes=stores))


# --- Leer el punto -----------------------------------------------------------------


def test_points_fall_in_the_cell_that_contains_them(stores):
    grid = stores["pm25-latest"].get().manifest.grid
    assert cell_of(grid, -8.5, 20.5) == cell(-8.5, 20.5)
    assert cell_of(grid, -8.9, 20.1) == cell(-8.5, 20.5)  # cualquier punto de la celda
    assert cell_of(grid, 90.0, 0.2) == (N_LAT - 1, 180)  # el polo cae en la última fila
    assert cell_of(grid, -90.0, 180.0) == (0, 0)  # 180° es la misma columna que -180°


def test_sample_reads_the_newest_step_at_the_cell_centre(stores):
    scene = stores["precipitation-latest"].get()
    sample = sample_point(SOUNDS["rain"], scene, RAIN[0] + 0.3, RAIN[1] - 0.2)
    assert (sample.lat, sample.lon) == RAIN
    assert sample.value == 2.0  # el paso más antiguo de la escena vale 0
    assert sample.stamp == "2026-11-14T21:30Z"
    assert sample.bearings.tolist() == [i * 11.25 for i in range(32)]

    # Llueve mucho más al este (90°) que al oeste (270°)
    east, west = sample.around[8], sample.around[24]
    assert east > 3 * west and west == pytest.approx(2.0)


def test_fire_value_is_the_strongest_fire_next_to_the_point(stores):
    scene = stores["fires-latest"].get()
    sound = SOUNDS["fire"]
    assert sample_point(sound, scene, *FIRE).value == 6.0
    assert sample_point(sound, scene, FIRE[0] + 1, FIRE[1] - 1).value == 6.0  # en diagonal: 3 x 3 celdas
    assert sample_point(sound, scene, FIRE[0], FIRE[1] - 2).value == 0.0  # a dos celdas ya no
    # Desde el incendio, el otro queda al este
    around = sample_point(sound, scene, *FIRE).around
    assert int(around.argmax()) == 8 and around[24] == 0.0


def test_directions_without_data_take_the_value_of_the_point():
    field = np.full((N_LAT, N_LON), np.nan, dtype="float32")
    field[cell(10.5, 10.5)] = 40.0
    sample = sample_point(SOUNDS["air"], scene_of("pm25-latest", {"pm25": field}), 10.5, 10.5)
    assert sample.value == 40.0
    assert sample.around.tolist() == [40.0] * 32


# --- Qué se dice -------------------------------------------------------------------


def test_reading_describes_the_sound_without_making_it(sonifier):
    reading = sonifier.read("rain", *RAIN)
    assert (reading.sound, reading.scene_id, reading.version) == (
        "rain",
        "precipitation-latest",
        "20261114T2130Z",
    )
    assert (reading.status, reading.value, reading.unit) == ("ok", 2.0, "mm/h")
    assert (reading.lat, reading.lon) == RAIN
    assert reading.intensity == pytest.approx(0.3608, abs=1e-4)
    assert reading.description.startswith("Precipitación de los satélites GPM del 14 nov 2026, 21:30 UTC")
    # Todo el lado este llueve igual: se nombra la primera de sus direcciones
    assert reading.description.endswith("Llueve más hacia el noreste: de ese lado llegan más gotas.")
    assert reading.audio == "rain/20261114T2130Z.wav?lat=5.5&lon=-75.5"
    assert reading.duration_s == 15.0
    assert reading.parameters["thunder"] == 0 and isinstance(reading.parameters["drops_per_s"], float)


def test_air_parameters_are_plain_json_values(sonifier):
    reading = sonifier.read("air", 40.5, -3.5)
    assert reading.parameters["semitones"] == [-12.0, 0.0, 1.0, 6.0, 13.0, 15.0]
    assert reading.parameters["intensity"] == reading.intensity == pytest.approx(0.355, abs=1e-3)
    assert "nivel moderado en la escala de la NASA" in reading.description


def test_no_fire_nearby_means_no_sound(sonifier):
    reading = sonifier.read("fire", 40.5, -3.5)
    assert (reading.status, reading.value) == ("absent", 0.0)
    assert reading.description.startswith("Sin incendios activos junto a este punto")
    assert reading.audio is None and reading.parameters is None and reading.intensity is None


def test_fire_nearby_names_its_power(sonifier):
    reading = sonifier.read("fire", *FIRE)
    assert (reading.status, reading.value, reading.intensity) == ("ok", 6.0, 0.75)
    assert reading.parameters["fire"] == "un incendio alrededor"
    assert "Hay más fuego hacia el este" in reading.description


def test_a_point_hidden_by_a_logo_has_no_data(sonifier):
    reading = sonifier.read("air", 60.5, -150.5)
    assert reading.status == "no_data"
    assert reading.value is None and reading.audio is None
    assert "no tiene dato en este punto" in reading.description


def test_dry_weather_still_has_a_sound(sonifier):
    reading = sonifier.read("rain", -30.5, 100.5)
    assert (reading.status, reading.value) == ("ok", 0.0)
    assert reading.description.endswith("No llueve: solo se oye el viento.")
    assert reading.audio is not None


def test_unknown_sounds_and_missing_scenes(stores):
    with pytest.raises(UnknownSoundError):
        Sonifier(stores).read("temperature", 0, 0)
    # Solo se ofrecen los sonidos cuya escena existe en la aplicación
    only_rain = Sonifier({"precipitation-latest": stores["precipitation-latest"]})
    assert only_rain.ids() == ["rain"]
    with pytest.raises(UnknownSoundError):
        only_rain.read("air", 0, 0)
    waiting = Sonifier({"pm25-latest": store_of("pm25-latest")})
    with pytest.raises(SceneNotReadyError):
        waiting.read("air", 0, 0)


# --- El audio ----------------------------------------------------------------------


@pytest.fixture(scope="module")
def fire_wav(stores) -> bytes:
    return Sonifier(stores).render("fire", "20261114T2130Z", *FIRE)


def test_audio_is_a_15_second_stereo_wav(fire_wav):
    with wave.open(io.BytesIO(fire_wav)) as wav:
        assert (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) == (2, 2, 44_100)
        assert wav.getnframes() == 15 * 44_100
        pcm = np.frombuffer(wav.readframes(wav.getnframes()), dtype="<i2")
    assert np.abs(pcm).max() > 3000  # suena


def test_audio_needs_a_known_version_and_a_point_with_sound(sonifier):
    with pytest.raises(NoAudioError, match="versión"):
        sonifier.render("fire", "20200101T0000Z", *FIRE)
    with pytest.raises(NoAudioError, match="no suena nada"):
        sonifier.render("fire", "20261114T2130Z", 40.5, -3.5)
    with pytest.raises(NoAudioError, match="no suena nada"):
        sonifier.render("air", "20261114T2130Z", 60.5, -150.5)
    with pytest.raises(UnknownSoundError):
        sonifier.render("temperature", "20261114T2130Z", 0, 0)


def test_only_a_few_sounds_are_made_at_once(stores):
    started, finish = threading.Event(), threading.Event()

    def slow(sample, parameters, seed):
        started.set()
        finish.wait(timeout=10)
        return np.zeros((2, 10))

    import dataclasses

    sounds = {"fire": dataclasses.replace(SOUNDS["fire"], synthesize=slow)}
    sonifier = Sonifier(stores, max_renders=1, sounds=sounds)
    first = threading.Thread(target=sonifier.render, args=("fire", "20261114T2130Z", *FIRE))
    first.start()
    try:
        assert started.wait(timeout=10)
        with pytest.raises(BusyError):
            sonifier.render("fire", "20261114T2130Z", *FIRE)
    finally:
        finish.set()
        first.join()
    # Al terminar el primero vuelve a haber sitio
    assert sonifier.render("fire", "20261114T2130Z", *FIRE)[:4] == b"RIFF"


# --- Rutas -------------------------------------------------------------------------


def test_sounds_are_listed(api):
    assert api.get("/api/sounds").json() == {"sounds": ["air", "fire", "rain"]}


def test_reading_route_returns_the_contract_without_empty_fields(api):
    response = api.get("/api/sounds/fire", params={"lat": 40.4, "lon": -3.7})
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-cache"
    body = response.json()
    assert body["status"] == "absent" and "audio" not in body and "parameters" not in body

    ok = api.get("/api/sounds/rain", params={"lat": RAIN[0], "lon": RAIN[1]}).json()
    assert ok["audio"] == "rain/20261114T2130Z.wav?lat=5.5&lon=-75.5"
    assert ok["parameters"]["drops_per_s"] > 0


def test_audio_route_serves_a_cacheable_wav(api, fire_wav):
    reading = api.get("/api/sounds/fire", params={"lat": FIRE[0], "lon": FIRE[1]}).json()
    response = api.get(f"/api/sounds/{reading['audio']}")
    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/wav"
    assert response.headers["cache-control"] == "public, max-age=86400, immutable"
    assert response.content == fire_wav  # el mismo punto suena siempre igual


def test_routes_reject_what_does_not_exist(api):
    point = {"lat": 0, "lon": 0}
    assert api.get("/api/sounds/temperature", params=point).status_code == 404
    assert api.get("/api/sounds/temperature/20261114T2130Z.wav", params=point).status_code == 404
    assert api.get("/api/sounds/fire/20200101T0000Z.wav", params=point).status_code == 404
    assert api.get("/api/sounds/fire/20261114T2130Z.wav", params=point).status_code == 404  # sin fuego
    assert api.get("/api/sounds/air", params={"lat": 95, "lon": 0}).status_code == 422
    assert api.get("/api/sounds/air", params={"lat": 0}).status_code == 422


def test_reading_route_asks_to_retry_while_the_scene_is_not_ready():
    api = TestClient(create_app(make_settings(), scenes={"pm25-latest": store_of("pm25-latest")}))
    response = api.get("/api/sounds/air", params={"lat": 0, "lon": 0})
    assert response.status_code == 503
    assert response.headers["retry-after"] == "5"
    assert "NASA" in response.json()["detail"]


def test_audio_route_asks_to_retry_when_busy(api, monkeypatch):
    def busy(*args, **kwargs):
        raise BusyError("fire")

    monkeypatch.setattr(Sonifier, "render", busy)
    response = api.get("/api/sounds/fire/20261114T2130Z.wav", params={"lat": FIRE[0], "lon": FIRE[1]})
    assert response.status_code == 503
    assert response.headers["retry-after"] == "2"
    assert response.headers["cache-control"] == "no-store"


# --- En tres dimensiones -------------------------------------------------------------


def test_survey_reads_every_cell_around_the_point_at_every_step(stores):
    around = survey(SOUNDS["fire"], stores["fires-latest"].get(), FIRE[0] + 0.3, FIRE[1] - 0.2)
    assert (around.lat, around.lon, around.far_km) == (*FIRE, 400)
    assert around.stamps == ("2026-11-14T18:30Z", "2026-11-14T21:30Z")
    assert around.values.shape == (2, around.km.size)
    assert around.km.max() <= 400 and around.km.size > 40

    own = np.flatnonzero(around.km == 0)
    assert own.size == 1 and around.values[:, own[0]].tolist() == [0.0, 6.0]
    # El otro incendio queda tres celdas al este; la celda de encima, justo al norte
    other = int(np.flatnonzero(around.values[1] == 2.0)[0])
    assert around.km[other] == pytest.approx(330, abs=5)
    assert around.bearing[other] == pytest.approx(90, abs=1)
    north = np.flatnonzero(np.isclose(around.bearing, 0) & (around.km > 0) & (around.km < 120))
    assert north.size == 1 and around.km[north[0]] == pytest.approx(111.2, abs=0.5)


def test_survey_crosses_the_date_line_reaches_around_the_pole_and_fills_gaps():
    field = np.full((N_LAT, N_LON), np.nan, dtype="float32")
    field[cell(0.5, -179.5)] = 5.0
    scene = scene_of("pm25-latest", {"pm25": field})

    around = survey(SOUNDS["air"], scene, 0.5, 179.5)
    east = int(around.values[1].argmax())
    assert around.values[1, east] == 5.0
    assert (around.bearing[east], around.km[east]) == pytest.approx((90, 111.2), abs=1)
    assert np.count_nonzero(around.values) == 1  # donde no hay dato cuenta como cero

    # Junto al polo el radio abarca todas las longitudes: hacia el norte, cruzando el polo, está
    # la celda del meridiano opuesto, tan cerca como la que queda justo al sur
    polar = survey(SOUNDS["air"], scene, 89.5, 0.5)
    one_cell_away = np.isclose(polar.km, 111.2, atol=0.5)
    northward = np.minimum(polar.bearing, 360 - polar.bearing) < 0.5
    assert np.count_nonzero(one_cell_away & northward) == 1
    assert np.count_nonzero(one_cell_away & np.isclose(polar.bearing, 180, atol=0.5)) == 1
    assert 3 * N_LON < polar.km.size < 4 * N_LON and polar.km.max() <= 400
    assert np.count_nonzero(polar.km == 0) == 1


def test_in_3d_a_far_fire_sounds_where_stereo_is_silent(sonifier):
    assert sonifier.read("fire", *WEST_OF_FIRE).status == "absent"
    reading = sonifier.read("fire", *WEST_OF_FIRE, "binaural")
    assert (reading.status, reading.mode, reading.value) == ("ok", "binaural", 0.0)
    assert reading.intensity == 0.75 and reading.parameters["fire"] == "un incendio alrededor"
    assert reading.audio == f"fire/{VERSION}.wav?lat=-8.5&lon=18.5&mode=binaural"
    assert reading.description.startswith("Sonido 3D para auriculares")
    assert "emite unos 6,0 MW y está a unos 220 km hacia el este" in reading.description


def test_in_3d_no_fire_in_the_whole_surroundings_means_no_sound(sonifier):
    reading = sonifier.read("fire", 40.5, -3.5, "binaural")
    assert (reading.status, reading.mode, reading.value) == ("absent", "binaural", 0.0)
    assert reading.description.startswith("Sin incendios activos a menos de 400 km de este punto")
    assert reading.audio is None and reading.parameters is None
    with pytest.raises(NoAudioError, match="no suena nada"):
        sonifier.render("fire", VERSION, 40.5, -3.5, mode="binaural")


def test_rain_in_3d_describes_its_surroundings(sonifier):
    reading = sonifier.read("rain", *RAIN, "binaural")
    assert (reading.status, reading.mode, reading.value) == ("ok", "binaural", 2.0)
    assert "Recorre los 2 pasos de la serie, del 14 nov 2026, 18:30 UTC al 14 nov 2026, 21:30 UTC" in (
        reading.description
    )
    assert "donde más, unos 12,0 mm/h (lluvia fuerte)" in reading.description
    assert reading.audio.endswith("&mode=binaural")


def test_stereo_is_the_default_and_the_answer_for_sounds_without_3d(sonifier):
    assert sonifier.read("rain", *RAIN).mode == "stereo"
    # El aire aún no tiene versión en tres dimensiones: pedirla da la lectura del estéreo
    asked = sonifier.read("air", 40.5, -3.5, "binaural")
    assert asked.mode == "stereo" and asked.audio == f"air/{VERSION}.wav?lat=40.5&lon=-3.5"
    assert asked == sonifier.read("air", 40.5, -3.5)
    assert sonifier.read("air", 60.5, -150.5, "binaural").status == "no_data"


@pytest.fixture(scope="module")
def far_fire_wav(stores) -> bytes:
    return Sonifier(stores).render("fire", VERSION, *WEST_OF_FIRE, mode="binaural")


def test_3d_audio_is_the_same_kind_of_file_and_leans_to_where_the_fire_is(far_fire_wav):
    with wave.open(io.BytesIO(far_fire_wav)) as wav:
        assert (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) == (2, 2, 44_100)
        assert wav.getnframes() == 15 * 44_100
        pcm = np.frombuffer(wav.readframes(wav.getnframes()), dtype="<i2").reshape(-1, 2).astype(float)
    left, right = np.sqrt(np.mean(pcm**2, axis=0))
    assert right > 1.2 * left > 0  # el incendio está al este


def test_3d_routes_take_the_mode_and_reject_unknown_ones(api, far_fire_wav):
    point = {"lat": WEST_OF_FIRE[0], "lon": WEST_OF_FIRE[1]}
    assert api.get("/api/sounds/fire", params=point).json()["mode"] == "stereo"
    reading = api.get("/api/sounds/fire", params={**point, "mode": "binaural"}).json()
    assert (reading["status"], reading["mode"]) == ("ok", "binaural")

    response = api.get(f"/api/sounds/{reading['audio']}")
    assert response.status_code == 200 and response.headers["content-type"] == "audio/wav"
    assert response.content == far_fire_wav  # el mismo punto suena siempre igual
    assert api.get(f"/api/sounds/fire/{VERSION}.wav", params=point).status_code == 404  # en estéreo, nada

    assert api.get("/api/sounds/fire", params={**point, "mode": "surround"}).status_code == 422
    assert api.get(f"/api/sounds/fire/{VERSION}.wav", params={**point, "mode": "5.1"}).status_code == 422
