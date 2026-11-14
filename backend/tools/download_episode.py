from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import xarray as xr

from geosfp.client import (
    DATASET_URL,
    load_in_chunks,
    nearest_index,
    open_remote,
    time_axis,
)

START = datetime(2026, 7, 24, 1, 0, tzinfo=UTC)
END = datetime(2026, 7, 28, 23, 0, tzinfo=UTC)
VARIABLES = ["brexttau", "bcexttau", "duexttau", "suexttau", "ssexttau", "totexttau"]
EUROPE = {"lat": slice(35.0, 60.0), "lon": slice(-15.0, 20.0)}
FILL_LIMIT = 1.0e14
OUT = Path("data/raw/geosfp_aer_europe_20260724_20260728.nc")


def main() -> None:
    ds = open_remote()
    times = time_axis(ds["time"].attrs, ds.sizes["time"])
    first, last = nearest_index(times, START), nearest_index(times, END)
    steps = times[first : last + 1]
    print(f"Pasos: {len(steps)} | {steps[0]:%Y-%m-%d %H:%M} -> {steps[-1]:%Y-%m-%d %H:%M} UTC")

    arrays, lat, lon = {}, None, None
    for name in VARIABLES:
        print(f"\n{name}")
        data = load_in_chunks(ds[name].isel(time=slice(first, last + 1)).sel(EUROPE))
        values = data.values
        if not np.isfinite(values).all() or (values >= FILL_LIMIT).any():
            raise SystemExit(f"{name}: contiene valores no válidos.")
        arrays[name] = (
            ("step", "lat", "lon"),
            values.astype("float32"),
            {"long_name": str(ds[name].attrs.get("long_name", "")).strip()},
        )
        lat, lon = data["lat"].values, data["lon"].values

    dataset = xr.Dataset(
        arrays,
        coords={"step": np.arange(len(steps)), "lat": lat, "lon": lon},
        attrs={
            "source_dataset": DATASET_URL,
            "product": "GEOS FP tavg3_2d_aer_Nx",
            "averaging": "3-hourly time average (GrADS step 180mn)",
            "units_note": "dimensionless (optical depth at 550 nm); not declared by server",
            "data_kind": "unverified",
            "time_stamps_utc": ",".join(f"{moment:%Y-%m-%dT%H:%M}Z" for moment in steps),
        },
    )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    dataset.to_netcdf(OUT, engine="scipy")
    print(f"\nGuardado en {OUT} ({OUT.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
