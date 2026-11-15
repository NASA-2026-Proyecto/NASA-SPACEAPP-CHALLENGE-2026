from fastapi import APIRouter

from app import __version__
from app.schemas import Health

router = APIRouter(tags=["estado"])


@router.get("/health", summary="Comprueba que la API está en marcha")
def health() -> Health:
    return Health(status="ok", version=__version__)
