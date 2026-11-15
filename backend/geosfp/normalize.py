import json
from pathlib import Path

import numpy as np
import xarray as xr

from geosfp.grid import regular_step

SPECIES = {
    "bcexttau": ("black_carbon", "Black Carbon"),
    "duexttau": ("dust", "Dust"),
    "ssexttau": ("sea_salt", "Sea Salt"),
    "suexttau": ("sulfate", "Sulfate"),
    "totexttau": ("total", "Total aerosol"),
}
SIGNIFICANT_DIGITS = 5
SCHEMA_VERSION = 1


def _validate(variable: str, values: np.ndarray, shape: tuple[int, int]) -> None:
    if values.shape != shape:
        raise ValueError(f"{variable}: forma {values.shape}, se esperaba {shape}.")
    if not np.isfinite(values).all():
        raise ValueError(f"{variable}: contiene valores no finitos.")
    if (values < 0).any():
        raise ValueError(f"{variable}: contiene valores negativos.")


def _round(values: np.ndarray) -> list[float]:
    return [float(f"{value:.{SIGNIFICANT_DIGITS}g}") for value in values.ravel()]


def normalize(source: Path, destination: Path) -> dict:
    with xr.open_dataset(source, engine="scipy", decode_times=False) as ds:
        lat = ds["lat"].values
        lon = ds["lon"].values
        shape = (lat.size, lon.size)
        grid = {
            "lat_min": float(lat[0]),
            "lat_step": regular_step(lat, "lat"),
            "lon_min": float(lon[0]),
            "lon_step": regular_step(lon, "lon"),
            "n_lat": int(lat.size),
            "n_lon": int(lon.size),
            "order": "row-major; rows south to north, columns west to east",
        }
        species = {}
        for variable, (key, label) in SPECIES.items():
            values = ds[variable].values.astype("float64")
            _validate(variable, values, shape)
            species[key] = {
                "source_variable": variable,
                "label": label,
                "long_name": str(ds[variable].attrs.get("long_name", "")).strip(),
                "unit": "dimensionless",
                "unit_source": "documented: optical depth is dimensionless; not declared by server",
                "min": float(values.min()),
                "max": float(values.max()),
                "values": _round(values),
            }
        document = {
            "schema_version": SCHEMA_VERSION,
            "layer": "aerosols",
            "provenance": {
                "provider": "NASA GMAO",
                "product": ds.attrs.get("product"),
                "source_dataset": ds.attrs.get("source_dataset"),
                "time_stamp_utc": ds.attrs.get("time_stamp_utc"),
                "averaging": ds.attrs.get("averaging"),
                "data_kind": ds.attrs.get("data_kind"),
                "original_file": source.name,
            },
            "precision": f"{SIGNIFICANT_DIGITS} significant digits",
            "grid": grid,
            "species": species,
        }
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(document, separators=(",", ":")), encoding="utf-8")
    return document
