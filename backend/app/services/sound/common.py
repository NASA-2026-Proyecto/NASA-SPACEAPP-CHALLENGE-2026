"""Lo que comparten todos los sonidos: la muestra de un punto, direcciones y textos."""

from dataclasses import dataclass
from datetime import datetime

import numpy as np
import numpy.typing as npt

from app.services.sound.dsp import Signal

SECONDS = 12.0  # duración del sonido
TAIL = 3.0  # silencio al final para que la reverberación se apague
EARTH_RADIUS_KM = 6371.0

COMPASS = ("norte", "noreste", "este", "sureste", "sur", "suroeste", "oeste", "noroeste")
MONTHS = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")


@dataclass(frozen=True)
class PointSample:
    """Todo lo que un sonido necesita saber de un punto.

    Attributes:
        lat: Latitud del punto, grados norte.
        lon: Longitud del punto, grados este.
        value: El dato en el punto, en la unidad del fenómeno. NaN si no hay dato.
        bearings: Direcciones alrededor del punto, en grados desde el norte y en sentido
            horario.
        around: Valor medio en cada una de esas direcciones, a cierta distancia. Decide
            de qué lado llegan más granos (gotas, chasquidos, polvo).
        stamp: Instante del dato, como en los manifiestos (2026-11-14T21:30Z).
    """

    lat: float
    lon: float
    value: float
    bearings: Signal
    around: Signal
    stamp: str


@dataclass(frozen=True)
class Surroundings:
    """El entorno de un punto a lo largo de la serie: lo que necesita el sonido en tres dimensiones.

    Attributes:
        lat: Latitud del punto, grados norte.
        lon: Longitud del punto, grados este.
        bearing: Rumbo de cada celda del entorno desde el punto, en grados desde el norte
            y en sentido horario.
        km: Distancia de cada celda al punto; 0 es la celda del propio punto.
        values: El dato de cada celda en cada paso, con forma [paso, celda] y del paso
            más antiguo al más reciente. Donde la fuente no tiene dato vale 0.
        stamps: Instante de cada paso, como en los manifiestos (2026-11-14T21:30Z).
        far_km: Distancia hasta la que se leyó el entorno.
    """

    lat: float
    lon: float
    bearing: Signal
    km: Signal
    values: Signal
    stamps: tuple[str, ...]
    far_km: float


def compass(bearing_deg: float) -> str:
    """Nombre del punto cardinal más cercano de los ocho (0 = norte, sentido horario)."""
    return COMPASS[round(bearing_deg / 45) % 8]


def great_circle(
    lat: float, lon: float, bearing_deg: npt.ArrayLike, km: npt.ArrayLike
) -> tuple[Signal, Signal]:
    """Puntos a los que se llega desde (lat, lon) con esos rumbos y distancias.

    Returns:
        Latitudes y longitudes (de -180 a 180), con la forma combinada de los argumentos.
    """
    p1, l1 = np.radians(lat), np.radians(lon)
    th, d = np.radians(np.asarray(bearing_deg, float)), np.asarray(km, float) / EARTH_RADIUS_KM
    p2 = np.arcsin(np.sin(p1) * np.cos(d) + np.cos(p1) * np.sin(d) * np.cos(th))
    l2 = l1 + np.arctan2(np.sin(th) * np.sin(d) * np.cos(p1), np.cos(d) - np.sin(p1) * np.sin(p2))
    return np.degrees(p2), (np.degrees(l2) + 180) % 360 - 180


def direction_weights(around: Signal) -> Signal:
    """Probabilidad de que un grano llegue de cada dirección; suman 1.

    La mitad se reparte por igual y la otra mitad en proporción al dato de cada lado: el
    sonido rodea siempre al oyente, pero carga hacia donde hay más.
    """
    total = around.sum()
    share = around / total if total > 0 else np.full(len(around), 1 / len(around))
    weights: Signal = 0.5 / len(around) + 0.5 * share
    return weights


def fade_envelope(n_samples: int, sr: int) -> Signal:
    """Envolvente del sonido completo: entra en 1,5 s y se apaga antes de la cola."""
    t = np.arange(n_samples) / sr
    envelope: Signal = (np.clip(t / 1.5, 0, 1) * np.clip((SECONDS - t) / 2.5, 0, 1)) ** 1.5
    return envelope


def number(value: float, decimals: int = 1) -> str:
    """Un número como se escribe en español: con coma decimal y sin "-0"."""
    text = f"{value:.{decimals}f}"
    if float(text) == 0:
        text = text.lstrip("-")
    return text.replace(".", ",")


def describe_stamp(stamp: str) -> str:
    """Un instante de manifiesto (2026-11-14T21:30Z) dicho en palabras: 14 nov 2026, 21:30 UTC."""
    moment = datetime.strptime(stamp, "%Y-%m-%dT%H:%MZ")
    return f"{moment.day} {MONTHS[moment.month - 1]} {moment.year}, {moment:%H:%M} UTC"


def describe_journey(around: Surroundings) -> str:
    """Cómo se oye el sonido en tres dimensiones y qué tramo de la serie recorre."""
    return (
        "Sonido 3D para auriculares: el norte suena delante y arriba, el sur detrás y abajo, "
        "y lo lejano, más flojo y apagado. "
        f"Recorre los {len(around.stamps)} pasos de la serie, del {describe_stamp(around.stamps[0])} "
        f"al {describe_stamp(around.stamps[-1])}, y termina en el más reciente."
    )


def describe_place(around: Surroundings, cell: int) -> str:
    """Dónde queda una celda del entorno respecto al punto, en palabras."""
    if around.km[cell] == 0:
        return "en el propio punto"
    return f"a unos {number(float(around.km[cell]), 0)} km hacia el {compass(float(around.bearing[cell]))}"
