"""Descarga un episodio de aerosoles de GEOS-FP (NASA GMAO) y lo guarda en un NetCDF.

Baja el espesor óptico de varias especies para un tramo de fechas. Por defecto cubre
todo el globo tomando una de cada cuatro celdas en cada dirección; con `--region` se
recorta a un rectángulo. El archivo resultante es la entrada de `tools.build_scene`.
Se conecta al servidor OPeNDAP de la NASA (sin clave).

Uso, desde backend/:

    uv run --group pipeline python -m tools.download_global_episode
    uv run --group pipeline python -m tools.download_global_episode --start 2026-07-24 --end 2026-07-29
    uv run --group pipeline python -m tools.download_global_episode --variables duexttau --out data/raw/du.nc
    uv run --group pipeline python -m tools.download_global_episode --help

Para un recorte a resolución completa: `--region LAT_MIN LAT_MAX LON_MIN LON_MAX
--lat-stride 1 --lon-stride 1` (por ejemplo, Europa es `--region 35 60 -15 20`).
"""

import argparse
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from geosfp.cli import EXPECTED_ERRORS, REGION_METAVAR, configure_logging, region_from_bounds, utc_datetime
from geosfp.client import DATASET_URL
from geosfp.episode import download_episode

DEFAULT_START = datetime(2026, 7, 24, 1, 0, tzinfo=UTC)
DEFAULT_END = datetime(2026, 7, 28, 23, 0, tzinfo=UTC)
DEFAULT_VARIABLES = ("brexttau", "bcexttau", "duexttau", "suexttau", "ssexttau")
DEFAULT_OUT = Path("data/raw/geosfp_aer_global_1deg_20260724_20260728.nc")
DEFAULT_STRIDE = 4


def build_parser() -> argparse.ArgumentParser:
    """Define los argumentos de la línea de comandos, con el episodio de julio de 2026 por defecto."""
    parser = argparse.ArgumentParser(
        description="Descarga un episodio de aerosoles de GEOS-FP a un archivo NetCDF."
    )
    parser.add_argument(
        "--start",
        type=utc_datetime,
        default=DEFAULT_START,
        help="comienzo del episodio, ISO 8601 en UTC (por defecto: %(default)s)",
    )
    parser.add_argument(
        "--end",
        type=utc_datetime,
        default=DEFAULT_END,
        help="final del episodio, incluido, ISO 8601 en UTC (por defecto: %(default)s)",
    )
    parser.add_argument(
        "--variables",
        nargs="+",
        default=list(DEFAULT_VARIABLES),
        metavar="VARIABLE",
        help="variables de la colección que se descargan (por defecto: %(default)s)",
    )
    parser.add_argument(
        "--region",
        type=float,
        nargs=4,
        metavar=REGION_METAVAR,
        help="recorte en grados (por defecto: todo el globo)",
    )
    parser.add_argument(
        "--lat-stride",
        type=int,
        default=DEFAULT_STRIDE,
        help="se toma una de cada N latitudes, sin promediar (por defecto: %(default)s)",
    )
    parser.add_argument(
        "--lon-stride",
        type=int,
        default=DEFAULT_STRIDE,
        help="se toma una de cada N longitudes, sin promediar (por defecto: %(default)s)",
    )
    parser.add_argument(
        "--out", type=Path, default=DEFAULT_OUT, help="archivo NetCDF de salida (por defecto: %(default)s)"
    )
    parser.add_argument(
        "--url", default=DATASET_URL, help="colección OPeNDAP de origen (por defecto: %(default)s)"
    )
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    """Punto de entrada: lee los argumentos, descarga el episodio y lo guarda.

    Args:
        argv: Argumentos de la línea de comandos; sin ellos se usan los del proceso.

    Raises:
        SystemExit: Si los argumentos no son válidos o la descarga falla.
    """
    args = build_parser().parse_args(argv)
    configure_logging()
    try:
        download_episode(
            args.start,
            args.end,
            args.variables,
            args.out,
            region=region_from_bounds(args.region) if args.region else None,
            lat_stride=args.lat_stride,
            lon_stride=args.lon_stride,
            url=args.url,
        )
    except EXPECTED_ERRORS as exc:
        raise SystemExit(f"Error: {exc}") from exc
    print(f"Episodio guardado en {args.out}")


if __name__ == "__main__":
    main()
