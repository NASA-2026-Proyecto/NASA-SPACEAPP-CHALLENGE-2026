"""Escena "aerosol-latest": los últimos pasos de GEOS-FP, por especie de aerosol.

Se construye una vez por paso nuevo del modelo (cada 3 h): una petición por especie
para todo el globo, tomando 1 de cada 4 celdas (malla de 1° x 1,25°).
"""

from datetime import UTC, datetime

import numpy as np

from app.services.geosfp import FILL_LIMIT, GeosFpClient, Grid
from app.services.scenes import Scene, grid_block, species_entry, stamp, version_of

STRIDE = 4

# id -> (variable de GEOS-FP, máximo de la escala de color).
# Escala fija (p99 del episodio global de julio de 2026) para que los colores sean
# comparables entre actualizaciones.
SPECIES: dict[str, tuple[str, float]] = {
    "brown_carbon": ("brexttau", 0.432),
    "black_carbon": ("bcexttau", 0.0418),
    "dust": ("duexttau", 0.355),
    "sea_salt": ("ssexttau", 0.163),
    "sulfate": ("suexttau", 0.163),
}


class AerosolSource:
    scene_id = "aerosol-latest"

    def __init__(self, client: GeosFpClient, steps: int = 8) -> None:
        self._client = client
        self._steps = steps

    def check(self) -> tuple[str, Grid]:
        grid = self._client.grid()
        return version_of(grid.time_at(grid.n_times - 1)), grid

    def build(self, version: str, grid: Grid) -> Scene:
        last = grid.n_times - 1
        first = max(0, last - self._steps + 1)

        files: dict[str, bytes] = {}
        species: dict[str, dict] = {}
        shape: tuple[int, ...] = ()
        for key, (variable, scale) in SPECIES.items():
            values = self._client.fields(variable, grid, first, last, STRIDE)
            if not np.isfinite(values).all() or (values >= FILL_LIMIT).any() or (values < 0).any():
                raise ValueError(f"{variable}: contiene valores no válidos.")
            shape = values.shape
            files[f"{key}.f32"], species[key] = species_entry(
                version,
                key,
                values,
                source_variable=variable,
                unit="dimensionless",
                display_scale_max=scale,
                display_scale_method="fixed: p99 of the global scene of 24-28 July 2026",
            )

        manifest = {
            "schema_version": 2,
            "scene_id": self.scene_id,
            "version": version,
            "generated_utc": stamp(datetime.now(UTC)),
            "layer": "aerosols",
            "kind": "grid-series",
            "provenance": {
                "provider": "NASA GMAO",
                "product": "GEOS FP tavg3_2d_aer_Nx (assimilation)",
                "source_dataset": self._client.url,
                "averaging": "3-hourly time average",
                "subsampling": f"every {STRIDE}th lat and {STRIDE}th lon; values not averaged",
                "data_kind": "model analysis, near real time",
                "units_note": "dimensionless (optical depth at 550 nm); not declared by server",
            },
            "time": {
                "steps": shape[0],
                "step_minutes": int(grid.time_step.total_seconds() // 60),
                "stamps_utc": [stamp(grid.time_at(index)) for index in range(first, last + 1)],
                "note": "3-hour time averages; the last stamp is the newest step served by NASA.",
            },
            "grid": grid_block(
                grid.lat_min, grid.lat_step * STRIDE, grid.lon_min, grid.lon_step * STRIDE, shape
            ),
            "species": species,
        }
        return Scene(version=version, manifest=manifest, files=files)
