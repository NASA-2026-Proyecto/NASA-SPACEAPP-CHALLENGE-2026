from datetime import datetime
from pathlib import Path

import numpy as np
import xarray as xr

from geosfp.client import DATASET_URL, load_in_chunks, nearest_index, open_remote, time_axis

FILL_LIMIT = 1.0e14


def download_episode(
    start: datetime,
    end: datetime,
    variables: list[str],
    out_path: Path,
    region: dict | None = None,
    lat_stride: int = 1,
    lon_stride: int = 1,
) -> None:
    ds = open_remote()
    times = time_axis(ds["time"].attrs, ds.sizes["time"])
    first, last = nearest_index(times, start), nearest_index(times, end)
    steps = times[first : last + 1]
    print(f"Pasos: {len(steps)} | {steps[0]:%Y-%m-%d %H:%M} -> {steps[-1]:%Y-%m-%d %H:%M} UTC")

    arrays, lat, lon = {}, None, None
    for name in variables:
        print(f"\n{name}")
        selection = ds[name].isel(
            time=slice(first, last + 1),
            lat=slice(None, None, lat_stride),
            lon=slice(None, None, lon_stride),
        )
        if region:
            selection = selection.sel(region)
        data = load_in_chunks(selection)
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
            "subsampling": f"every {lat_stride}th lat and {lon_stride}th lon; values not averaged",
            "time_stamps_utc": ",".join(f"{moment:%Y-%m-%dT%H:%M}Z" for moment in steps),
        },
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    dataset.to_netcdf(out_path, engine="scipy")
    print(f"\nGuardado en {out_path} ({out_path.stat().st_size / 1e6:.1f} MB)")
