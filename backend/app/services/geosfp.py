"""Cliente mínimo de GEOS-FP (NASA GMAO) por OPeNDAP, sin clave.

Solo usa la biblioteca estándar y numpy: pide los metadatos (.das) y las matrices en
binario (.dods). El servidor responde a veces con 502/504, de ahí los reintentos.
"""

import re
import struct
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import quote

import numpy as np

from app.services.http import http_get

# Análisis ("assim") de aerosoles: medias de 3 h en una malla de 0,25° x 0,3125°
DATASET_URL = "https://opendap.nccs.nasa.gov/dods/GEOS-5/fp/0.25_deg/assim/tavg3_2d_aer_Nx"
FILL_LIMIT = 1.0e14  # el servidor marca los huecos con 1e15

_STEP_UNITS = {"mn": "minutes", "hr": "hours", "dy": "days"}


@dataclass(frozen=True)
class Grid:
    """Malla regular lat/lon y eje de tiempo de una colección."""

    lat_min: float
    lat_step: float
    n_lat: int
    lon_min: float
    lon_step: float
    n_lon: int
    time_start: datetime
    time_step: timedelta
    n_times: int

    def time_at(self, index: int) -> datetime:
        return self.time_start + index * self.time_step


def _das_block(das: str, name: str) -> dict[str, str]:
    match = re.search(rf"\n    {name} \{{(.*?)\n    \}}", das, re.S)
    if match is None:
        raise ValueError(f"El DAS no tiene el bloque '{name}'.")
    return dict(re.findall(r'\w+ (\w+) "?([^";]*)"?;', match.group(1)))


def parse_das(das: str) -> Grid:
    lat, lon, axis = (_das_block(das, name) for name in ("lat", "lon", "time"))
    step = re.fullmatch(r"(\d+)(mn|hr|dy)", axis["grads_step"])
    if step is None:
        raise ValueError(f"Paso de tiempo desconocido: {axis['grads_step']!r}")
    return Grid(
        lat_min=float(lat["minimum"]),
        lat_step=float(lat["resolution"]),
        n_lat=int(lat["grads_size"]),
        lon_min=float(lon["minimum"]),
        lon_step=float(lon["resolution"]),
        n_lon=int(lon["grads_size"]),
        time_start=datetime.strptime(axis["grads_min"], "%H:%Mz%d%b%Y").replace(tzinfo=UTC),
        time_step=timedelta(**{_STEP_UNITS[step.group(2)]: int(step.group(1))}),
        n_times=int(axis["grads_size"]),
    )


def parse_dods(body: bytes, shape: tuple[int, ...]) -> np.ndarray:
    """Extrae la matriz float32 de una respuesta .dods con una sola variable.

    Tras la cabecera de texto viene "Data:" y la matriz en XDR: su longitud dos veces
    (enteros big-endian) y los valores float32 big-endian. Los ejes que siguen se ignoran.
    """
    marker = b"\nData:\n"
    start = body.find(marker)
    if start < 0:
        raise ValueError("Respuesta .dods sin sección de datos.")
    start += len(marker)
    count = int(np.prod(shape))
    declared = struct.unpack_from(">II", body, start)
    if declared != (count, count):
        raise ValueError(f"La matriz trae {declared[0]} valores, se esperaban {count}.")
    values = np.frombuffer(body, dtype=">f4", count=count, offset=start + 8)
    return values.reshape(shape).astype("<f4")


class GeosFpClient:
    def __init__(self, url: str = DATASET_URL, get: Callable[[str], bytes] = http_get) -> None:
        self._url = url
        self._get = get

    @property
    def url(self) -> str:
        return self._url

    def grid(self) -> Grid:
        """Malla y eje de tiempo actuales (el eje crece con cada paso nuevo del modelo)."""
        return parse_das(self._get(f"{self._url}.das").decode())

    def fields(self, variable: str, grid: Grid, first: int, last: int, stride: int) -> np.ndarray:
        """Una variable en todo el globo para los pasos first..last, 1 de cada `stride` celdas.

        Devuelve float32 con forma (pasos, latitudes, longitudes): sur a norte, oeste a este.
        """
        query = f"{variable}[{first}:{last}][0:{stride}:{grid.n_lat - 1}][0:{stride}:{grid.n_lon - 1}]"
        shape = (
            last - first + 1,
            len(range(0, grid.n_lat, stride)),
            len(range(0, grid.n_lon, stride)),
        )
        return parse_dods(self._get(f"{self._url}.dods?{quote(query, safe=':,')}"), shape)
