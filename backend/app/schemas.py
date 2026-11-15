"""Contrato de la API con el front: los modelos de las respuestas.

El manifiesto de una escena es el contrato más importante: el front
(`frontend/js/data/scene-data.js`) lo usa para saber qué archivos pedir y cómo leerlos.
"""

from typing import Literal

from pydantic import BaseModel, Field

# Valores sueltos que documentan el origen de una escena (texto, números o listas de URLs)
type ProvenanceValue = str | int | float | list[str]


class Health(BaseModel):
    """Estado de la API."""

    status: str
    version: str


class SceneList(BaseModel):
    """Identificadores de las escenas que sirve la API."""

    scenes: list[str]


class TimeAxis(BaseModel):
    """Eje de tiempo de una escena: un paso por cada instante, del más antiguo al más reciente."""

    steps: int = Field(ge=1)
    step_minutes: int = Field(description="Minutos entre un paso y el siguiente")
    stamps_utc: list[str] = Field(description="Un instante por paso, como 2026-11-14T13:30Z")
    note: str = Field(description="Qué significan los instantes y con qué precisión se conocen")


class GridBlock(BaseModel):
    """Malla regular lat/lon. Las coordenadas son las de los valores (centros de celda)."""

    lat_min: float
    lat_step: float
    lon_min: float
    lon_step: float
    n_lat: int
    n_lon: int
    lon_periodic: bool = Field(description="La malla da la vuelta completa al globo")
    reference: str
    order: str = Field(description="Orden de los valores dentro de cada archivo")


class Scale(BaseModel):
    """Escala de color original de los datos: el front pinta con ella."""

    kind: Literal["log", "linear"]
    min: float
    max: float
    ramp: list[str] = Field(description="Colores #rrggbb repartidos de `min` a `max`")


class SpeciesEntry(BaseModel):
    """Una variable de la escena y el archivo binario que lleva sus valores."""

    source_variable: str
    long_name: str | None = None
    unit: str
    missing: str | None = Field(default=None, description="Cómo se marcan los huecos, si los hay")
    file: str = Field(description="Ruta del archivo de valores, relativa a la URL de la escena")
    dtype: Literal["float32-little-endian"] = "float32-little-endian"
    sha256: str
    min: float
    max: float
    scale: Scale | None = None
    display_scale_max: float
    display_scale_method: str


class Manifest(BaseModel):
    """Descripción completa de una escena (schema_version 2, serie de mallas)."""

    schema_version: Literal[2] = 2
    scene_id: str
    version: str = Field(description="Cambia con cada actualización; forma parte de la URL de los archivos")
    generated_utc: str
    layer: str
    kind: Literal["grid-series"] = "grid-series"
    provenance: dict[str, ProvenanceValue]
    time: TimeAxis
    grid: GridBlock
    species: dict[str, SpeciesEntry]
