"""La lógica pura del pipeline offline: eje de tiempo, validación y argumentos de los scripts.

Solo necesita numpy: se ejecuta siempre, también sin el grupo `pipeline`.
"""

import argparse
import logging
from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from app.services.geosfp import FILL_LIMIT
from geosfp.cli import configure_logging, region_from_bounds, utc_datetime
from geosfp.timeline import (
    TimeWindow,
    format_stamp,
    nearest_index,
    select_window,
    step_duration,
    time_axis,
)
from geosfp.validation import count_invalid, require_valid

FIRST = datetime(2026, 7, 24, 1, 30, tzinfo=UTC)
GRADS_TIME = {"grads_min": "01:30z24jul2026", "grads_step": "180mn"}


def axis(size: int = 10) -> list[datetime]:
    """Un eje como el del servidor: un paso cada 3 horas desde el 24 de julio a las 01:30."""
    return time_axis(GRADS_TIME, size)


# --- Paso de tiempo de GrADS -------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("180mn", timedelta(hours=3)),
        ("90mn", timedelta(minutes=90)),
        ("3hr", timedelta(hours=3)),
        ("1dy", timedelta(days=1)),
        ("10dy", timedelta(days=10)),
    ],
)
def test_step_understands_minutes_hours_and_days(text, expected):
    assert step_duration(text) == expected


@pytest.mark.parametrize(
    "text",
    ["1mo", "1yr", "30sc", "180", "mn", "", "3 hr", " 3hr", "-3hr", "1.5hr", "180MN", "3hrs"],
)
def test_unknown_step_is_rejected(text):
    with pytest.raises(ValueError, match="Paso de tiempo desconocido"):
        step_duration(text)


def test_zero_step_is_rejected():
    with pytest.raises(ValueError, match="no puede ser cero"):
        step_duration("0hr")


# --- Eje de tiempo -----------------------------------------------------------------


def test_time_axis_starts_at_grads_min_in_utc_and_advances_by_the_step():
    times = time_axis(GRADS_TIME, 4)

    assert times == [FIRST + timedelta(hours=3 * i) for i in range(4)]
    assert all(moment.tzinfo is UTC for moment in times)


@pytest.mark.parametrize(
    ("step", "second"),
    [
        ("180mn", datetime(2026, 7, 24, 4, 30, tzinfo=UTC)),
        ("3hr", datetime(2026, 7, 24, 4, 30, tzinfo=UTC)),
        ("1dy", datetime(2026, 7, 25, 1, 30, tzinfo=UTC)),
    ],
)
def test_time_axis_with_each_step_unit(step, second):
    assert time_axis({**GRADS_TIME, "grads_step": step}, 2) == [FIRST, second]


def test_time_axis_crosses_month_and_year_boundaries():
    times = time_axis({"grads_min": "00:00z31dec2026", "grads_step": "1dy"}, 2)

    assert times[1] == datetime(2027, 1, 1, tzinfo=UTC)


def test_time_axis_without_steps_is_empty():
    assert time_axis(GRADS_TIME, 0) == []


def test_time_axis_rejects_an_unknown_step_unit():
    with pytest.raises(ValueError, match="Paso de tiempo desconocido: '1mo'"):
        time_axis({**GRADS_TIME, "grads_step": "1mo"}, 3)


def test_time_axis_rejects_an_unreadable_start():
    with pytest.raises(ValueError):
        time_axis({**GRADS_TIME, "grads_min": "2026-07-24"}, 3)


def test_time_axis_needs_both_attributes():
    with pytest.raises(KeyError):
        time_axis({"grads_min": "01:30z24jul2026"}, 3)


# --- Paso más cercano --------------------------------------------------------------


@pytest.mark.parametrize(
    ("target", "expected"),
    [
        (FIRST, 0),
        (FIRST + timedelta(hours=6), 2),
        (FIRST + timedelta(hours=4), 1),
        (FIRST + timedelta(hours=5), 2),
        (FIRST - timedelta(days=30), 0),
        (FIRST + timedelta(days=30), 9),
    ],
    ids=[
        "primer paso",
        "paso exacto",
        "antes del medio",
        "después del medio",
        "antes del eje",
        "tras el eje",
    ],
)
def test_nearest_index(target, expected):
    assert nearest_index(axis(), target) == expected


def test_nearest_index_prefers_the_earlier_step_on_a_tie():
    halfway = FIRST + timedelta(hours=1, minutes=30)

    assert nearest_index(axis(), halfway) == 0


def test_nearest_index_of_an_empty_axis_is_an_error():
    with pytest.raises(ValueError, match="vacío"):
        nearest_index([], FIRST)


# --- Tramo de un episodio ----------------------------------------------------------


def test_window_snaps_both_ends_to_the_nearest_steps():
    window = select_window(
        axis(), datetime(2026, 7, 24, 7, tzinfo=UTC), datetime(2026, 7, 24, 17, tzinfo=UTC)
    )

    assert (window.first, window.last) == (2, 5)
    assert window.steps == tuple(axis()[2:6])
    assert window.index == slice(2, 6)


def test_window_of_a_single_instant_has_one_step():
    window = select_window(axis(), FIRST, FIRST)

    assert window == TimeWindow(first=0, last=0, steps=(FIRST,))


def test_window_can_cover_the_whole_axis():
    times = axis()

    assert select_window(times, times[0], times[-1]).steps == tuple(times)


def test_window_accepts_ends_within_one_step_of_the_axis():
    times = axis()
    window = select_window(times, times[0] - timedelta(hours=3), times[-1] + timedelta(hours=3))

    assert (window.first, window.last) == (0, 9)


@pytest.mark.parametrize(
    ("start", "end"),
    [
        (FIRST - timedelta(days=10), FIRST - timedelta(days=9)),
        (FIRST - timedelta(hours=3, minutes=1), FIRST + timedelta(hours=6)),
        (FIRST, FIRST + timedelta(days=30)),
    ],
    ids=["todo antes del eje", "empieza antes", "termina después"],
)
def test_window_outside_the_axis_is_an_error(start, end):
    with pytest.raises(ValueError, match="se sale del eje de tiempo"):
        select_window(axis(), start, end)


def test_window_that_ends_before_it_starts_is_an_error():
    with pytest.raises(ValueError, match="anterior al comienzo"):
        select_window(axis(), FIRST + timedelta(hours=6), FIRST)


def test_window_of_an_empty_axis_is_an_error():
    with pytest.raises(ValueError, match="vacío"):
        select_window([], FIRST, FIRST)


def test_stamp_format():
    assert format_stamp(datetime(2026, 7, 4, 1, 30, tzinfo=UTC)) == "2026-07-04T01:30Z"


# --- Validación de los valores descargados ------------------------------------------


def test_clean_values_have_no_invalid_cells():
    assert count_invalid(np.array([[0.0, 0.25], [3.5, 9.9e13]], dtype="float32")) == 0


def test_gaps_are_counted():
    values = np.array([0.1, np.nan, np.inf, -np.inf, 1.0e15, FILL_LIMIT, 0.2])

    assert count_invalid(values) == 5


def test_an_empty_array_has_no_invalid_cells():
    assert count_invalid(np.empty((0, 3, 3), dtype="float32")) == 0


def test_require_valid_accepts_clean_values():
    require_valid("duexttau", np.zeros((2, 2), dtype="float32"))


def test_require_valid_names_the_variable_and_counts_the_gaps():
    values = np.array([[0.1, 1.0e15], [np.nan, 0.2]], dtype="float32")

    with pytest.raises(ValueError, match=r"duexttau: contiene valores no válidos \(2 de 4 celdas\)"):
        require_valid("duexttau", values)


# --- Argumentos de los scripts -----------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2026-07-24", datetime(2026, 7, 24, tzinfo=UTC)),
        ("2026-07-24T01:00", datetime(2026, 7, 24, 1, tzinfo=UTC)),
        ("2026-07-24 01:00", datetime(2026, 7, 24, 1, tzinfo=UTC)),
        ("2026-07-24T01:00Z", datetime(2026, 7, 24, 1, tzinfo=UTC)),
        ("2026-07-24T03:00+02:00", datetime(2026, 7, 24, 1, tzinfo=UTC)),
    ],
)
def test_dates_are_read_as_utc(text, expected):
    moment = utc_datetime(text)

    assert moment == expected
    assert moment.utcoffset() == timedelta(0)


@pytest.mark.parametrize("text", ["", "ayer", "24/07/2026", "2026-13-01"])
def test_unreadable_dates_are_rejected(text):
    with pytest.raises(argparse.ArgumentTypeError, match="fecha no válida"):
        utc_datetime(text)


def test_region_from_bounds():
    assert region_from_bounds([35.0, 60.0, -15.0, 20.0]) == {
        "lat": slice(35.0, 60.0),
        "lon": slice(-15.0, 20.0),
    }


@pytest.mark.parametrize(
    "bounds",
    [[60.0, 35.0, -15.0, 20.0], [35.0, 60.0, 20.0, -15.0], [35.0, 35.0, -15.0, 20.0]],
    ids=["latitudes al revés", "longitudes al revés", "sin altura"],
)
def test_empty_regions_are_rejected(bounds):
    with pytest.raises(ValueError, match="Región vacía"):
        region_from_bounds(bounds)


def test_a_region_needs_four_numbers():
    with pytest.raises(ValueError, match="cuatro números"):
        region_from_bounds([35.0, 60.0, -15.0])


def test_configure_logging_shows_the_progress_of_the_library():
    library = logging.getLogger("geosfp")
    previous = library.level
    try:
        library.setLevel(logging.WARNING)
        configure_logging()
        assert logging.getLogger("geosfp.client").isEnabledFor(logging.INFO)
    finally:
        library.setLevel(previous)
