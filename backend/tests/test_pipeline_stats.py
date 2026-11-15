"""Las estadísticas por paso, su CSV y el resumen por día (`tools.summarize_episode`).

Solo necesita numpy: se ejecuta siempre, también sin el grupo `pipeline`.
"""

from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from geosfp.stats import (
    CSV_FIELDS,
    DaySummary,
    StepStats,
    read_stats_csv,
    step_statistics,
    summarize_by_day,
    top_steps,
    write_stats_csv,
)
from tools import summarize_episode

FIRST = datetime(2026, 7, 24, 19, 30, tzinfo=UTC)

# Tres pasos: dos del 24 de julio y uno del 25
ROWS = [
    StepStats("2026-07-24T19:30Z", europe_max=2.0, iberia_mean=0.25, iberia_max=0.5),
    StepStats("2026-07-24T22:30Z", europe_max=3.5, iberia_mean=0.75, iberia_max=1.25),
    StepStats("2026-07-25T01:30Z", europe_max=1.0, iberia_mean=0.125, iberia_max=0.375),
]


def steps(count: int) -> list[datetime]:
    return [FIRST + timedelta(hours=3 * i) for i in range(count)]


# --- Estadísticas por paso ---------------------------------------------------------


def test_each_step_gets_the_region_maximum_and_the_focus_mean_and_maximum():
    region = np.array([[[0.0, 1.0], [2.0, 4.0]], [[8.0, 0.5], [0.25, 0.0]]], dtype="float32")
    focus = np.array([[[1.0, 2.0]], [[0.5, 0.25]]], dtype="float32")

    rows = step_statistics(steps(2), region, focus)

    assert rows == [
        StepStats("2026-07-24T19:30Z", europe_max=4.0, iberia_mean=1.5, iberia_max=2.0),
        StepStats("2026-07-24T22:30Z", europe_max=8.0, iberia_mean=0.375, iberia_max=0.5),
    ]
    assert all(
        type(value) is float for value in (rows[0].europe_max, rows[0].iberia_mean, rows[0].iberia_max)
    )


def test_an_empty_series_has_no_rows():
    assert step_statistics([], np.empty((0, 4, 5)), np.empty((0, 2, 2))) == []


@pytest.mark.parametrize(
    ("region_steps", "focus_steps"), [(2, 3), (3, 2), (4, 4)], ids=["región", "zona", "ambas"]
)
def test_arrays_must_have_one_slice_per_step(region_steps, focus_steps):
    with pytest.raises(ValueError, match="Hay 3 pasos"):
        step_statistics(steps(3), np.zeros((region_steps, 2, 2)), np.zeros((focus_steps, 1, 1)))


def test_a_focus_without_cells_is_an_error():
    with pytest.raises(ValueError, match="no contiene ninguna celda"):
        step_statistics(steps(2), np.zeros((2, 3, 3)), np.zeros((2, 0, 3)))


def test_top_steps_are_sorted_by_focus_mean_from_highest():
    assert top_steps(ROWS, 2) == [ROWS[1], ROWS[0]]


def test_top_steps_with_fewer_rows_than_requested():
    assert top_steps(ROWS, 8) == [ROWS[1], ROWS[0], ROWS[2]]
    assert top_steps([], 8) == []


# --- CSV ---------------------------------------------------------------------------


def test_csv_keeps_the_columns_of_the_original_study(tmp_path):
    path = tmp_path / "episodio.csv"

    write_stats_csv(ROWS, path)

    lines = path.read_text(encoding="utf-8").splitlines()
    assert CSV_FIELDS == ("time_utc", "europe_max", "iberia_mean", "iberia_max")
    assert lines[0] == "time_utc,europe_max,iberia_mean,iberia_max"
    assert lines[1] == "2026-07-24T19:30Z,2.0,0.25,0.5"
    assert len(lines) == 1 + len(ROWS)


def test_csv_round_trip(tmp_path):
    path = tmp_path / "episodio.csv"
    rows = [StepStats("2026-07-24T19:30Z", europe_max=0.1 + 0.2, iberia_mean=1 / 3, iberia_max=2.5e-7)]

    write_stats_csv(rows, path)

    assert read_stats_csv(path) == rows


def test_csv_is_written_in_a_new_folder(tmp_path):
    path = tmp_path / "processed" / "episodes" / "episodio.csv"

    write_stats_csv(ROWS, path)

    assert read_stats_csv(path) == ROWS


def test_csv_without_rows_has_only_the_header(tmp_path):
    path = tmp_path / "vacio.csv"

    write_stats_csv([], path)

    assert path.read_text(encoding="utf-8").splitlines() == ["time_utc,europe_max,iberia_mean,iberia_max"]
    assert read_stats_csv(path) == []


def test_csv_with_missing_columns_is_rejected(tmp_path):
    path = tmp_path / "otro.csv"
    path.write_text("time_utc,europe_max\n2026-07-24T19:30Z,2.0\n", encoding="utf-8")

    with pytest.raises(ValueError, match="faltan las columnas iberia_max, iberia_mean"):
        read_stats_csv(path)


def test_empty_csv_file_is_rejected(tmp_path):
    path = tmp_path / "nada.csv"
    path.write_text("", encoding="utf-8")

    with pytest.raises(ValueError, match="faltan las columnas"):
        read_stats_csv(path)


def test_csv_with_a_value_that_is_not_a_number_is_rejected(tmp_path):
    path = tmp_path / "roto.csv"
    path.write_text(
        "time_utc,europe_max,iberia_mean,iberia_max\n2026-07-24T19:30Z,2.0,mucho,0.5\n", encoding="utf-8"
    )

    with pytest.raises(ValueError):
        read_stats_csv(path)


# --- Resumen por día ---------------------------------------------------------------


def test_days_are_summarised_in_date_order():
    summaries = summarize_by_day(reversed(ROWS))

    assert summaries == [
        DaySummary("2026-07-24", iberia_mean=0.5, iberia_max=1.25, europe_max=3.5),
        DaySummary("2026-07-25", iberia_mean=0.125, iberia_max=0.375, europe_max=1.0),
    ]


def test_summary_of_no_rows_is_empty():
    assert summarize_by_day([]) == []


# --- Script tools.summarize_episode ------------------------------------------------


def test_table_has_a_header_and_one_aligned_row_per_day():
    assert summarize_episode.format_table(summarize_by_day(ROWS)) == [
        "fecha        media_iberia  max_iberia  max_europa",
        "2026-07-24        0.5000       1.250       3.500",
        "2026-07-25        0.1250       0.375       1.000",
    ]


def test_script_prints_the_table_of_a_csv(tmp_path, capsys):
    source = tmp_path / "episodio.csv"
    write_stats_csv(ROWS, source)

    summarize_episode.main(["--source", str(source)])

    assert capsys.readouterr().out.splitlines() == summarize_episode.format_table(summarize_by_day(ROWS))


def test_script_with_an_empty_table_prints_only_the_header(tmp_path, capsys):
    source = tmp_path / "vacio.csv"
    write_stats_csv([], source)

    summarize_episode.main(["--source", str(source)])

    assert capsys.readouterr().out.splitlines() == ["fecha        media_iberia  max_iberia  max_europa"]


def test_script_reports_a_missing_file_without_a_traceback(tmp_path):
    with pytest.raises(SystemExit, match="Error: "):
        summarize_episode.main(["--source", str(tmp_path / "no-existe.csv")])


def test_script_default_source_is_the_table_written_by_find_episode():
    args = summarize_episode.build_parser().parse_args([])

    assert args.source.as_posix() == "data/processed/episodes/brexttau_europe_2026-07.csv"
