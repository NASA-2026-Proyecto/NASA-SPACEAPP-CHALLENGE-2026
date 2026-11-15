"""Busca en GEOS-FP (NASA GMAO) los días con más aerosol sobre una zona de interés.

Descarga una variable para un tramo de fechas, recortada a una región amplia (por
defecto Europa), y calcula por cada paso de tiempo el máximo de la región y la media
y el máximo de una zona de interés dentro de ella (por defecto la península ibérica).
Guarda la tabla en un CSV (columnas time_utc, europe_max, iberia_mean, iberia_max, que
conservan esos nombres aunque se elijan otras regiones) y muestra los pasos con mayor
media. Con `tools.summarize_episode` el CSV se resume por día. Se conecta al servidor
OPeNDAP de la NASA (sin clave).

Uso, desde backend/:

    uv run --group pipeline python -m tools.find_episode
    uv run --group pipeline python -m tools.find_episode --start 2026-07-14 --end 2026-07-31
    uv run --group pipeline python -m tools.find_episode --variable duexttau --out data/processed/polvo.csv
    uv run --group pipeline python -m tools.find_episode --help

Las regiones se dan como `--region LAT_MIN LAT_MAX LON_MIN LON_MAX` (y `--focus` igual).
"""

import argparse
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import xarray as xr

from geosfp.cli import EXPECTED_ERRORS, REGION_METAVAR, configure_logging, region_from_bounds, utc_datetime
from geosfp.client import DATASET_URL, dataset_window, load_series, open_remote
from geosfp.stats import StepStats, step_statistics, top_steps, write_stats_csv
from geosfp.validation import count_invalid

DEFAULT_START = datetime(2026, 7, 14, tzinfo=UTC)
DEFAULT_END = datetime(2026, 7, 31, tzinfo=UTC)
DEFAULT_VARIABLE = "brexttau"
DEFAULT_REGION = (35.0, 60.0, -15.0, 20.0)  # Europa
DEFAULT_FOCUS = (36.0, 44.0, -10.0, 4.0)  # península ibérica
DEFAULT_OUT = Path("data/processed/episodes/brexttau_europe_2026-07.csv")
TOP_COUNT = 8


def collect_statistics(
    ds: xr.Dataset,
    start: datetime,
    end: datetime,
    variable: str,
    region: dict[str, slice],
    focus: dict[str, slice],
) -> list[StepStats]:
    """Descarga la serie de una variable y calcula sus estadísticas por paso.

    Args:
        ds: Colección remota ya abierta.
        start: Comienzo del tramo (UTC).
        end: Final del tramo (UTC, incluido).
        variable: Nombre de la variable.
        region: Recorte de la región amplia (`{"lat": slice, "lon": slice}`).
        focus: Recorte de la zona de interés, dentro de la región amplia.

    Returns:
        Una fila de estadísticas por paso de tiempo.

    Raises:
        ValueError: Si el tramo no está en la colección, algún recorte queda vacío o
            la serie trae celdas sin dato.
    """
    window = dataset_window(ds, start, end)
    series = load_series(ds, variable, window, region)
    print(f"Recorte Europa: {dict(series.sizes)}")
    invalid = count_invalid(series.values)
    print(f"Celdas no válidas: {invalid} de {series.size}")
    if invalid:
        raise ValueError("Hay valores ausentes: revisar antes de continuar.")
    return step_statistics(window.steps, series.values, series.sel(focus).values)


def format_top(rows: Sequence[StepStats]) -> list[str]:
    """Líneas de texto con las estadísticas de los pasos destacados, una por paso."""
    return [
        f"  {row.time_utc}  media={row.iberia_mean:.4f}  "
        f"máx={row.iberia_max:.4f}  Europa máx={row.europe_max:.4f}"
        for row in rows
    ]


def build_parser() -> argparse.ArgumentParser:
    """Define los argumentos de la línea de comandos, con el estudio de julio de 2026 por defecto."""
    parser = argparse.ArgumentParser(
        description="Calcula estadísticas por paso de tiempo de una variable de GEOS-FP y las guarda en CSV."
    )
    parser.add_argument(
        "--start",
        type=utc_datetime,
        default=DEFAULT_START,
        help="comienzo del tramo, ISO 8601 en UTC (por defecto: %(default)s)",
    )
    parser.add_argument(
        "--end",
        type=utc_datetime,
        default=DEFAULT_END,
        help="final del tramo, incluido, ISO 8601 en UTC (por defecto: %(default)s)",
    )
    parser.add_argument(
        "--variable", default=DEFAULT_VARIABLE, help="variable de la colección (por defecto: %(default)s)"
    )
    parser.add_argument(
        "--region",
        type=float,
        nargs=4,
        default=DEFAULT_REGION,
        metavar=REGION_METAVAR,
        help="región amplia en grados, columna europe_max (por defecto: Europa, %(default)s)",
    )
    parser.add_argument(
        "--focus",
        type=float,
        nargs=4,
        default=DEFAULT_FOCUS,
        metavar=REGION_METAVAR,
        help="zona de interés dentro de la región, columnas iberia_* "
        "(por defecto: península ibérica, %(default)s)",
    )
    parser.add_argument(
        "--out", type=Path, default=DEFAULT_OUT, help="archivo CSV de salida (por defecto: %(default)s)"
    )
    parser.add_argument(
        "--url", default=DATASET_URL, help="colección OPeNDAP de origen (por defecto: %(default)s)"
    )
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    """Punto de entrada: descarga la serie, guarda el CSV y muestra los pasos destacados.

    Args:
        argv: Argumentos de la línea de comandos; sin ellos se usan los del proceso.

    Raises:
        SystemExit: Si los argumentos no son válidos, la descarga falla o hay celdas sin dato.
    """
    args = build_parser().parse_args(argv)
    configure_logging()
    try:
        region, focus = region_from_bounds(args.region), region_from_bounds(args.focus)
        rows = collect_statistics(open_remote(args.url), args.start, args.end, args.variable, region, focus)
        write_stats_csv(rows, args.out)
    except EXPECTED_ERRORS as exc:
        raise SystemExit(f"Error: {exc}") from exc
    print(f"Tabla guardada en {args.out}")

    print(f"\nTop {TOP_COUNT} pasos por media sobre Iberia:")
    print("\n".join(format_top(top_steps(rows, TOP_COUNT))))


if __name__ == "__main__":
    main()
