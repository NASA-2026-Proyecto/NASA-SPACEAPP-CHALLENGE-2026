"""Resume por día el CSV de estadísticas que escribe `tools.find_episode`.

Muestra, para cada fecha (UTC), la media diaria de la zona de interés y los máximos
del día en la zona de interés y en la región amplia. No usa la red ni necesita el
grupo de dependencias `pipeline`.

Uso, desde backend/:

    uv run python -m tools.summarize_episode
    uv run python -m tools.summarize_episode --source data/processed/episodes/brexttau_europe_2026-07.csv
    uv run python -m tools.summarize_episode --help
"""

import argparse
from collections.abc import Iterable, Sequence
from pathlib import Path

from geosfp.cli import EXPECTED_ERRORS
from geosfp.stats import DaySummary, read_stats_csv, summarize_by_day

DEFAULT_SOURCE = Path("data/processed/episodes/brexttau_europe_2026-07.csv")
TABLE_HEADER = "fecha        media_iberia  max_iberia  max_europa"


def format_table(summaries: Iterable[DaySummary]) -> list[str]:
    """Líneas de la tabla: la cabecera y una fila por día."""
    return [TABLE_HEADER] + [
        f"{day.day}   {day.iberia_mean:11.4f}  {day.iberia_max:10.3f}  {day.europe_max:10.3f}"
        for day in summaries
    ]


def build_parser() -> argparse.ArgumentParser:
    """Define los argumentos de la línea de comandos."""
    parser = argparse.ArgumentParser(
        description="Resume por día el CSV de estadísticas de tools.find_episode."
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=DEFAULT_SOURCE,
        help="CSV escrito por tools.find_episode (por defecto: %(default)s)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    """Punto de entrada: lee el CSV y muestra la tabla por día.

    Args:
        argv: Argumentos de la línea de comandos; sin ellos se usan los del proceso.

    Raises:
        SystemExit: Si los argumentos no son válidos o el CSV no se puede leer.
    """
    args = build_parser().parse_args(argv)
    try:
        summaries = summarize_by_day(read_stats_csv(args.source))
    except EXPECTED_ERRORS as exc:
        raise SystemExit(f"Error: {exc}") from exc
    print("\n".join(format_table(summaries)))


if __name__ == "__main__":
    main()
