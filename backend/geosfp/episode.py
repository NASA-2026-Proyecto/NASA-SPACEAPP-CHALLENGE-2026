"""Descarga de un episodio de GEOS-FP (varias variables en un tramo de tiempo) a NetCDF.

El archivo resultante es la entrada de `tools.build_scene`: una variable por especie
con dimensiones (step, lat, lon) y las marcas de tiempo en el atributo global
`time_stamps_utc`. Necesita el grupo de dependencias `pipeline`.
"""

import logging
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path

import numpy as np
import xarray as xr

from geosfp.client import DATASET_URL, dataset_window, load_series, open_remote
from geosfp.timeline import format_stamp
from geosfp.validation import require_valid

logger = logging.getLogger(__name__)

EPISODE_DIMS = ("step", "lat", "lon")


def episode_variable(name: str, data: xr.DataArray) -> xr.DataArray:
    """Valida una serie descargada y la prepara como variable del episodio.

    Args:
        name: Nombre de la variable, para el mensaje de error.
        data: Serie en memoria con dimensiones (time, lat, lon).

    Returns:
        La serie en float32 con dimensiones (step, lat, lon), sus coordenadas `lat`
        y `lon`, y el atributo `long_name`.

    Raises:
        ValueError: Si la serie tiene celdas sin dato (no finitas o de relleno).
    """
    values = data.values
    require_valid(name, values)
    return xr.DataArray(
        values.astype("float32"),
        dims=EPISODE_DIMS,
        coords={"lat": data["lat"].values, "lon": data["lon"].values},
        attrs={"long_name": str(data.attrs.get("long_name", "")).strip()},
    )


def build_episode(
    variables: Mapping[str, xr.DataArray],
    steps: Sequence[datetime],
    source_url: str = DATASET_URL,
    lat_stride: int = 1,
    lon_stride: int = 1,
) -> xr.Dataset:
    """Reúne las variables de un episodio en un dataset listo para guardar.

    Args:
        variables: Variables (step, lat, lon) por nombre; ver `episode_variable`.
        steps: Instantes UTC de los pasos; se guardan en `time_stamps_utc`.
        source_url: Colección de la que salen los datos.
        lat_stride: Salto de latitudes con que se submuestreó.
        lon_stride: Salto de longitudes con que se submuestreó.

    Returns:
        El dataset con las coordenadas `step`, `lat` y `lon` y los atributos de procedencia.

    Raises:
        ValueError: Si no hay variables, alguna no tiene un paso por cada instante o
            no comparten la misma malla.
    """
    if not variables:
        raise ValueError("Hace falta al menos una variable.")
    for name, variable in variables.items():
        if variable.sizes["step"] != len(steps):
            raise ValueError(f"{name}: trae {variable.sizes['step']} pasos, se esperaban {len(steps)}.")
    xr.align(*variables.values(), join="exact")  # falla si las mallas no coinciden
    grid = next(iter(variables.values()))
    return xr.Dataset(
        {name: variable.variable for name, variable in variables.items()},
        coords={"step": np.arange(len(steps)), "lat": grid["lat"].values, "lon": grid["lon"].values},
        attrs={
            "source_dataset": source_url,
            "product": "GEOS FP tavg3_2d_aer_Nx",
            "averaging": "3-hourly time average (GrADS step 180mn)",
            "units_note": "dimensionless (optical depth at 550 nm); not declared by server",
            "data_kind": "unverified",
            "subsampling": f"every {lat_stride}th lat and {lon_stride}th lon; values not averaged",
            "time_stamps_utc": ",".join(format_stamp(moment) for moment in steps),
        },
    )


def fetch_episode(
    ds: xr.Dataset,
    start: datetime,
    end: datetime,
    variables: Sequence[str],
    region: dict[str, slice] | None = None,
    lat_stride: int = 1,
    lon_stride: int = 1,
    source_url: str = DATASET_URL,
) -> xr.Dataset:
    """Descarga las variables de un episodio de una colección ya abierta.

    Cada variable se valida nada más descargarla, para no seguir bajando datos si
    alguna trae huecos.

    Args:
        ds: Colección remota (ver `geosfp.client.open_remote`).
        start: Comienzo del episodio (UTC).
        end: Final del episodio (UTC, incluido).
        variables: Nombres de las variables que se descargan.
        region: Recorte por coordenadas (`{"lat": slice, "lon": slice}`); sin él, todo el globo.
        lat_stride: Se toma una de cada `lat_stride` latitudes (sin promediar).
        lon_stride: Se toma una de cada `lon_stride` longitudes (sin promediar).
        source_url: Dirección de `ds`, para anotar la procedencia.

    Returns:
        El episodio en memoria (ver `build_episode`).

    Raises:
        ValueError: Si no se piden variables, el intervalo no está en la colección o
            alguna variable trae celdas sin dato.
        requests.exceptions.RequestException: Si una descarga agota sus reintentos.
    """
    if not variables:
        raise ValueError("Hace falta al menos una variable.")
    window = dataset_window(ds, start, end)
    loaded: dict[str, xr.DataArray] = {}
    for name in variables:
        logger.info("%s", name)
        series = load_series(ds, name, window, region, lat_stride, lon_stride)
        loaded[name] = episode_variable(name, series)
    return build_episode(loaded, window.steps, source_url, lat_stride, lon_stride)


def write_episode(episode: xr.Dataset, out_path: Path) -> None:
    """Guarda un episodio en NetCDF clásico (motor scipy), creando la carpeta si falta."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    episode.to_netcdf(out_path, engine="scipy")
    logger.info("Guardado en %s (%.1f MB)", out_path, out_path.stat().st_size / 1e6)


def download_episode(
    start: datetime,
    end: datetime,
    variables: Sequence[str],
    out_path: Path,
    region: dict[str, slice] | None = None,
    lat_stride: int = 1,
    lon_stride: int = 1,
    url: str = DATASET_URL,
) -> None:
    """Descarga un episodio de GEOS-FP y lo guarda en un NetCDF.

    Args:
        start: Comienzo del episodio (UTC).
        end: Final del episodio (UTC, incluido).
        variables: Nombres de las variables que se descargan.
        out_path: Archivo NetCDF de salida.
        region: Recorte por coordenadas (`{"lat": slice, "lon": slice}`); sin él, todo el globo.
        lat_stride: Se toma una de cada `lat_stride` latitudes (sin promediar).
        lon_stride: Se toma una de cada `lon_stride` longitudes (sin promediar).
        url: Dirección OPeNDAP de la colección.

    Raises:
        RuntimeError: Si no se puede abrir la colección.
        ValueError: Si los argumentos o los datos descargados no son válidos.
        requests.exceptions.RequestException: Si una descarga agota sus reintentos.
    """
    episode = fetch_episode(open_remote(url), start, end, variables, region, lat_stride, lon_stride, url)
    write_episode(episode, out_path)
