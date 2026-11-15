"""Estadísticas por paso de un episodio y su tabla CSV (cálculo puro y lectura/escritura).

`tools.find_episode` calcula una fila por paso de tiempo y la guarda en un CSV;
`tools.summarize_episode` lee ese CSV y lo resume por día. Los nombres de las columnas
vienen del estudio original (humo sobre Europa, con la península ibérica como zona
de interés) y se mantienen aunque se elijan otras regiones.
"""

import csv
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass, fields
from datetime import datetime
from pathlib import Path

import numpy as np
import numpy.typing as npt

from geosfp.timeline import format_stamp


@dataclass(frozen=True)
class StepStats:
    """Estadísticas de un paso de tiempo; cada atributo es una columna del CSV.

    Attributes:
        time_utc: Marca de tiempo del paso, como "2026-07-24T01:30Z".
        europe_max: Máximo en la región amplia.
        iberia_mean: Media en la zona de interés.
        iberia_max: Máximo en la zona de interés.
    """

    time_utc: str
    europe_max: float
    iberia_mean: float
    iberia_max: float


@dataclass(frozen=True)
class DaySummary:
    """Resumen de los pasos de un mismo día (UTC).

    Attributes:
        day: Fecha, como "2026-07-24".
        iberia_mean: Media de las medias de la zona de interés.
        iberia_max: Máximo del día en la zona de interés.
        europe_max: Máximo del día en la región amplia.
    """

    day: str
    iberia_mean: float
    iberia_max: float
    europe_max: float


CSV_FIELDS: tuple[str, ...] = tuple(field.name for field in fields(StepStats))


def step_statistics(
    steps: Sequence[datetime],
    region: npt.NDArray[np.floating],
    focus: npt.NDArray[np.floating],
) -> list[StepStats]:
    """Calcula las estadísticas de cada paso de tiempo.

    Args:
        steps: Instantes UTC de los pasos.
        region: Valores de la región amplia, con forma (pasos, lat, lon).
        focus: Valores de la zona de interés, con forma (pasos, lat, lon).

    Returns:
        Una fila por paso, en el mismo orden que `steps`.

    Raises:
        ValueError: Si el número de pasos no coincide con las matrices o si alguna
            de las dos zonas no tiene celdas.
    """
    if not len(steps) == region.shape[0] == focus.shape[0]:
        raise ValueError(
            f"Hay {len(steps)} pasos, pero las matrices traen {region.shape[0]} y {focus.shape[0]}."
        )
    if steps and (region[0].size == 0 or focus[0].size == 0):
        raise ValueError("La región o la zona de interés no contiene ninguna celda de la malla.")
    wide, inner = region.astype("float64"), focus.astype("float64")
    return [
        StepStats(
            time_utc=format_stamp(moment),
            europe_max=float(wide[i].max()),
            iberia_mean=float(inner[i].mean()),
            iberia_max=float(inner[i].max()),
        )
        for i, moment in enumerate(steps)
    ]


def top_steps(rows: Iterable[StepStats], count: int) -> list[StepStats]:
    """Los `count` pasos con mayor media en la zona de interés, de mayor a menor."""
    return sorted(rows, key=lambda row: row.iberia_mean, reverse=True)[:count]


def write_stats_csv(rows: Iterable[StepStats], path: Path) -> None:
    """Guarda las filas en un CSV con cabecera (columnas `CSV_FIELDS`), creando la carpeta."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(asdict(row) for row in rows)


def read_stats_csv(path: Path) -> list[StepStats]:
    """Lee un CSV escrito por `write_stats_csv`.

    Raises:
        ValueError: Si al archivo le falta alguna de las columnas `CSV_FIELDS` o un
            valor no es numérico.
    """
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        missing = set(CSV_FIELDS) - set(reader.fieldnames or ())
        if missing:
            raise ValueError(f"{path}: faltan las columnas {', '.join(sorted(missing))}.")
        return [
            StepStats(
                time_utc=row["time_utc"],
                europe_max=float(row["europe_max"]),
                iberia_mean=float(row["iberia_mean"]),
                iberia_max=float(row["iberia_max"]),
            )
            for row in reader
        ]


def summarize_by_day(rows: Iterable[StepStats]) -> list[DaySummary]:
    """Agrupa las filas por día (UTC) y resume cada grupo, en orden de fecha."""
    days: defaultdict[str, list[StepStats]] = defaultdict(list)
    for row in rows:
        days[row.time_utc[:10]].append(row)
    return [
        DaySummary(
            day=day,
            iberia_mean=sum(row.iberia_mean for row in group) / len(group),
            iberia_max=max(row.iberia_max for row in group),
            europe_max=max(row.europe_max for row in group),
        )
        for day, group in sorted(days.items())
    ]
