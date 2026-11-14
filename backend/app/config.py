"""Configuración leída solo de variables de entorno.

En Docker las inyecta Compose desde el .env de la raíz del repo.
En local, sin Docker: `uv run --env-file ../.env uvicorn app.main:app --reload`.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    # Orígenes que pueden llamar a la API desde otro dominio (formato JSON en el entorno).
    # Vacío por defecto: el front llama a /api en su mismo origen y nginx hace de proxy.
    cors_origins: list[str] = []


@lru_cache
def get_settings() -> Settings:
    return Settings()
