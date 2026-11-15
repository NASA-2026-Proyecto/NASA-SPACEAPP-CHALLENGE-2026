"""El sonido en tres dimensiones: la cabeza, la distancia, el paso del tiempo y los dos sonidos que lo usan.

Cada sonido tarda en torno a un segundo, así que se genera una sola vez (fixtures de
módulo) y los tests miran propiedades suyas: de qué lado llega, cuánto se oye y cuándo.
"""

import numpy as np
import pytest

from app.services.sound import fire, rain, spatial
from app.services.sound.common import SECONDS, Surroundings
from app.services.sound.dsp import SAMPLE_RATE

SR = SAMPLE_RATE
# Un entorno mínimo: la celda del punto y una a 200 km en cada punto cardinal
HERE, NORTH, EAST, SOUTH, WEST = range(5)
BEARING = np.array([0.0, 0.0, 90.0, 180.0, 270.0])
KM = np.array([0.0, 200.0, 200.0, 200.0, 200.0])


def surroundings(values: list[list[float]], far_km: float = 400.0) -> Surroundings:
    """Entorno con un valor por celda en cada paso; los pasos son días a partir del 14 nov 2026."""
    stamps = tuple(f"2026-11-{14 + day}T00:00Z" for day in range(len(values)))
    return Surroundings(10.5, 20.5, BEARING, KM, np.array(values, dtype=np.float64), stamps, far_km)


def only(cell: int, value: float) -> list[float]:
    return [value if index == cell else 0.0 for index in range(5)]


def rms(audio: np.ndarray) -> float:
    return float(np.sqrt(np.mean(audio**2)))


def span(audio: np.ndarray, start: float, stop: float) -> np.ndarray:
    return audio[..., int(start * SR) : int(stop * SR)]


def high_band(audio: np.ndarray, low_hz: float) -> np.ndarray:
    spectrum = np.fft.rfft(audio, axis=-1)
    spectrum[..., np.fft.rfftfreq(audio.shape[-1], 1 / SR) < low_hz] = 0
    return np.fft.irfft(spectrum, n=audio.shape[-1], axis=-1)


def right_delay(audio: np.ndarray) -> int:
    """Muestras que tarda de más el oído derecho (positivo: la fuente está a la izquierda)."""
    left, right = span(audio, 0, 6)
    lags = range(-44, 45)
    scores = [np.dot(left[44:-44], right[44 + lag : right.size - 44 + lag]) for lag in lags]
    return lags[int(np.argmax(scores))]


# --- La cabeza y las piezas ----------------------------------------------------------


def test_the_head_is_a_ring_of_twelve_directions_at_the_sound_sample_rate():
    with np.load(spatial.HEAD_FILE) as data:
        assert int(data["sample_rate"]) == SR
        assert data["hrir"].shape == (12, 2, 512) and np.isfinite(data["hrir"]).all()
        # El norte, delante y arriba; el sur, detrás y abajo; el este, a la derecha (SOFA: 270°)
        assert (data["azimuths"][0], data["elevations"][0]) == (0, 40)
        assert (data["azimuths"][6], data["elevations"][6]) == (180, -40)
        assert (data["azimuths"][3], data["elevations"][3]) == (270, 0)
    head = spatial.head()
    assert head.bearings.tolist() == [30.0 * index for index in range(12)]
    assert head.spectra.shape == (12, 2, spatial.N_SAMPLES // 2 + 1)
    assert head.spectra.dtype == np.complex64
    assert spatial.head() is head  # se prepara una sola vez


def test_distance_on_the_map_becomes_metres_on_a_log_scale():
    km = np.array([0.0, 30.0, 400.0, 900.0])
    assert spatial.metres(km, 30, 400) == pytest.approx([1, 1, spatial.FAR_METRES, spatial.FAR_METRES])
    halfway = float(np.sqrt(30 * 400))  # a mitad de camino en escala logarítmica
    assert spatial.metres(np.array([halfway]), 30, 400) == pytest.approx([np.sqrt(spatial.FAR_METRES)])


def test_the_sound_walks_through_the_steps_and_stays_on_the_newest():
    seconds = np.array([0.0, 4.5, 9.0, 12.0])
    assert spatial.position(seconds, 3) == pytest.approx([0, 1, 2, 2])
    assert spatial.position(seconds, 1) == pytest.approx([0, 0, 0, 0])
    curve = spatial.follow(np.array([0.0, 10.0]))
    assert curve.size == spatial.N_SAMPLES
    assert curve[[0, int(4.5 * SR), int(9 * SR), -1]] == pytest.approx([0, 5, 10, 10], abs=0.01)
    assert spatial.follow(np.array([7.0])) == pytest.approx(7.0)


def test_grains_come_from_where_the_data_is_at_each_moment():
    rng = np.random.default_rng(0)
    # Al principio solo hay dato en la celda 0; al final, solo en la 1
    grains = spatial.draw_grains(rng, np.array([[50.0, 0.0], [0.0, 50.0]]))
    assert 450 < grains.seconds.size < 750 and np.all(np.diff(grains.seconds) >= 0)
    early, late = grains.seconds < 1.5, grains.seconds > 9
    assert np.mean(grains.cell[early] == 0) > 0.8
    assert np.all(grains.cell[late] == 1) and np.all(grains.step[late] == 1)
    assert np.array_equal(grains.cell, grains.step)  # cada paso solo tiene dato en una celda

    still = spatial.draw_grains(rng, np.array([[10.0, 30.0]]))
    assert np.all(still.step == 0) and 0.6 < np.mean(still.cell == 1) < 0.9

    nothing = spatial.draw_grains(rng, np.zeros((3, 4)))
    assert nothing.seconds.size == nothing.cell.size == nothing.step.size == 0


def test_grains_arrive_from_their_cell_and_surround_the_listener_at_the_point():
    rng = np.random.default_rng(0)
    cells = np.array([EAST] * 200 + [HERE] * 200)
    bearing = spatial.grain_bearings(rng, surroundings([only(EAST, 1.0)]), cells)
    assert np.all(np.abs(bearing[:200] - 90) <= spatial.BEARING_JITTER)
    assert np.ptp(bearing[200:]) > 300  # la celda propia: de todas partes


def test_noise_has_unit_level_and_stays_between_its_cuts():
    noise = spatial.unit_noise(np.random.default_rng(0), 1.0, 200, 1000)
    assert noise.size == spatial.N_SAMPLES
    assert rms(noise) == pytest.approx(1.0)
    assert rms(high_band(noise, 4000)) < 0.1


# --- El espacio ----------------------------------------------------------------------


def clicks_from(bearing: float, metres: float = 1.0, dull_far: bool = True) -> np.ndarray:
    """200 chasquidos iguales entre 0,5 y 5 s, desde un rumbo y una distancia."""
    rng = np.random.default_rng(0)
    t = np.arange(40) / SR
    shapes = [spatial.grain_shape(rng.standard_normal(40) * np.exp(-t / 0.0003), 500, 12_000)]
    space = spatial.Space(rng)
    count = 200
    space.add_grains(
        np.linspace(0.5, 5, count),
        np.full(count, 0.5),
        np.full(count, bearing),
        np.full(count, metres),
        shapes,
        dull_far=dull_far,
    )
    return space.render(0.7)


@pytest.fixture(scope="module")
def from_east() -> np.ndarray:
    return clicks_from(90)


@pytest.fixture(scope="module")
def from_afar() -> np.ndarray:
    return clicks_from(90, spatial.FAR_METRES)


def test_a_source_to_the_east_reaches_the_right_ear_louder_and_sooner(from_east):
    assert from_east.shape == (2, spatial.N_SAMPLES)
    assert rms(from_east[1]) > 2 * rms(from_east[0])
    assert -40 <= right_delay(from_east) <= -20  # unos 0,7 ms antes

    from_west = clicks_from(270)
    assert rms(from_west[0]) > 2 * rms(from_west[1])
    assert 20 <= right_delay(from_west) <= 40


def test_north_and_south_are_centred_but_do_not_sound_the_same():
    from_north, from_south = clicks_from(0), clicks_from(180)
    for audio in (from_north, from_south):
        assert rms(audio[1]) == pytest.approx(rms(audio[0]), rel=0.1)
        assert abs(right_delay(audio)) <= 2
    # Delante y arriba llega con más agudos que detrás y abajo: la oreja hace de pantalla
    brightness = [
        rms(high_band(span(audio, 0, 6), 5000)) / rms(span(audio, 0, 6)) for audio in (from_north, from_south)
    ]
    assert brightness[0] > 1.2 * brightness[1]


def test_far_sources_are_quieter_and_duller_but_the_room_stays(from_east, from_afar):
    near, far = span(from_east, 0.4, 5.02), span(from_afar, 0.4, 5.02)
    assert rms(far) < 0.4 * rms(near)

    def brightness(audio: np.ndarray) -> float:
        return rms(high_band(audio, 4000)) / rms(audio)

    assert brightness(far) < 0.8 * brightness(near)
    # Sin apagar lo lejano (granos que solo suenan cerca) conserva sus agudos
    assert brightness(
        span(clicks_from(90, spatial.FAR_METRES, dull_far=False), 0.4, 5.02)
    ) > 1.2 * brightness(far)
    # Tras el último chasquido solo queda la sala, igual de fuerte desde cerca que desde lejos
    assert rms(span(from_afar, 5.1, 5.6)) == pytest.approx(rms(span(from_east, 5.1, 5.6)), rel=0.02)


def test_the_same_seed_gives_the_same_space(from_east):
    assert np.array_equal(from_east, clicks_from(90))


def test_nothing_added_is_silence():
    space = spatial.Space(np.random.default_rng(0))
    empty = np.zeros(0)
    space.add_grains(empty, empty, empty, empty, [])
    assert not space.render(0.5).any()


def test_beds_sound_from_the_sectors_that_have_power():
    around = surroundings([only(EAST, 1.0)])
    made = []

    def noise() -> np.ndarray:
        made.append(1)
        return spatial.unit_noise(np.random.default_rng(len(made)), 1.0, 300, 6000)

    space = spatial.Space(np.random.default_rng(0))
    space.add_beds(around, np.array([only(EAST, 0.01)]), noise, np.ones(spatial.N_SAMPLES))
    audio = space.render(0.5)
    assert len(made) == 1  # solo el sector del este
    assert rms(audio[1]) > 1.5 * rms(audio[0])

    made.clear()
    space = spatial.Space(np.random.default_rng(0))
    space.add_beds(around, np.array([only(HERE, 0.01)]), noise, np.ones(spatial.N_SAMPLES))
    audio = space.render(0.5)
    assert len(made) == 6  # la celda propia se reparte entre todos los sectores
    assert rms(audio[1]) == pytest.approx(rms(audio[0]), rel=0.25)


# --- Fuego en tres dimensiones -------------------------------------------------------


@pytest.fixture(scope="module")
def fire_that_goes_out() -> np.ndarray:
    # Un incendio de 6 MW a 200 km al este el primer día; después, nada
    around = surroundings([only(EAST, 6.0), only(EAST, 0.0), only(EAST, 0.0)])
    return fire.synthesize_spatial(around, fire.spatial_mapping(around))


@pytest.fixture(scope="module")
def fire_here() -> np.ndarray:
    around = surroundings([only(HERE, 6.0)])
    return fire.synthesize_spatial(around, fire.spatial_mapping(around))


def test_fire_in_3d_has_the_expected_format(fire_here):
    assert fire_here.shape == (2, spatial.N_SAMPLES)
    assert np.isfinite(fire_here).all() and np.abs(fire_here).max() < 0.95
    assert rms(span(fire_here, 2, 10)) > 0.005  # suena


def test_a_fire_to_the_east_crackles_on_the_right_and_stops_when_it_goes_out(fire_that_goes_out):
    crackle = high_band(span(fire_that_goes_out, 0.3, 3), 1000)
    assert rms(crackle[1]) > 1.3 * rms(crackle[0])
    assert rms(span(fire_that_goes_out, 9.5, 11.5)) < 0.1 * rms(span(fire_that_goes_out, 0.3, 3))


def test_a_fire_at_the_point_surrounds_the_listener_and_is_louder_than_a_far_one(
    fire_here, fire_that_goes_out
):
    assert rms(fire_here[1]) == pytest.approx(rms(fire_here[0]), rel=0.25)
    assert rms(span(fire_here, 0.3, 3)) > 2 * rms(span(fire_that_goes_out, 0.3, 3))


def test_fire_timbre_is_that_of_the_fire_heard_the_most():
    # 8 MW a 200 km se oyen más que 1 MW en el punto, pero menos que 3 MW en el punto
    far_wins = surroundings([[1.0, 0.0, 8.0, 0.0, 0.0]])
    assert fire.spatial_mapping(far_wins) == fire.mapping(8.0)
    text = fire.describe_spatial(far_wins, fire.spatial_mapping(far_wins))
    assert text.startswith("Sonido 3D para auriculares: el norte suena delante y arriba")
    assert "Recorre los 1 pasos de la serie, del 14 nov 2026, 00:00 UTC al 14 nov 2026, 00:00 UTC" in text
    assert "emite unos 8,0 MW y está a unos 200 km hacia el este; suena como un incendio alrededor" in text
    assert text.endswith("hay fuego en 2 de las 5 celdas del entorno.")

    near_wins = surroundings([[0.0, 0.0, 8.0, 0.0, 0.0], [3.0, 0.0, 8.0, 0.0, 0.0]])
    assert fire.spatial_mapping(near_wins) == fire.mapping(3.0)
    assert "emite unos 3,0 MW y está en el propio punto" in fire.describe_spatial(
        near_wins, fire.mapping(3.0)
    )


def test_no_fire_anywhere_is_said_in_words():
    text = fire.describe_absent_spatial(surroundings([only(HERE, 0.0), only(HERE, 0.0)]))
    assert text == (
        "Sin incendios activos a menos de 400 km de este punto entre el 14 nov 2026, 00:00 UTC "
        "y el 15 nov 2026, 00:00 UTC (satélite VIIRS): no suena ningún fuego."
    )


# --- Lluvia en tres dimensiones ------------------------------------------------------


@pytest.fixture(scope="module")
def rain_everywhere() -> np.ndarray:
    around = surroundings([[20.0] * 5], far_km=300)
    return rain.synthesize_spatial(around, rain.spatial_mapping(around))


@pytest.fixture(scope="module")
def rain_that_passes() -> np.ndarray:
    # Seco, luego 12 mm/h a 200 km al oeste, luego seco otra vez
    around = surroundings([only(WEST, 0.0), only(WEST, 12.0), only(WEST, 0.0)], far_km=300)
    return rain.synthesize_spatial(around, rain.spatial_mapping(around))


def test_rain_in_3d_has_the_expected_format(rain_everywhere):
    assert rain_everywhere.shape == (2, spatial.N_SAMPLES)
    assert np.isfinite(rain_everywhere).all() and np.abs(rain_everywhere).max() <= 0.95


def test_heavy_rain_everywhere_is_about_as_loud_as_in_stereo_and_surrounds(rain_everywhere):
    from tests.test_sounds import sample

    stereo = rain.synthesize(sample(20.0, np.full(32, 20.0)), rain.mapping(20.0))
    level = rms(span(rain_everywhere, 2, 10)) / rms(span(stereo, 2, 10))
    # Con solo cinco celdas, la del punto pone la mitad de las gotas y suena más fuerte que en una
    # escena real (allí el nivel se ajustó al del estéreo): aquí basta con que no se dispare
    assert 0.5 < level < 2.5
    assert rms(rain_everywhere[1]) == pytest.approx(rms(rain_everywhere[0]), rel=0.25)


def test_rain_that_passes_to_the_west_swells_on_the_left_and_leaves_only_wind(rain_that_passes):
    during, after = span(rain_that_passes, 3.5, 5.5), span(rain_that_passes, 9.5, 11.5)
    assert rms(during) > 3 * rms(after)
    drops = high_band(during, 1000)
    assert rms(drops[0]) > 1.3 * rms(drops[1])
    assert rms(after) > 0  # el viento sigue
    assert rms(high_band(after, 1000)) < 0.1 * rms(drops)


def test_rain_timbre_is_that_of_the_rain_heard_on_average():
    dry = surroundings([only(HERE, 0.0)], far_km=300)
    assert rain.spatial_mapping(dry) == rain.mapping(0.0)
    text = rain.describe_spatial(dry, rain.mapping(0.0))
    assert "Precipitación medida por los satélites GPM hasta 300 km del punto" in text
    assert text.endswith("En el paso más reciente no llueve en el entorno.")

    everywhere = surroundings([[5.0] * 5], far_km=300)
    assert rain.spatial_mapping(everywhere).intensity == pytest.approx(rain.wetness(5.0))
    # Lo que no llega a lluvia no cuenta en la media
    one_side = surroundings([[0.01, 0.0, 12.0, 0.0, 0.0]], far_km=300)
    assert rain.spatial_mapping(one_side).intensity == pytest.approx(rain.wetness(12.0))
    text = rain.describe_spatial(one_side, rain.spatial_mapping(one_side))
    assert text.endswith(
        "En el paso más reciente llueve en 1 de las 5 celdas del entorno; donde más, "
        "unos 12,0 mm/h (lluvia fuerte), a unos 200 km hacia el este."
    )


def test_many_wetness_values_at_once_match_one_by_one():
    values = np.array([-1.0, 0.0, 0.3, 5.0, 20.0, 80.0])
    assert rain.wetness_field(values).tolist() == [rain.wetness(float(value)) for value in values]
    assert SECONDS == 12.0  # el recorrido de la serie (9 s) cabe en el sonido
