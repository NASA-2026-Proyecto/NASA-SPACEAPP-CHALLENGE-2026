"""Escenas: el formato común con el que los datos en malla llegan al front.

Una escena es un manifiesto (schema_version 2, kind "grid-series") más un .f32 por
especie: float32 little-endian en orden [paso][lat][lon], de sur a norte y de oeste a
este. Es el formato de backend/tools/build_scene.py, así que el front carga igual una
escena estática que una preparada aquí.

Cada fuente (GEOS-FP, visualización diaria del EIC...) sabe comprobar si hay datos
nuevos y construir su escena. `SceneStore` la guarda en memoria y la renueva en segundo
plano: ningún clic del usuario espera a la NASA.
"""

import hashlib
import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

import numpy as np

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Scene:
    version: str  # forma parte de la URL de los .f32, que así se pueden cachear
    manifest: dict
    files: dict[str, bytes]  # "<especie>.f32" -> valores


class SceneSource(Protocol):
    scene_id: str

    def check(self) -> tuple[str, Any]:
        """Consulta barata: versión disponible en origen y lo necesario para construirla."""

    def build(self, version: str, context: Any) -> Scene:
        """Descarga los datos y construye la escena. Puede tardar."""


def stamp(moment: datetime) -> str:
    return f"{moment:%Y-%m-%dT%H:%M}Z"


def version_of(moment: datetime) -> str:
    return f"{moment:%Y%m%dT%H%MZ}"


def grid_block(lat_min: float, lat_step: float, lon_min: float, lon_step: float, shape: tuple) -> dict:
    n_lat, n_lon = shape[-2:]
    return {
        "lat_min": lat_min,
        "lat_step": lat_step,
        "lon_min": lon_min,
        "lon_step": lon_step,
        "n_lat": n_lat,
        "n_lon": n_lon,
        "lon_periodic": bool(np.isclose(lon_step * n_lon, 360.0)),
        "reference": "values at the listed grid coordinates",
        "order": "[step][lat][lon], row-major; lat south to north, lon west to east",
    }


def species_entry(version: str, key: str, values: np.ndarray, **extra: Any) -> tuple[bytes, dict]:
    """Serializa una especie y devuelve (bytes del .f32, su entrada del manifiesto)."""
    data = np.ascontiguousarray(values, dtype="<f4").tobytes()
    entry = {
        "file": f"{version}/{key}.f32",
        "dtype": "float32-little-endian",
        "sha256": hashlib.sha256(data).hexdigest(),
        "min": float(np.nanmin(values)),
        "max": float(np.nanmax(values)),
        **extra,
    }
    return data, entry


class SceneStore:
    """Guarda la escena actual de una fuente y la renueva cuando en origen hay una versión nueva.

    Conserva también la anterior: un navegador que ya tenía el manifiesto viejo puede
    terminar de descargar sus .f32 aunque haya habido una actualización entre medias.
    """

    def __init__(
        self,
        source: SceneSource,
        check_seconds: float = 900.0,
        retry_seconds: float = 30.0,
    ) -> None:
        self._source = source
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
        """Comprueba si hay una versión nueva y, si la hay, construye la escena. Bloquea."""
        scene_id = self._source.scene_id
        try:
            version, context = self._source.check()
            current = self._current
            if current is None or current.version != version:
                scene = self._source.build(version, context)
                with self._lock:
                    self._previous, self._current = current, scene
                logger.info("Escena %s lista: %s", scene_id, scene.version)
            delay, self.error = self._check_seconds, None
        except Exception as error:  # la NASA falla a ratos: se conserva la escena anterior
            logger.warning("No se pudo renovar la escena %s: %r", scene_id, error)
            delay, self.error = self._retry_seconds, f"{type(error).__name__}: {error}"
        with self._lock:
            self._next_check = time.monotonic() + delay
            self._refreshing = False
