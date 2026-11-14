from datetime import datetime, timedelta, timezone

import time 
import requests
import xarray as xr

DATASET_URL = ("https://opendap.nccs.nasa.gov/dods/GEOS-5/fp/0.25_deg/seamless/"
               "tavg3_2d_aer_Nx/tavg3_2d_aer_Nx.20261101_00")


def open_remote(url: str = DATASET_URL) -> xr.Dataset:
    for candidate in (url.replace("https://", "dap2://", 1), url):
        try:
            return xr.open_dataset(candidate, engine="pydap", decode_times=False)
        except Exception as exc:
            print(f"Falló {candidate}: {type(exc).__name__}: {exc}")
    raise RuntimeError(f"No se pudo abrir {url}")


def time_axis(attrs: dict, size: int) -> list[datetime]:
    start = datetime.strptime(attrs["grads_min"], "%H:%Mz%d%b%Y").replace(tzinfo=timezone.utc)
    step = int(attrs["grads_step"].removesuffix("mn"))
    return [start + timedelta(minutes=step * i) for i in range(size)]


def nearest_index(times: list[datetime], target: datetime) -> int:
    return min(range(len(times)), key=lambda i: abs(times[i] - target))

def load_with_retry(array: xr.DataArray, attempts: int = 5, delay: float = 3.0) -> xr.DataArray:
    for attempt in range(1, attempts + 1):
        try:
            return array.load()
        except requests.exceptions.RequestException as exc:
            if attempt == attempts:
                raise
            wait = delay * 2 ** (attempt - 1)
            print(f"  intento {attempt}/{attempts} falló ({type(exc).__name__}); "
                  f"reintento en {wait:.0f} s")
            time.sleep(wait)
    raise RuntimeError("Sin resultado tras los reintentos.")

def load_in_chunks(array: xr.DataArray, dim: str = "time", size: int = 8,
                   attempts: int = 5, delay: float = 3.0, pause: float = 0.5) -> xr.DataArray:
    total = array.sizes[dim]
    parts = []
    for start in range(0, total, size):
        stop = min(start + size, total)
        print(f"  {dim}: pasos {start}-{stop - 1} de {total - 1}")
        parts.append(load_with_retry(array.isel({dim: slice(start, stop)}), attempts, delay))
        time.sleep(pause)
    return xr.concat(parts, dim=dim)

def load_snapshot(ds: xr.Dataset, names: list[str], index: int,
                  attempts: int = 5, delay: float = 3.0) -> xr.Dataset:
    arrays = {}
    for name in names:
        arrays[name] = load_with_retry(ds[name].isel(time=index), attempts, delay)
        print(f"  {name}: descargada")
    return xr.Dataset(arrays)