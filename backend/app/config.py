"""Configuración leída solo de variables de entorno.

En Docker las inyecta Compose desde el .env de la raíz del repo.
En local, sin Docker: `uv run --env-file ../.env uvicorn app.main:app --reload`.
"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Ajustes de la API. Cada campo se lee de la variable de entorno del mismo nombre."""

    model_config = SettingsConfigDict(extra="ignore")

    cors_origins: list[str] = Field(
        default_factory=list,
        description="Orígenes que pueden llamar a la API desde otro dominio (JSON en el entorno). "
        "Vacío por defecto: el front llama a /api en su mismo origen y nginx hace de proxy.",
    )
    scene_steps: int = Field(
        default=8,
        ge=1,
        le=24,
        description="Pasos de cada escena. 8 pasos de 3 h cubren el último día, que el front "
        "anima en bucle; cada paso de más son más megas que descarga el navegador.",
    )
    scene_warmup: bool = Field(
        default=True,
        description="Empezar a preparar las escenas al arrancar (si no, con la primera petición).",
    )


@lru_cache
def get_settings() -> Settings:
    """Ajustes del proceso, leídos del entorno una sola vez."""
    return Settings()
