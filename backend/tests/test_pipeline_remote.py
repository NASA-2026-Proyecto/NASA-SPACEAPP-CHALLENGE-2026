"""La descarga de GEOS-FP con un servidor de mentira (necesita el grupo `pipeline`).

Ningún test sale a la red ni espera de verdad: la colección remota es un dataset en
memoria, los cortes de conexión se simulan al cargar los datos y `time.sleep` se
sustituye por una función que solo apunta las esperas.
"""

import logging
import time
from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

xr = pytest.importorskip("xarray", reason="requiere `uv run --group pipeline pytest`")
requests = pytest.importorskip("requests", reason="requiere `uv run --group pipeline pytest`")
pytest.importorskip("scipy", reason="requiere `uv run --group pipeline pytest`")

from geosfp.client import (  # noqa: E402
    DATASET_URL,
    dataset_window,
    load_in_chunks,
    load_series,
    load_with_retry,
    open_remote,
    plan_chunks,
)
from geosfp.episode import (  # noqa: E402
    build_episode,
    download_episode,
    episode_variable,
    fetch_episode,
    write_episode,
)
from geosfp.timeline import TimeWindow  # noqa: E402
from tools import download_global_episode, find_episode  # noqa: E402

FIRST = datetime(2026, 7, 24, 1, 30, tzinfo=UTC)
LAT = np.arange(30.0, 66.0, 5.0)  # 30, 35 ... 65
LON = np.arange(-20.0, 16.0, 5.0)  # -20, -15 ... 15
EUROPE = {"lat": slice(35.0, 60.0), "lon": slice(-15.0, 20.0)}
IBERIA = {"lat": slice(36.0, 44.0), "lon": slice(-10.0, 4.0)}
REAL_OPEN_DATASET = xr.open_dataset


def remote(n_times: int = 10, names: tuple[str, ...] = ("brexttau",)) -> "xr.Dataset":
    """Una colección pequeña con el eje de tiempo descrito como lo hace el servidor.

    El valor de cada celda es `paso + 0.1 * fila + 0.01 * columna` (más 100 por cada
    variable siguiente), así que se sabe qué debe salir de cada recorte.
    """
    step, row, column = np.meshgrid(
        np.arange(n_times), np.arange(LAT.size), np.arange(LON.size), indexing="ij"
    )
    field = (step + 0.1 * row + 0.01 * column).astype("float32")
    return xr.Dataset(
        {
            name: (("time", "lat", "lon"), field + 100 * order, {"long_name": f"  {name} optical depth  "})
            for order, name in enumerate(names)
        },
        coords={
            "time": (
                "time",
                np.arange(n_times, dtype="float64"),
                {"grads_min": "01:30z24jul2026", "grads_step": "180mn"},
            ),
            "lat": LAT,
            "lon": LON,
        },
    )


def window(first: int, last: int) -> TimeWindow:
    return TimeWindow(first, last, tuple(FIRST + timedelta(hours=3 * i) for i in range(first, last + 1)))


class Network:
    """Cuenta las descargas y hace fallar las que se le indiquen (la primera es la 1)."""

    def __init__(self) -> None:
        self.downloads = 0
        self.failing: set[int] = set()
        self.error: Exception = requests.exceptions.ConnectionError("corte simulado")

    def fail(self, *downloads: int) -> None:
        self.failing = set(downloads)

    def always_fail(self) -> None:
        self.failing = set(range(1, 1000))


@pytest.fixture
def network(monkeypatch) -> Network:
    state = Network()
    real_load = xr.DataArray.load

    def load(array, **kwargs):
        state.downloads += 1
        if state.downloads in state.failing:
            raise state.error
        return real_load(array, **kwargs)

    monkeypatch.setattr(xr.DataArray, "load", load)
    return state


@pytest.fixture(autouse=True)
def waits(monkeypatch) -> list[float]:
    """Las esperas pedidas a `time.sleep`, que en estos tests no duerme."""
    asked: list[float] = []
    monkeypatch.setattr(time, "sleep", asked.append)
    return asked


@pytest.fixture
def server(monkeypatch) -> list[str]:
    """Sustituye la apertura por OPeNDAP: toda URL abre la colección de mentira."""
    opened: list[str] = []

    def open_dataset(url, **_options):
        opened.append(url)
        return remote(names=("brexttau", "bcexttau", "duexttau", "suexttau", "ssexttau"))

    monkeypatch.setattr(xr, "open_dataset", open_dataset)
    return opened


# --- Reparto en bloques ------------------------------------------------------------


@pytest.mark.parametrize(
    ("total", "size", "expected"),
    [
        (0, 8, []),
        (1, 8, [slice(0, 1)]),
        (7, 8, [slice(0, 7)]),
        (8, 8, [slice(0, 8)]),
        (9, 8, [slice(0, 8), slice(8, 9)]),
        (16, 8, [slice(0, 8), slice(8, 16)]),
        (10, 4, [slice(0, 4), slice(4, 8), slice(8, 10)]),
        (3, 1, [slice(0, 1), slice(1, 2), slice(2, 3)]),
    ],
)
def test_chunks_cover_every_step_once_and_in_order(total, size, expected):
    assert plan_chunks(total, size) == expected


@pytest.mark.parametrize(("total", "size"), [(10, 0), (10, -1), (-1, 8)])
def test_chunks_need_a_positive_size_and_a_total(total, size):
    with pytest.raises(ValueError, match="No se pueden repartir"):
        plan_chunks(total, size)


# --- Reintentos --------------------------------------------------------------------


def test_load_without_failures_does_not_wait(network, waits):
    array = remote()["brexttau"]

    loaded = load_with_retry(array)

    assert np.array_equal(loaded.values, remote()["brexttau"].values)
    assert network.downloads == 1
    assert waits == []


def test_failed_first_attempt_is_retried_after_the_delay(network, waits):
    network.fail(1)

    loaded = load_with_retry(remote()["brexttau"], attempts=5, delay=3.0)

    assert np.array_equal(loaded.values, remote()["brexttau"].values)
    assert network.downloads == 2
    assert waits == [3.0]


def test_the_wait_doubles_after_each_failure(network, waits):
    network.fail(1, 2, 3)

    load_with_retry(remote()["brexttau"], attempts=5, delay=1.5)

    assert network.downloads == 4
    assert waits == [1.5, 3.0, 6.0]


def test_when_retries_run_out_the_network_error_reaches_the_caller(network, waits):
    network.always_fail()

    with pytest.raises(requests.exceptions.ConnectionError, match="corte simulado"):
        load_with_retry(remote()["brexttau"], attempts=3, delay=2.0)

    assert network.downloads == 3
    assert waits == [2.0, 4.0]  # tras el último intento ya no se espera


def test_a_single_attempt_never_waits(network, waits):
    network.always_fail()

    with pytest.raises(requests.exceptions.ConnectionError):
        load_with_retry(remote()["brexttau"], attempts=1)

    assert network.downloads == 1
    assert waits == []


@pytest.mark.parametrize(
    "error",
    [requests.exceptions.HTTPError("502 Bad Gateway"), requests.exceptions.Timeout("sin respuesta")],
    ids=["error del servidor", "tiempo de espera"],
)
def test_server_errors_and_timeouts_are_retried_too(network, waits, error):
    network.error = error
    network.fail(1)

    load_with_retry(remote()["brexttau"])

    assert network.downloads == 2


def test_errors_that_are_not_from_the_network_are_not_retried(network, waits):
    network.error = KeyError("variable desconocida")
    network.always_fail()

    with pytest.raises(KeyError):
        load_with_retry(remote()["brexttau"])

    assert network.downloads == 1
    assert waits == []


def test_at_least_one_attempt_is_required(network):
    with pytest.raises(ValueError, match="al menos un intento"):
        load_with_retry(remote()["brexttau"], attempts=0)

    assert network.downloads == 0


# --- Descarga por bloques ----------------------------------------------------------


def test_chunked_download_returns_the_whole_array(network, waits):
    original = remote(n_times=10)["brexttau"]

    loaded = load_in_chunks(remote(n_times=10)["brexttau"], size=4, pause=0.5)

    assert loaded.identical(original)  # mismos valores, coordenadas y atributos
    assert network.downloads == 3
    assert waits == [0.5, 0.5, 0.5]  # una pausa tras cada bloque


@pytest.mark.parametrize(("n_times", "size", "downloads"), [(8, 8, 1), (9, 8, 2), (16, 8, 2), (5, 8, 1)])
def test_chunk_boundaries(network, n_times, size, downloads):
    loaded = load_in_chunks(remote(n_times)["brexttau"], size=size)

    assert loaded.sizes["time"] == n_times
    assert np.array_equal(loaded.values, remote(n_times)["brexttau"].values)
    assert network.downloads == downloads


def test_a_chunk_that_fails_once_is_downloaded_again(network, waits):
    network.fail(2)  # el segundo bloque, al primer intento

    loaded = load_in_chunks(remote(n_times=10)["brexttau"], size=4, delay=3.0, pause=0.5)

    assert loaded.identical(remote(n_times=10)["brexttau"])
    assert network.downloads == 4
    assert waits == [0.5, 3.0, 0.5, 0.5]


def test_a_chunk_that_keeps_failing_stops_the_download(network, waits):
    network.fail(2, 3)

    with pytest.raises(requests.exceptions.ConnectionError):
        load_in_chunks(remote(n_times=10)["brexttau"], size=4, attempts=2, delay=3.0, pause=0.5)

    assert network.downloads == 3  # el tercer bloque ni se pide
    assert waits == [0.5, 3.0]


def test_other_dimensions_can_be_chunked(network):
    loaded = load_in_chunks(remote()["brexttau"], dim="lat", size=3)

    assert loaded.identical(remote()["brexttau"])
    assert network.downloads == 3


def test_nothing_to_download_is_an_error(network):
    with pytest.raises(ValueError, match="la dimensión 'time' está vacía"):
        load_in_chunks(remote()["brexttau"].isel(time=slice(0, 0)))

    assert network.downloads == 0


# --- Tramo de tiempo y series ------------------------------------------------------


def test_window_is_read_from_the_time_attributes_of_the_dataset(caplog):
    caplog.set_level(logging.INFO, logger="geosfp")

    selected = dataset_window(
        remote(), datetime(2026, 7, 24, 7, tzinfo=UTC), datetime(2026, 7, 24, 14, tzinfo=UTC)
    )

    assert selected == window(2, 4)
    assert "Pasos: 3 | 2026-07-24 07:30 -> 2026-07-24 13:30 UTC" in caplog.text


def test_window_outside_the_dataset_is_an_error():
    with pytest.raises(ValueError, match="se sale del eje de tiempo"):
        dataset_window(remote(), datetime(2026, 7, 14, tzinfo=UTC), datetime(2026, 7, 31, tzinfo=UTC))


def test_series_has_only_the_steps_of_the_window(network):
    series = load_series(remote(), "brexttau", window(2, 4))

    assert series.dims == ("time", "lat", "lon")
    assert series.shape == (3, LAT.size, LON.size)
    assert np.array_equal(series.values, remote()["brexttau"].values[2:5])


def test_series_can_be_cropped_to_a_region_with_both_ends_included(network):
    series = load_series(remote(), "brexttau", window(0, 1), region=EUROPE)

    assert series["lat"].values.tolist() == [35.0, 40.0, 45.0, 50.0, 55.0, 60.0]
    assert series["lon"].values.tolist() == [-15.0, -10.0, -5.0, 0.0, 5.0, 10.0, 15.0]


def test_series_can_be_subsampled_without_averaging(network):
    series = load_series(remote(), "brexttau", window(0, 0), lat_stride=4, lon_stride=3)

    assert series["lat"].values.tolist() == [30.0, 50.0]
    assert series["lon"].values.tolist() == [-20.0, -5.0, 10.0]
    assert np.array_equal(series.values[0], remote()["brexttau"].values[0, ::4, ::3])


def test_a_region_without_grid_cells_is_an_error(network):
    with pytest.raises(ValueError, match="no contiene ninguna celda"):
        load_series(
            remote(), "brexttau", window(0, 1), region={"lat": slice(80.0, 85.0), "lon": slice(0.0, 5.0)}
        )

    assert network.downloads == 0


@pytest.mark.parametrize(("lat_stride", "lon_stride"), [(0, 1), (1, 0), (-1, 1)])
def test_strides_must_be_positive(lat_stride, lon_stride):
    with pytest.raises(ValueError, match="deben ser al menos 1"):
        load_series(remote(), "brexttau", window(0, 1), lat_stride=lat_stride, lon_stride=lon_stride)


# --- Apertura de la colección ------------------------------------------------------


def test_collection_is_opened_with_the_dap2_scheme_first(monkeypatch):
    calls = []

    def open_dataset(url, **options):
        calls.append((url, options))
        return remote()

    monkeypatch.setattr(xr, "open_dataset", open_dataset)

    assert open_remote("https://example.test/dods/aer").identical(remote())
    assert calls == [("dap2://example.test/dods/aer", {"engine": "pydap", "decode_times": False})]


def test_plain_url_is_tried_when_the_dap2_scheme_fails(monkeypatch, caplog):
    tried = []

    def open_dataset(url, **_options):
        tried.append(url)
        if url.startswith("dap2://"):
            raise OSError("esquema no admitido")
        return remote()

    monkeypatch.setattr(xr, "open_dataset", open_dataset)

    assert open_remote("https://example.test/dods/aer").identical(remote())
    assert tried == ["dap2://example.test/dods/aer", "https://example.test/dods/aer"]
    assert "Falló dap2://example.test/dods/aer: OSError: esquema no admitido" in caplog.text


def test_collection_that_cannot_be_opened_is_a_runtime_error(monkeypatch):
    def open_dataset(url, **_options):
        raise requests.exceptions.ConnectionError(f"sin conexión con {url}")

    monkeypatch.setattr(xr, "open_dataset", open_dataset)

    with pytest.raises(RuntimeError, match="No se pudo abrir https://example.test/dods/aer") as failure:
        open_remote("https://example.test/dods/aer")

    assert isinstance(failure.value.__cause__, requests.exceptions.ConnectionError)


def test_default_collection_is_the_seamless_aerosol_product():
    assert DATASET_URL == (
        "https://opendap.nccs.nasa.gov/dods/GEOS-5/fp/0.25_deg/seamless/tavg3_2d_aer_Nx/tavg3_2d_aer_Nx.20261101_00"
    )


# --- Episodio ----------------------------------------------------------------------


def test_episode_variable_is_float32_over_step_lat_lon(network):
    series = load_series(remote(), "brexttau", window(0, 2), region=EUROPE)

    variable = episode_variable("brexttau", series.astype("float64", keep_attrs=True))

    assert variable.dims == ("step", "lat", "lon")
    assert variable.dtype == np.dtype("float32")
    assert variable.attrs == {"long_name": "brexttau optical depth"}
    assert variable["lat"].values.tolist() == series["lat"].values.tolist()
    assert np.array_equal(variable.values, series.values)


@pytest.mark.parametrize("gap", [1.0e15, np.nan, np.inf], ids=["relleno", "nan", "infinito"])
def test_episode_variable_with_gaps_is_rejected(gap):
    series = remote()["brexttau"].copy()
    series[1, 2, 3] = gap

    with pytest.raises(ValueError, match="brexttau: contiene valores no válidos"):
        episode_variable("brexttau", series)


def test_episode_needs_at_least_one_variable():
    with pytest.raises(ValueError, match="al menos una variable"):
        build_episode({}, window(0, 2).steps)


def test_episode_variables_must_have_one_slice_per_step():
    variable = episode_variable("brexttau", remote(n_times=3)["brexttau"])

    with pytest.raises(ValueError, match="brexttau: trae 3 pasos, se esperaban 2"):
        build_episode({"brexttau": variable}, window(0, 1).steps)


def test_episode_variables_must_share_the_grid():
    whole = episode_variable("brexttau", remote(n_times=2)["brexttau"])
    cropped = episode_variable("duexttau", remote(n_times=2)["brexttau"].sel(EUROPE))

    with pytest.raises(ValueError):
        build_episode({"brexttau": whole, "duexttau": cropped}, window(0, 1).steps)


def test_fetched_episode_describes_where_the_data_comes_from(network):
    episode = fetch_episode(
        remote(names=("brexttau", "duexttau")),
        datetime(2026, 7, 24, 1, tzinfo=UTC),
        datetime(2026, 7, 24, 8, tzinfo=UTC),
        ["brexttau", "duexttau"],
        lat_stride=4,
        lon_stride=2,
        source_url="https://example.test/dods/aer",
    )

    assert episode.attrs == {
        "source_dataset": "https://example.test/dods/aer",
        "product": "GEOS FP tavg3_2d_aer_Nx",
        "averaging": "3-hourly time average (GrADS step 180mn)",
        "units_note": "dimensionless (optical depth at 550 nm); not declared by server",
        "data_kind": "unverified",
        "subsampling": "every 4th lat and 2th lon; values not averaged",
        "time_stamps_utc": "2026-07-24T01:30Z,2026-07-24T04:30Z,2026-07-24T07:30Z",
    }
    assert list(episode.data_vars) == ["brexttau", "duexttau"]
    assert episode["step"].values.tolist() == [0, 1, 2]
    assert episode["lat"].values.tolist() == [30.0, 50.0]
    assert episode["lon"].values.tolist() == [-20.0, -10.0, 0.0, 10.0]
    assert np.array_equal(episode["duexttau"].values, remote()["brexttau"].values[:3, ::4, ::2] + 100)


def test_fetch_stops_at_the_first_variable_with_gaps(network):
    ds = remote(names=("brexttau", "duexttau", "suexttau"))
    ds["duexttau"][0, 0, 0] = 1.0e15

    with pytest.raises(ValueError, match="duexttau: contiene valores no válidos"):
        fetch_episode(ds, FIRST, FIRST + timedelta(hours=3), ["brexttau", "duexttau", "suexttau"])

    assert network.downloads == 2  # la tercera variable ya no se descarga


def test_fetch_without_variables_is_an_error(network):
    with pytest.raises(ValueError, match="al menos una variable"):
        fetch_episode(remote(), FIRST, FIRST, [])

    assert network.downloads == 0


def test_written_episode_has_the_layout_that_build_scene_reads(tmp_path, network):
    episode = fetch_episode(
        remote(names=("brexttau", "duexttau")), FIRST, FIRST + timedelta(hours=9), ["brexttau", "duexttau"]
    )
    path = tmp_path / "raw" / "episodio.nc"

    write_episode(episode, path)

    with REAL_OPEN_DATASET(path, engine="scipy", decode_times=False) as saved:
        assert dict(saved.sizes) == {"step": 4, "lat": LAT.size, "lon": LON.size}
        assert len(saved.attrs["time_stamps_utc"].split(",")) == saved.sizes["step"]
        assert saved["lat"].values.tolist() == LAT.tolist()
        assert saved["lon"].values.tolist() == LON.tolist()
        for name in ("brexttau", "duexttau"):
            assert saved[name].dims == ("step", "lat", "lon")
            assert saved[name].dtype == np.dtype("float32")
            assert saved[name].attrs["long_name"] == f"{name} optical depth"
            assert np.array_equal(saved[name].values, episode[name].values)
        assert saved.attrs == episode.attrs


def test_download_opens_the_collection_and_writes_the_file(tmp_path, server, network):
    path = tmp_path / "episodio.nc"

    download_episode(
        FIRST,
        FIRST + timedelta(hours=6),
        ["duexttau"],
        path,
        region=EUROPE,
        url="https://example.test/dods/aer",
    )

    assert server == ["dap2://example.test/dods/aer"]
    with REAL_OPEN_DATASET(path, engine="scipy", decode_times=False) as saved:
        assert dict(saved.sizes) == {"step": 3, "lat": 6, "lon": 7}
        assert saved.attrs["source_dataset"] == "https://example.test/dods/aer"
        assert saved.attrs["subsampling"] == "every 1th lat and 1th lon; values not averaged"


# --- Script tools.download_global_episode ------------------------------------------


def test_download_script_defaults_are_the_global_july_episode():
    args = download_global_episode.build_parser().parse_args([])

    assert args.start == datetime(2026, 7, 24, 1, 0, tzinfo=UTC)
    assert args.end == datetime(2026, 7, 28, 23, 0, tzinfo=UTC)
    assert args.variables == ["brexttau", "bcexttau", "duexttau", "suexttau", "ssexttau"]
    assert args.out.as_posix() == "data/raw/geosfp_aer_global_1deg_20260724_20260728.nc"
    assert (args.lat_stride, args.lon_stride, args.region) == (4, 4, None)
    assert args.url == DATASET_URL


def test_download_script_writes_the_episode(tmp_path, server, network, capsys):
    path = tmp_path / "episodio.nc"

    download_global_episode.main(
        ["--start", "2026-07-24T01:00", "--end", "2026-07-24T10:00", "--out", str(path)]
    )

    assert server == [DATASET_URL.replace("https://", "dap2://")]
    assert f"Episodio guardado en {path}" in capsys.readouterr().out
    with REAL_OPEN_DATASET(path, engine="scipy", decode_times=False) as saved:
        assert list(saved.data_vars) == ["brexttau", "bcexttau", "duexttau", "suexttau", "ssexttau"]
        assert dict(saved.sizes) == {"step": 4, "lat": 2, "lon": 2}
        assert saved.attrs["subsampling"] == "every 4th lat and 4th lon; values not averaged"
        assert saved.attrs["time_stamps_utc"].split(",")[0] == "2026-07-24T01:30Z"


def test_download_script_takes_the_region_and_the_variables_from_the_arguments(tmp_path, server, network):
    path = tmp_path / "europa.nc"

    download_global_episode.main(
        [
            "--start",
            "2026-07-24T01:30",
            "--end",
            "2026-07-24T04:30",
            "--variables",
            "duexttau",
            "--out",
            str(path),
        ]
        + ["--region", "35", "60", "-15", "20", "--lat-stride", "1", "--lon-stride", "2"]
    )

    with REAL_OPEN_DATASET(path, engine="scipy", decode_times=False) as saved:
        assert list(saved.data_vars) == ["duexttau"]
        assert saved["lat"].values.tolist() == [35.0, 40.0, 45.0, 50.0, 55.0, 60.0]
        assert saved["lon"].values.tolist() == [-10.0, 0.0, 10.0]


def test_download_script_reports_dates_that_the_server_does_not_have(tmp_path, server):
    path = tmp_path / "episodio.nc"

    with pytest.raises(SystemExit, match="Error: El intervalo pedido .* se sale del eje de tiempo"):
        download_global_episode.main(
            ["--out", str(path)]
        )  # las fechas por defecto no están en el servidor falso

    assert not path.exists()


def test_download_script_rejects_an_unreadable_date(capsys):
    with pytest.raises(SystemExit) as failure:
        download_global_episode.main(["--start", "ayer"])

    assert failure.value.code == 2
    assert "fecha no válida" in capsys.readouterr().err


# --- Script tools.find_episode -----------------------------------------------------


def test_find_script_defaults_are_the_european_smoke_study():
    args = find_episode.build_parser().parse_args([])

    assert args.start == datetime(2026, 7, 14, tzinfo=UTC)
    assert args.end == datetime(2026, 7, 31, tzinfo=UTC)
    assert args.variable == "brexttau"
    assert tuple(args.region) == (35.0, 60.0, -15.0, 20.0)
    assert tuple(args.focus) == (36.0, 44.0, -10.0, 4.0)
    assert args.out.as_posix() == "data/processed/episodes/brexttau_europe_2026-07.csv"
    assert args.url == DATASET_URL


def test_statistics_come_from_the_region_and_the_focus_zone(network, capsys):
    rows = find_episode.collect_statistics(
        remote(), FIRST, FIRST + timedelta(hours=6), "brexttau", region=EUROPE, focus=IBERIA
    )

    # Región: filas 1..6 y columnas 1..7. Zona de interés: fila 2 y columnas 2..4.
    assert [row.time_utc for row in rows] == ["2026-07-24T01:30Z", "2026-07-24T04:30Z", "2026-07-24T07:30Z"]
    assert [row.europe_max for row in rows] == pytest.approx([0.67, 1.67, 2.67], abs=1e-5)
    assert [row.iberia_mean for row in rows] == pytest.approx([0.23, 1.23, 2.23], abs=1e-5)
    assert [row.iberia_max for row in rows] == pytest.approx([0.24, 1.24, 2.24], abs=1e-5)
    output = capsys.readouterr().out
    assert "Recorte Europa: {'time': 3, 'lat': 6, 'lon': 7}" in output
    assert "Celdas no válidas: 0 de 126" in output


def test_statistics_are_not_computed_from_a_series_with_gaps(network, capsys):
    ds = remote()
    ds["brexttau"][1, 3, 3] = 1.0e15

    with pytest.raises(ValueError, match="Hay valores ausentes"):
        find_episode.collect_statistics(ds, FIRST, FIRST + timedelta(hours=6), "brexttau", EUROPE, IBERIA)

    assert "Celdas no válidas: 1 de 126" in capsys.readouterr().out


def test_find_script_writes_the_table_and_prints_the_top_steps(tmp_path, server, network, capsys):
    path = tmp_path / "episodes" / "tabla.csv"

    find_episode.main(["--start", "2026-07-24T01:30", "--end", "2026-07-25T04:30", "--out", str(path)])

    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "time_utc,europe_max,iberia_mean,iberia_max"
    assert len(lines) == 1 + 10
    assert lines[1].startswith("2026-07-24T01:30Z,0.67")
    output = capsys.readouterr().out.splitlines()
    assert f"Tabla guardada en {path}" in output
    top = output[output.index("Top 8 pasos por media sobre Iberia:") + 1 :]
    assert len(top) == 8
    assert top[0] == "  2026-07-25T04:30Z  media=9.2300  máx=9.2400  Europa máx=9.6700"
    assert top[-1] == "  2026-07-24T07:30Z  media=2.2300  máx=2.2400  Europa máx=2.6700"


def test_find_script_takes_the_regions_from_the_arguments(tmp_path, server, network, capsys):
    path = tmp_path / "tabla.csv"

    find_episode.main(
        [
            "--start",
            "2026-07-24T01:30",
            "--end",
            "2026-07-24T01:30",
            "--variable",
            "duexttau",
            "--out",
            str(path),
        ]
        + ["--region", "30", "40", "-20", "-10", "--focus", "30", "30.5", "-20", "-19.5"]
    )

    # Región: filas 0..2 y columnas 0..2 de la tercera variable (+200). Zona: la celda (0, 0).
    stamp, *values = path.read_text(encoding="utf-8").splitlines()[1].split(",")
    assert stamp == "2026-07-24T01:30Z"
    assert [float(value) for value in values] == pytest.approx([200.22, 200.0, 200.0], abs=1e-4)


def test_find_script_stops_when_the_collection_cannot_be_opened(tmp_path, monkeypatch):
    def open_dataset(url, **_options):
        raise requests.exceptions.ConnectionError("sin conexión")

    monkeypatch.setattr(xr, "open_dataset", open_dataset)

    with pytest.raises(SystemExit, match="Error: No se pudo abrir"):
        find_episode.main(["--out", str(tmp_path / "tabla.csv")])

    assert not (tmp_path / "tabla.csv").exists()


def test_find_script_rejects_an_empty_region(tmp_path, server):
    with pytest.raises(SystemExit, match="Error: Región vacía"):
        find_episode.main(["--region", "60", "35", "-15", "20", "--out", str(tmp_path / "tabla.csv")])

    assert server == []  # se comprueba antes de conectar
