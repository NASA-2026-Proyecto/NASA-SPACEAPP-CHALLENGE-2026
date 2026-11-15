from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from geosfp.client import (
    DATASET_URL,
    load_snapshot,
    nearest_index,
    open_remote,
    time_axis,
)

TARGET = datetime(2026, 11, 1, 4, 30, tzinfo=UTC)
SAVED = ["bcexttau", "duexttau", "ssexttau", "suexttau", "totexttau"]
EXTRA = ["ocexttau", "brexttau", "niexttau"]
WITH_BR = ["bcexttau", "ocexttau", "brexttau", "niexttau", "duexttau", "ssexttau", "suexttau"]
WITHOUT_BR = [name for name in WITH_BR if name != "brexttau"]
LAT, LON = (34.0, 46.0), (-12.0, 6.0)
OUT = Path("data/raw/geosfp_aer_iberia_20261101T0430Z.nc")


def closure(snapshot, names: list[str]) -> np.ndarray:
    parts = sum(snapshot[name].values.astype("float64") for name in names)
    return snapshot["totexttau"].values.astype("float64") - parts


def report(label: str, diff: np.ndarray) -> None:
    print(f"  {label}: |dif| máx={np.abs(diff).max():.4g}  media={diff.mean():.4g}")


def main() -> None:
    ds = open_remote()
    times = time_axis(ds["time"].attrs, ds.sizes["time"])
    index = nearest_index(times, TARGET)
    print(f"Instante: {times[index]:%Y-%m-%d %H:%M} UTC (índice {index})\nDescargando:")

    snapshot = load_snapshot(ds, SAVED + EXTRA, index)

    print("\nCierre: total - suma de especies")
    report("con br ", closure(snapshot, WITH_BR))
    report("sin br ", closure(snapshot, WITHOUT_BR))

    region = snapshot[SAVED].sel(lat=slice(*LAT), lon=slice(*LON))
    region.attrs = {
        "source_dataset": DATASET_URL,
        "product": "GEOS FP tavg3_2d_aer_Nx",
        "time_stamp_utc": f"{times[index]:%Y-%m-%dT%H:%M}Z",
        "averaging": "3-hourly time average (GrADS step 180mn)",
        "units_note": "dimensionless (optical depth); not declared by server",
        "data_kind": "unverified",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    region.to_netcdf(OUT, engine="scipy")
    print(f"\nRecorte {dict(region.sizes)} guardado en {OUT}")


if __name__ == "__main__":
    main()
