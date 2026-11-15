"""Acceso remoto a GEOS-FP (NASA GMAO) por OPeNDAP con xarray + pydap.

Abre la colección sin descargarla y baja solo los trozos que se piden. El servidor
falla a ratos (502/504, cortes de conexión), así que las descargas se hacen en
bloques pequeños y con reintentos. Necesita el grupo de dependencias `pipeline`.
"""

import logging
import time
from datetime import datetime

import requests
import xarray as xr

from geosfp.timeline import TimeWindow, select_window, time_axis

logger = logging.getLogger(__name__)

# Aerosoles de GEOS-FP en medias de 3 h (tavg3_2d_aer_Nx), colección "seamless" del 2026-11-01 00z
DATASET_URL = (
    "https://opendap.nccs.nasa.gov/dods/GEOS-5/fp/0.25_deg/seamless/"
    "tavg3_2d_aer_Nx/tavg3_2d_aer_Nx.20261101_00"
)


def open_remote(url: str = DATASET_URL) -> xr.Dataset:
    """Abre una colección OPeNDAP sin descargar sus datos.

    Prueba primero el esquema `dap2://`, que le indica a pydap el protocolo, y
    después la URL tal cual.

    Args:
        url: Dirección https de la colección.

    Returns:
        El dataset remoto, con el eje de tiempo sin decodificar.

    Raises:
        RuntimeError: Si no se puede abrir de ninguna de las dos formas.
    """
    error: Exception | None = None
    for candidate in (url.replace("https://", "dap2://", 1), url):
        try:
            return xr.open_dataset(candidate, engine="pydap", decode_times=False)
        except Exception as exc:  # pydap falla con errores muy distintos según el caso
            logger.warning("Falló %s: %s: %s", candidate, type(exc).__name__, exc)
            error = exc
    raise RuntimeError(f"No se pudo abrir {url}") from error


def dataset_window(ds: xr.Dataset, start: datetime, end: datetime) -> TimeWindow:
    """Elige los pasos de tiempo de una colección que cubren `start`..`end`.

    Args:
        ds: Colección con una coordenada `time` descrita al estilo GrADS.
        start: Comienzo del intervalo (UTC).
        end: Final del intervalo (UTC, incluido).

    Returns:
        El tramo del eje de tiempo entre los pasos más cercanos a cada extremo.

    Raises:
        ValueError: Si el eje no se entiende o no contiene el intervalo.
    """
    window = select_window(time_axis(ds["time"].attrs, ds.sizes["time"]), start, end)
    logger.info(
        "Pasos: %d | %s -> %s UTC",
        len(window.steps),
        window.steps[0].strftime("%Y-%m-%d %H:%M"),
        window.steps[-1].strftime("%Y-%m-%d %H:%M"),
    )
    return window


def plan_chunks(total: int, size: int) -> list[slice]:
    """Reparte `total` pasos en bloques consecutivos de `size` (el último, lo que quede).

    Raises:
        ValueError: Si `total` es negativo o `size` no es positivo.
    """
    if total < 0 or size < 1:
        raise ValueError(f"No se pueden repartir {total} pasos en bloques de {size}.")
    return [slice(start, min(start + size, total)) for start in range(0, total, size)]


def load_with_retry(array: xr.DataArray, attempts: int = 5, delay: float = 3.0) -> xr.DataArray:
    """Descarga los valores de una matriz remota, reintentando los fallos de red.

    Args:
        array: Matriz perezosa; se carga en memoria.
        attempts: Intentos en total antes de dejar pasar el error.
        delay: Segundos de espera tras el primer fallo; se duplica en cada reintento.

    Returns:
        La misma matriz, ya con los valores en memoria.

    Raises:
        ValueError: Si `attempts` es menor que 1.
        requests.exceptions.RequestException: Si todos los intentos fallan.
    """
    if attempts < 1:
        raise ValueError("Hace falta al menos un intento.")
    for attempt in range(1, attempts):
        try:
            return array.load()
        except requests.exceptions.RequestException as exc:
            wait = delay * 2 ** (attempt - 1)
            logger.warning(
                "  intento %d/%d falló (%s); reintento en %.0f s", attempt, attempts, type(exc).__name__, wait
            )
            time.sleep(wait)
    # Último intento: si falla, el error llega tal cual a quien llama
    return array.load()


def load_in_chunks(
    array: xr.DataArray,
    dim: str = "time",
    size: int = 8,
    attempts: int = 5,
    delay: float = 3.0,
    pause: float = 0.5,
) -> xr.DataArray:
    """Descarga una matriz remota por bloques a lo largo de una dimensión.

    Args:
        array: Matriz perezosa.
        dim: Dimensión que se trocea.
        size: Pasos por bloque.
        attempts: Intentos por bloque (ver `load_with_retry`).
        delay: Espera inicial entre reintentos, en segundos.
        pause: Segundos de pausa tras cada bloque, para no saturar al servidor.

    Returns:
        La matriz completa en memoria, con los bloques unidos en orden.

    Raises:
        ValueError: Si la matriz no tiene pasos en `dim` o `size` no es positivo.
        requests.exceptions.RequestException: Si un bloque agota sus reintentos.
    """
    total = array.sizes[dim]
    chunks = plan_chunks(total, size)
    if not chunks:
        raise ValueError(f"No hay nada que descargar: la dimensión '{dim}' está vacía.")
    parts: list[xr.DataArray] = []
    for chunk in chunks:
        logger.info("  %s: pasos %d-%d de %d", dim, chunk.start, chunk.stop - 1, total - 1)
        parts.append(load_with_retry(array.isel({dim: chunk}), attempts, delay))
        time.sleep(pause)
    return xr.concat(parts, dim=dim)


def load_series(
    ds: xr.Dataset,
    name: str,
    window: TimeWindow,
    region: dict[str, slice] | None = None,
    lat_stride: int = 1,
    lon_stride: int = 1,
) -> xr.DataArray:
    """Descarga la serie temporal de una variable, recortada y submuestreada.

    Args:
        ds: Colección remota.
        name: Nombre de la variable.
        window: Pasos de tiempo que se quieren.
        region: Recorte por coordenadas, p. ej.
            `{"lat": slice(35.0, 60.0), "lon": slice(-15.0, 20.0)}`. Sin recorte, todo el globo.
        lat_stride: Se toma una de cada `lat_stride` latitudes (sin promediar).
        lon_stride: Se toma una de cada `lon_stride` longitudes (sin promediar).

    Returns:
        La serie en memoria, con dimensiones (time, lat, lon).

    Raises:
        ValueError: Si algún salto de malla no es positivo o el recorte no contiene
            ninguna celda de la malla.
        requests.exceptions.RequestException: Si un bloque agota sus reintentos.
    """
    if lat_stride < 1 or lon_stride < 1:
        raise ValueError("Los saltos de malla (lat_stride, lon_stride) deben ser al menos 1.")
    selection = ds[name].isel(
        time=window.index,
        lat=slice(None, None, lat_stride),
        lon=slice(None, None, lon_stride),
    )
    if region:
        selection = selection.sel(region)
    if selection.size == 0:
        raise ValueError(f"{name}: el recorte {dict(selection.sizes)} no contiene ninguna celda.")
    return load_in_chunks(selection)
