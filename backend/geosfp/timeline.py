"""Eje de tiempo de una colección GrADS/OPeNDAP: cálculo puro, sin red ni xarray.

El servidor describe el eje con dos atributos de texto: el primer instante
(`grads_min`, p. ej. "01:30z24jul2026") y el paso (`grads_step`, p. ej. "180mn").
Aquí se convierten en instantes UTC y se elige el tramo que cubre un episodio.
"""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

STAMP_FORMAT = "%Y-%m-%dT%H:%MZ"

_GRADS_START_FORMAT = "%H:%Mz%d%b%Y"
_STEP_PATTERN = re.compile(r"(\d+)(mn|hr|dy)")
_STEP_UNITS = {"mn": "minutes", "hr": "hours", "dy": "days"}


@dataclass(frozen=True)
class TimeWindow:
    """Tramo contiguo del eje de tiempo de una colección.

    Attributes:
        first: Índice del primer paso del tramo.
        last: Índice del último paso del tramo (incluido).
        steps: Instantes UTC de los pasos `first`..`last`.
    """

    first: int
    last: int
    steps: tuple[datetime, ...]

    @property
    def index(self) -> slice:
        """Rebanada que selecciona el tramo en el eje de tiempo."""
        return slice(self.first, self.last + 1)


def step_duration(grads_step: str) -> timedelta:
    """Convierte un paso de tiempo de GrADS en una duración.

    Args:
        grads_step: Número entero seguido de la unidad: "mn" (minutos), "hr" (horas)
            o "dy" (días). Por ejemplo "180mn", "3hr" o "1dy".

    Returns:
        La duración de un paso.

    Raises:
        ValueError: Si el texto no tiene esa forma, la unidad es otra o el paso es cero.
    """
    match = _STEP_PATTERN.fullmatch(grads_step)
    if match is None:
        raise ValueError(
            f"Paso de tiempo desconocido: {grads_step!r} (se esperaba p. ej. '180mn', '3hr', '1dy')."
        )
    duration = timedelta(**{_STEP_UNITS[match.group(2)]: int(match.group(1))})
    if not duration:
        raise ValueError(f"El paso de tiempo no puede ser cero: {grads_step!r}.")
    return duration


def time_axis(attrs: Mapping[str, str], size: int) -> list[datetime]:
    """Calcula los instantes UTC del eje de tiempo de una colección.

    Args:
        attrs: Atributos de la coordenada `time`; se leen `grads_min` y `grads_step`.
        size: Número de pasos del eje.

    Returns:
        Un instante por paso, en orden creciente.

    Raises:
        KeyError: Si falta alguno de los dos atributos.
        ValueError: Si `grads_min` o `grads_step` no se entienden.
    """
    start = datetime.strptime(attrs["grads_min"], _GRADS_START_FORMAT).replace(tzinfo=UTC)
    step = step_duration(attrs["grads_step"])
    return [start + step * i for i in range(size)]


def nearest_index(times: Sequence[datetime], target: datetime) -> int:
    """Índice del instante más cercano a `target` (el primero, si hay empate).

    Raises:
        ValueError: Si `times` está vacío.
    """
    if not times:
        raise ValueError("El eje de tiempo está vacío.")
    return min(range(len(times)), key=lambda i: abs(times[i] - target))


def select_window(times: Sequence[datetime], start: datetime, end: datetime) -> TimeWindow:
    """Elige los pasos del eje que cubren el intervalo `start`..`end`.

    Cada extremo se ajusta al paso más cercano, así que no hace falta pedir la hora
    exacta de un paso.

    Args:
        times: Eje de tiempo completo, en orden creciente.
        start: Comienzo del intervalo.
        end: Final del intervalo (incluido).

    Returns:
        El tramo del eje entre los pasos más cercanos a `start` y a `end`.

    Raises:
        ValueError: Si el eje está vacío, si `end` es anterior a `start` o si algún
            extremo queda a más de un paso de distancia del eje (el servidor no
            tiene esas fechas).
    """
    if not times:
        raise ValueError("El eje de tiempo está vacío.")
    if end < start:
        raise ValueError(f"El final ({format_stamp(end)}) es anterior al comienzo ({format_stamp(start)}).")
    if len(times) > 1:
        margin = times[1] - times[0]
        if start < times[0] - margin or end > times[-1] + margin:
            raise ValueError(
                f"El intervalo pedido ({format_stamp(start)} a {format_stamp(end)}) se sale del eje de "
                f"tiempo disponible ({format_stamp(times[0])} a {format_stamp(times[-1])})."
            )
    first, last = nearest_index(times, start), nearest_index(times, end)
    return TimeWindow(first, last, tuple(times[first : last + 1]))


def format_stamp(moment: datetime) -> str:
    """Marca de tiempo UTC al minuto, como "2026-07-24T01:30Z".

    Es el formato de `time_stamps_utc` en los NetCDF y de `time_utc` en los CSV.
    """
    return moment.strftime(STAMP_FORMAT)
