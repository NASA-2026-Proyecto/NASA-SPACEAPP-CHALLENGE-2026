import sys
from datetime import datetime, timedelta, timezone

import numpy as np
import xarray as xr

BASE = ("https://opendap.nccs.nasa.gov/dods/GEOS-5/fp/0.25_deg/seamless/"
        "tavg3_2d_aer_Nx/tavg3_2d_aer_Nx.20261101_00")
TARGET = datetime(2026, 11, 1, 4, 30, tzinfo=timezone.utc)
SPECIES = ["bcexttau", "duexttau", "ssexttau", "suexttau", "totexttau"]
FILL_LIMIT = 1.0e14


def open_remote(url: str) -> xr.Dataset:
    for candidate in (url.replace("https://", "dap2://", 1), url):
        try:
            print(f"Intentando abrir: {candidate}")
            return xr.open_dataset(candidate, engine="pydap", decode_times=False)
        except Exception as exc:
            print(f"  Falló: {type(exc).__name__}: {exc}")
    raise SystemExit("No se pudo abrir el dataset.")


def grads_time_axis(attrs: dict, size: int) -> list[datetime]:
    start = datetime.strptime(attrs["grads_min"], "%H:%Mz%d%b%Y").replace(tzinfo=timezone.utc)
    minutes = int(attrs["grads_step"].removesuffix("mn"))
    return [start + timedelta(minutes=minutes * i) for i in range(size)]


def main(url: str) -> None:
    ds = open_remote(url)
    times = grads_time_axis(ds["time"].attrs, ds.sizes["time"])
    print(f"\nPrimer paso: {times[0]:%Y-%m-%d %H:%M} UTC")
    print(f"Último paso: {times[-1]:%Y-%m-%d %H:%M} UTC")

    index = min(range(len(times)), key=lambda i: abs(times[i] - TARGET))
    print(f"\nPaso elegido: índice {index} -> {times[index]:%Y-%m-%d %H:%M} UTC")

    snapshot = ds.isel(time=index)
    for name in SPECIES:
        values = np.asarray(snapshot[name].values, dtype="float64")
        valid = values[np.isfinite(values) & (values < FILL_LIMIT)]
        print(f"\n{name} ({snapshot[name].attrs.get('long_name', '').strip()})")
        print(f"  celdas: {values.size} | válidas: {valid.size} | ausentes: {values.size - valid.size}")
        if valid.size:
            print(f"  min={valid.min():.4g}  p50={np.percentile(valid, 50):.4g}  "
                  f"p99={np.percentile(valid, 99):.4g}  max={valid.max():.4g}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else BASE)