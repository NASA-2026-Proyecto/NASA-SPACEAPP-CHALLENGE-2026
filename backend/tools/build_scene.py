import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import xarray as xr

from geosfp.grid import describe_grid

DEFAULT_SOURCE = Path("data/raw/geosfp_aer_europe_20260724_20260728.nc")
DEFAULT_SCENE_ID = "europe-smoke-2026-07"
SCALE_PERCENTILE = 99.0
SPECIES = {
    "brown_carbon": "brexttau",
    "black_carbon": "bcexttau",
    "dust": "duexttau",
    "sulfate": "suexttau",
    "sea_salt": "ssexttau",
    "total": "totexttau",
}


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(source: Path, scene_id: str) -> None:
    out_dir = Path("data/processed") / scene_id
    out_dir.mkdir(parents=True, exist_ok=True)

    with xr.open_dataset(source, engine="scipy", decode_times=False) as ds:
        lat, lon = ds["lat"].values, ds["lon"].values
        stamps = ds.attrs["time_stamps_utc"].split(",")
        n_steps = int(ds.sizes["step"])
        if len(stamps) != n_steps:
            raise ValueError("El número de marcas de tiempo no coincide con los pasos.")
        grid = describe_grid(lat, lon)
        expected = (n_steps, lat.size, lon.size)

        species = {}
        for key, variable in SPECIES.items():
            if variable not in ds.data_vars:
                print(f"{key}: no está en el archivo, se omite.")
                continue
            values = np.ascontiguousarray(ds[variable].values, dtype="<f4")
            if values.shape != expected:
                raise ValueError(f"{variable}: forma {values.shape}, se esperaba {expected}.")
            if not np.isfinite(values).all() or (values < 0).any():
                raise ValueError(f"{variable}: contiene valores no finitos o negativos.")
            path = out_dir / f"{key}.f32"
            path.write_bytes(values.tobytes())
            scale = float(f"{np.percentile(values, SCALE_PERCENTILE):.3g}")
            species[key] = {
                "source_variable": variable,
                "long_name": str(ds[variable].attrs.get("long_name", "")).strip(),
                "unit": "dimensionless",
                "file": path.name,
                "dtype": "float32-little-endian",
                "sha256": sha256_of(path),
                "min": float(values.min()),
                "max": float(values.max()),
                "display_scale_max": scale,
                "display_scale_method": f"p{SCALE_PERCENTILE:g} over all steps and cells of this scene",
            }
            print(
                f"{key:13s} min={values.min():.4g} max={values.max():.4g} "
                f"escala={scale} archivo={path.stat().st_size / 1e6:.2f} MB"
            )

        manifest = {
            "schema_version": 2,
            "scene_id": scene_id,
            "layer": "aerosols",
            "kind": "grid-series",
            "provenance": {
                "provider": "NASA GMAO",
                "product": ds.attrs.get("product"),
                "source_dataset": ds.attrs.get("source_dataset"),
                "averaging": ds.attrs.get("averaging"),
                "subsampling": ds.attrs.get("subsampling"),
                "data_kind": ds.attrs.get("data_kind"),
                "units_note": ds.attrs.get("units_note"),
            },
            "time": {
                "steps": n_steps,
                "step_minutes": 180,
                "stamps_utc": stamps,
                "note": "3-hour time averages; the meaning of each stamp (start or center) is not verified.",
            },
            "grid": grid,
            "species": species,
        }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"\nEscena guardada en {out_dir}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Convierte una serie NetCDF en una escena para la web.")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--scene-id", default=DEFAULT_SCENE_ID)
    args = parser.parse_args()
    build(args.source, args.scene_id)


if __name__ == "__main__":
    main()
