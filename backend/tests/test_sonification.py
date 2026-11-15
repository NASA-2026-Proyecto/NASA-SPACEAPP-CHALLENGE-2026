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
)
from tests.conftest import make_settings
from tests.fake_scenes import N_LAT, N_LON, cell, scene_of, store_of

FIRE = (-8.5, 20.5)  # un incendio de 6 MW en esta celda
RAIN = (5.5, -75.5)  # llueve aquí y cada vez más hacia el este


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
