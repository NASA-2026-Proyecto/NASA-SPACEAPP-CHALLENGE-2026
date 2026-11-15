"""Comprobación de que la API está en marcha (la usan Docker y los despliegues)."""

from fastapi import APIRouter

from app import __version__
from app.schemas import Health

router = APIRouter(tags=["estado"])


@router.get("/health", summary="Comprueba que la API está en marcha")
def health() -> Health:
    """Responde siempre "ok" con la versión de la API; no depende de la NASA."""
    return Health(status="ok", version=__version__)
