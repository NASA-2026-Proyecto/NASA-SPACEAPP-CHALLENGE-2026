"""Escena "en vivo" de aerosoles: los últimos pasos de GEOS-FP en el formato de escenas del front.

El formato (manifiesto schema_version 2 + un .f32 por especie) es el de
backend/tools/build_scene.py, así que el front la carga igual que una escena estática.
La escena se construye una vez por paso nuevo del modelo (cada 3 h) y se guarda en
memoria: ningún clic del usuario espera a la NASA.
"""

import hashlib
import logging
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime

import numpy as np

from app.services.geosfp import FILL_LIMIT, GeosFpClient, Grid

logger = logging.getLogger(__name__)

SCENE_ID = "aerosol-latest"
STRIDE = 4  # 1 de cada 4 celdas: malla global de 1° x 1,25°

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


@dataclass(frozen=True)
class Scene:
    version: str  # marca del paso más reciente; forma parte de la URL de los .f32
    manifest: dict
    files: dict[str, bytes]  # "<especie>.f32" -> float32 little-endian, [paso][lat][lon]


def _stamp(moment: datetime) -> str:
    return f"{moment:%Y-%m-%dT%H:%M}Z"


def latest_version(grid: Grid) -> str:
    return f"{grid.time_at(grid.n_times - 1):%Y%m%dT%H%MZ}"


def build_scene(client: GeosFpClient, grid: Grid, steps: int) -> Scene:
    last = grid.n_times - 1
    first = max(0, last - steps + 1)
    version = latest_version(grid)

    files: dict[str, bytes] = {}
    species: dict[str, dict] = {}
    shape: tuple[int, ...] = ()
    for key, (variable, scale) in SPECIES.items():
        values = client.fields(variable, grid, first, last, STRIDE)
        if not np.isfinite(values).all() or (values >= FILL_LIMIT).any() or (values < 0).any():
            raise ValueError(f"{variable}: contiene valores no válidos.")
        shape = values.shape
        data = values.tobytes()
        files[f"{key}.f32"] = data
        species[key] = {
            "source_variable": variable,
            "unit": "dimensionless",
            "file": f"{version}/{key}.f32",
            "dtype": "float32-little-endian",
            "sha256": hashlib.sha256(data).hexdigest(),
            "min": float(values.min()),
            "max": float(values.max()),
            "display_scale_max": scale,
            "display_scale_method": "fixed: p99 of the global scene of 24-28 July 2026",
        }

    n_steps, n_lat, n_lon = shape
    lon_step = grid.lon_step * STRIDE
    manifest = {
        "schema_version": 2,
        "scene_id": SCENE_ID,
        "version": version,
        "generated_utc": _stamp(datetime.now(UTC)),
        "layer": "aerosols",
        "kind": "grid-series",
        "provenance": {
            "provider": "NASA GMAO",
            "product": "GEOS FP tavg3_2d_aer_Nx (assimilation)",
            "source_dataset": client.url,
            "averaging": "3-hourly time average",
            "subsampling": f"every {STRIDE}th lat and {STRIDE}th lon; values not averaged",
            "data_kind": "model analysis, near real time",
            "units_note": "dimensionless (optical depth at 550 nm); not declared by server",
        },
        "time": {
            "steps": n_steps,
            "step_minutes": int(grid.time_step.total_seconds() // 60),
            "stamps_utc": [_stamp(grid.time_at(index)) for index in range(first, last + 1)],
            "note": "3-hour time averages; the last stamp is the newest step served by NASA.",
        },
        "grid": {
            "lat_min": grid.lat_min,
            "lat_step": grid.lat_step * STRIDE,
            "lon_min": grid.lon_min,
            "lon_step": lon_step,
            "n_lat": n_lat,
            "n_lon": n_lon,
            "lon_periodic": bool(np.isclose(lon_step * n_lon, 360.0)),
            "reference": "values at the listed grid coordinates",
            "order": "[step][lat][lon], row-major; lat south to north, lon west to east",
        },
        "species": species,
    }
    return Scene(version=version, manifest=manifest, files=files)


class SceneStore:
    """Guarda la escena actual y la renueva en segundo plano cuando la NASA publica un paso nuevo.

    Conserva también la anterior: un navegador que ya tenía el manifiesto viejo puede
    terminar de descargar sus .f32 aunque haya habido una actualización entre medias.
    """

    def __init__(
        self,
        client: GeosFpClient,
        steps: int = 3,
        check_seconds: float = 900.0,
        retry_seconds: float = 30.0,
    ) -> None:
        self._client = client
        self._steps = steps
        self._check_seconds = check_seconds
        self._retry_seconds = retry_seconds
        self._lock = threading.Lock()
        self._refreshing = False
        self._current: Scene | None = None
        self._previous: Scene | None = None
        self._next_check = 0.0  # reloj monótono
        self.error: str | None = None

    def get(self) -> Scene | None:
        """Devuelve la escena disponible (o None) sin esperar; lanza la renovación si toca."""
        with self._lock:
            due = not self._refreshing and time.monotonic() >= self._next_check
            if due:
                self._refreshing = True
        if due:
            threading.Thread(target=self.refresh, name="scene-refresh", daemon=True).start()
        return self._current

    def file(self, version: str, name: str) -> bytes | None:
        for scene in (self._current, self._previous):
            if scene is not None and scene.version == version:
                return scene.files.get(name)
        return None

    def refresh(self) -> None:
        """Comprueba si hay un paso nuevo y, si lo hay, construye la escena. Bloquea."""
        try:
            grid = self._client.grid()
            current = self._current
            if current is None or current.version != latest_version(grid):
                scene = build_scene(self._client, grid, self._steps)
                with self._lock:
                    self._previous, self._current = current, scene
                logger.info("Escena %s lista: %s", SCENE_ID, scene.version)
            delay, self.error = self._check_seconds, None
        except Exception as error:  # la NASA falla a ratos: se conserva la escena anterior
            logger.warning("No se pudo renovar la escena %s: %r", SCENE_ID, error)
            delay, self.error = self._retry_seconds, f"{type(error).__name__}: {error}"
        with self._lock:
            self._next_check = time.monotonic() + delay
            self._refreshing = False
