from fastapi import APIRouter

from app.api.params import Lat, Lon
from app.schemas import PointResponse

router = APIRouter(tags=["globo"])


@router.get("/point", summary="Confirma la recepción de unas coordenadas del globo")
def get_point(lat: Lat, lon: Lon) -> PointResponse:
    return PointResponse(
        ok=True,
        lat=lat,
        lon=lon,
        message=f"Coordenadas recibidas: lat {lat:.4f}, lon {lon:.4f}",
    )
