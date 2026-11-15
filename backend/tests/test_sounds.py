"""Los tres sonidos: del dato a los parámetros, a las palabras y al audio.

Generar un sonido tarda en torno a un segundo, así que cada uno se genera una sola vez
(fixtures de módulo) y los tests miran propiedades suyas.
"""

import numpy as np
import pytest

from app.services.sound import air, fire, rain
from app.services.sound.common import SECONDS, TAIL, PointSample
from app.services.sound.dsp import SAMPLE_RATE, loudness_lufs

BEARINGS = np.arange(32) * 360 / 32
EAST = 1 + np.cos(np.radians(BEARINGS - 90))  # el doble hacia el este, nada hacia el oeste
N_SAMPLES = int((SECONDS + TAIL) * SAMPLE_RATE)


def sample(value: float, around: np.ndarray, stamp: str = "2026-11-14T21:30Z") -> PointSample:
    return PointSample(lat=10.5, lon=20.5, value=value, bearings=BEARINGS, around=around, stamp=stamp)


def rms(audio: np.ndarray) -> float:
    return float(np.sqrt(np.mean(audio**2)))


def high_band(audio: np.ndarray, low_hz: float) -> np.ndarray:
    spectrum = np.fft.rfft(audio, axis=-1)
    spectrum[..., np.fft.rfftfreq(audio.shape[-1], 1 / SAMPLE_RATE) < low_hz] = 0
    return np.fft.irfft(spectrum, n=audio.shape[-1], axis=-1)


def events(audio: np.ndarray, threshold: float) -> int:
    """Cuántas veces la señal salta por encima de un umbral: una medida de chasquidos."""
    loud = np.abs(audio).max(axis=0) > threshold
    return int(np.count_nonzero(loud[1:] & ~loud[:-1]))


# --- Aire --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def clean_air() -> np.ndarray:
    return air.synthesize(sample(2.0, 2 * EAST + 1), air.mapping(2.0))


@pytest.fixture(scope="module")
def dirty_air() -> np.ndarray:
    return air.synthesize(sample(300.0, 300 * EAST + 1), air.mapping(300.0))


def test_air_intensity_is_logarithmic_between_1_and_350():
    assert [air.haze(v) for v in (0.0, 1.0, 350.0, 5000.0)] == [0.0, 0.0, 1.0, 1.0]
    assert air.haze(18.7) == pytest.approx(0.5, abs=0.001)  # raíz de 350: la mitad de la escala
    steps = [air.haze(v) for v in (2, 4, 8, 16)]
    assert np.diff(steps) == pytest.approx([np.log(2) / np.log(350)] * 3)  # cada x2, el mismo paso


def test_air_parameters_grow_with_the_data_and_the_rest_stay_fixed():
    low, high = air.mapping(1.0), air.mapping(350.0)
    assert (low.dust_db, low.drone_db, low.wind_db) == (-7, -14, -6)
    assert (high.dust_db, high.drone_db, high.wind_db) == (0, 0, 0)
    assert high.loudness_lufs - low.loudness_lufs == pytest.approx(9.0)
    assert (low.dust_per_s, high.dust_per_s) == pytest.approx((200, 350.8))
    assert (low.semitones, low.width, low.reverb_s) == (high.semitones, high.width, high.reverb_s)


def test_air_level_words_match_the_position_on_nasas_scale():
    # Los mismos cinco tramos que usa el front (js/data/point-reading.js)
    assert [air.level(v) for v in (0.1, 0.5, 3.0, 10.0, 50.0, 300.0, 9999.0)] == [
        "muy bajo",
        "muy bajo",
        "bajo",
        "moderado",
        "alto",
        "muy alto",
        "muy alto",
    ]


def test_air_sound_has_the_expected_format(clean_air):
    assert clean_air.shape == (2, N_SAMPLES)
    assert clean_air.dtype == np.float64
    assert np.abs(clean_air).max() < 0.95
    assert np.abs(clean_air[:, -SAMPLE_RATE // 10 :]).max() < 1e-3  # acaba en silencio


def test_dirtier_air_sounds_louder_by_the_stated_amount(clean_air, dirty_air):
    clean, dirty = air.mapping(2.0), air.mapping(300.0)
    assert loudness_lufs(clean_air) == pytest.approx(clean.loudness_lufs, abs=0.5)
    assert loudness_lufs(dirty_air) == pytest.approx(dirty.loudness_lufs, abs=0.5)
    assert loudness_lufs(dirty_air) - loudness_lufs(clean_air) > 7


def test_air_dust_comes_from_the_dirtier_side(dirty_air):
    dust = high_band(dirty_air, 700)  # por encima del zumbido, que se corta a 450 Hz
    assert rms(dust[1]) > 1.1 * rms(dust[0])  # más polvo en el oído derecho: el este


def test_air_description_says_what_is_heard():
    text = air.describe(sample(35.0, 35 * EAST + 1), air.mapping(35.0))
    assert "unos 35,0 µg/m³, nivel alto en la escala de la NASA" in text
    assert "del 14 nov 2026, 21:30 UTC" in text
    assert "281 granos por segundo" in text and "6 dB por debajo de su máximo" in text
    assert text.endswith("El aire está más sucio hacia el este: de ese lado llegan más partículas.")

    worst = air.describe(sample(400.0, np.full(32, 400.0)), air.mapping(400.0))
    assert "con toda su fuerza" in worst
    assert "más sucio hacia" not in worst  # igual en todas las direcciones: no se dice ninguna


# --- Lluvia ------------------------------------------------------------------------


@pytest.fixture(scope="module")
def dry() -> np.ndarray:
    return rain.synthesize(sample(0.0, np.zeros(32)), rain.mapping(0.0))


@pytest.fixture(scope="module")
def drizzle() -> np.ndarray:
    return rain.synthesize(sample(0.3, 0.3 * EAST), rain.mapping(0.3))


@pytest.fixture(scope="module")
def downpour() -> np.ndarray:
    return rain.synthesize(sample(25.0, 25 * EAST), rain.mapping(25.0))


def test_rain_intensity_grows_like_the_logarithm_and_saturates_at_20():
    assert rain.wetness(0.0) == 0.0 and rain.wetness(-1.0) == 0.0
    assert rain.wetness(20.0) == 1.0 and rain.wetness(50.0) == 1.0
    assert rain.wetness(3.58) == pytest.approx(0.5, abs=0.001)  # log(1 + 3,58) es la mitad de log(21)


def test_rain_parameters_from_dry_to_downpour():
    none, trace, full = rain.mapping(0.0), rain.mapping(0.04), rain.mapping(20.0)
    assert (none.drops_per_s, none.taps_per_s, none.thunder) == (0, 0, 0)
    assert trace.drops_per_s == 0  # por debajo de 0,05 mm/h no cae ninguna gota
    assert (full.drops_per_s, full.taps_per_s, full.thunder) == (25_000, 60, 3)
    assert (none.sheet_db, full.sheet_db) == (-16, 0)
    assert [rain.mapping(v).thunder for v in (1.0, 4.0, 6.0, 10.0)] == [0, 0, 1, 2]
    drops = [rain.mapping(v).drops_per_s for v in (0.1, 1, 5, 20)]
    assert drops == sorted(drops)


def test_rain_categories_follow_the_meteorological_ones():
    assert [rain.category(v) for v in (0.0, 0.04, 0.05, 2.4, 2.5, 7.5, 7.6, 40.0)] == [
        "seco",
        "seco",
        "lluvia débil",
        "lluvia débil",
        "lluvia moderada",
        "lluvia moderada",
        "lluvia fuerte",
        "lluvia fuerte",
    ]


def test_rain_sound_has_the_expected_format(downpour):
    assert downpour.shape == (2, N_SAMPLES)
    assert np.abs(downpour).max() < 0.95
    assert np.abs(downpour[:, -SAMPLE_RATE // 10 :]).max() < 1e-3


def test_more_rain_is_louder_and_denser(dry, drizzle, downpour):
    assert rms(dry) < rms(drizzle) < rms(downpour)
    assert rms(downpour) > 10 * rms(dry)  # en seco solo queda una brisa
    heard = slice(2 * SAMPLE_RATE, 9 * SAMPLE_RATE)
    hiss = [rms(high_band(x[:, heard], 3000)) for x in (dry, drizzle, downpour)]
    assert hiss[0] < 0.05 * hiss[1] and hiss[1] < 0.3 * hiss[2]  # sin gotas no hay siseo


def test_rain_comes_from_the_wetter_side(downpour):
    assert rms(downpour[1]) > 1.1 * rms(downpour[0])


def test_rain_description_says_what_is_heard():
    wet = rain.describe(sample(3.0, 3 * EAST**3), rain.mapping(3.0))
    assert "unos 3,0 mm por hora, lluvia moderada" in wet
    assert "un repiqueteo constante (en torno a 3498 gotas pequeñas por segundo)" in wet
    assert "y 18 gotas gordas por segundo golpeando cerca." in wet
    assert wet.endswith("Llueve más hacia el este: de ese lado llegan más gotas.")

    assert "el crepitar de gotas sueltas" in rain.describe(sample(0.3, 0.3 * EAST), rain.mapping(0.3))
    # Con tan poca lluvia no hay gotas gordas que nombrar
    trace = rain.describe(sample(0.06, np.zeros(32)), rain.mapping(0.06))
    assert trace.endswith(
        "lluvia débil. Se oye el crepitar de gotas sueltas (en torno a 1 gotas pequeñas por segundo)."
    )
    storm = rain.describe(sample(25.0, np.full(32, 25.0)), rain.mapping(25.0))
    assert "el siseo denso de un aguacero" in storm and storm.endswith("3 truenos.")
    assert rain.describe(sample(6.0, np.full(32, 6.0)), rain.mapping(6.0)).endswith("1 trueno.")
    nothing = rain.describe(sample(0.0, np.zeros(32)), rain.mapping(0.0))
    assert nothing.endswith("unos 0,0 mm por hora, seco. No llueve: solo se oye el viento.")


# --- Fuego -------------------------------------------------------------------------


def embers_audio(seed: int = 0) -> np.ndarray:
    return fire.synthesize(sample(0.42, np.zeros(32)), fire.mapping(0.42), seed)


@pytest.fixture(scope="module")
def embers() -> np.ndarray:
    return embers_audio()


@pytest.fixture(scope="module")
def wildfire() -> np.ndarray:
    return fire.synthesize(sample(8.0, 4 * EAST), fire.mapping(8.0))


def test_fire_intensity_is_the_position_on_nasas_linear_scale():
    assert [fire.intensity(v) for v in (0.0, 2.0, 8.0, 30.0)] == [0.0, 0.25, 1.0, 1.0]


def test_fire_parameters_grow_from_embers_to_wildfire():
    low, high = fire.mapping(0.0), fire.mapping(8.0)
    assert (low.crackles_per_s, high.crackles_per_s) == (1.5, 39.5)
    assert (low.crackle_db, high.crackle_db) == (-6, 0)
    assert (low.width, high.width) == (0.25, 1.0)
    assert low.flicker_hz == pytest.approx(7) and high.flicker_hz == pytest.approx(
        0.8
    )  # llamas grandes, lentas
    assert low.crackle_hz > high.crackle_hz and low.roar_hz < high.roar_hz
    assert [fire.mapping(v).fire for v in (0.42, 2.0, 5.0, 8.0)] == [
        "unas brasas que chasquean",
        "una fogata pequeña",
        "una hoguera grande",
        "un incendio alrededor",
    ]


def test_fire_sound_has_the_expected_format(wildfire):
    assert wildfire.shape == (2, N_SAMPLES)
    assert np.abs(wildfire).max() < 0.95
    assert np.abs(wildfire[:, -SAMPLE_RATE // 10 :]).max() < 1e-3


def test_a_stronger_fire_is_louder_and_crackles_more(embers, wildfire):
    assert rms(wildfire) > 3 * rms(embers)
    crackles = [events(high_band(x, 1000), 0.02) for x in (embers, wildfire)]
    assert crackles[1] > 5 * crackles[0] > 0


def test_fire_crackles_come_from_the_side_with_more_fire(wildfire):
    crackle = high_band(wildfire, 1000)
    assert rms(crackle[1]) > 1.2 * rms(crackle[0])


def test_the_same_point_and_seed_always_sound_the_same(embers):
    assert np.array_equal(embers, embers_audio())
    assert not np.array_equal(embers, embers_audio(seed=1))


def test_fire_description_says_what_is_heard():
    text = fire.describe(sample(4.2, EAST**4, "2026-11-08T00:00Z"), fire.mapping(4.2))
    assert "dato del 8 nov 2026, 00:00 UTC" in text
    assert "el más fuerte junto a este punto emite unos 4,2 MW" in text
    assert "Se oye una hoguera grande: unas 15 ráfagas de chasquidos por segundo" in text
    assert text.endswith("Hay más fuego hacia el este: de ese lado llegan más chasquidos.")

    alone = fire.describe(sample(4.2, np.zeros(32)), fire.mapping(4.2))
    assert "Hay más fuego hacia" not in alone  # el único incendio está en el propio punto

    absent = fire.describe_absent(sample(0.0, np.zeros(32), "2026-11-08T00:00Z"))
    assert absent.startswith("Sin incendios activos junto a este punto")
    assert "no suena ningún fuego" in absent
