"""Escenas hechas a mano (sin NASA) para probar lo que lee de ellas: los sonidos."""

from datetime import UTC, datetime, timedelta

import numpy as np

from app.services.scenes import (
    Scene,
    SceneStore,
    build_manifest,
    encode_species,
    time_axis,
    whole_globe_grid,
)

# Celdas de 1°: la celda (fila, columna) tiene su centro en fila - 89,5 y columna - 179,5
N_LAT, N_LON = 180, 360
NEWEST = datetime(2026, 11, 14, 21, 30, tzinfo=UTC)


def cell(lat: float, lon: float) -> tuple[int, int]:
    """Fila y columna de la celda de 1° que contiene un punto."""
    return int(lat + 90), int(lon + 180)


def scene_of(scene_id: str, fields: dict[str, np.ndarray], version: str = "20261114T2130Z") -> Scene:
    """Escena de dos pasos: el más antiguo a cero y el más reciente con `fields` (especie -> malla 2D)."""
    files, species = {}, {}
    for key, newest in fields.items():
        values = np.stack([np.zeros_like(newest), newest]).astype("float32")
        files[f"{key}.f32"], species[key] = encode_species(
            version,
            key,
            values,
            source_variable="test",
            unit="test",
            display_scale_max=1.0,
            display_scale_method="test",
        )
    manifest = build_manifest(
        scene_id=scene_id,
        version=version,
        layer="test",
        provenance={},
        time=time_axis([NEWEST - timedelta(hours=3), NEWEST], step_minutes=180, note="test"),
        grid=whole_globe_grid(N_LAT, N_LON),
        species=species,
    )
    return Scene(version=version, manifest=manifest, files=files)


class StaticSource:
    """Fuente que entrega la escena que se le ponga en `scene` (None = aún no hay datos)."""

    def __init__(self, scene_id: str, scene: Scene | None = None) -> None:
        self.scene_id = scene_id
        self.scene = scene

    def check(self) -> tuple[str, Scene]:
        if self.scene is None:
            raise TimeoutError("sin datos todavía")
        return self.scene.version, self.scene

    def build(self, version: str, scene: Scene) -> Scene:
        return scene


def store_of(scene_id: str, scene: Scene | None = None) -> SceneStore:
    """Almacén con esa escena ya cargada; no lanza renovaciones por su cuenta."""
    store = SceneStore(StaticSource(scene_id, scene), spawn=lambda task: None)
    store.refresh()
    return store
