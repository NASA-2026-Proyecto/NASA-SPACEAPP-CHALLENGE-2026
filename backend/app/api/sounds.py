"""Rutas de los sonidos: qué suena en un punto y el audio que lo dice."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, Response

from app.schemas import SoundList, SoundReading
from app.services.sonification import (
    BusyError,
    NoAudioError,
    SceneNotReadyError,
    Sonifier,
    UnknownSoundError,
)

router = APIRouter(prefix="/sounds", tags=["sonidos"])

SCENE_RETRY_SECONDS = "5"
BUSY_RETRY_SECONDS = "2"

Latitude = Annotated[float, Query(ge=-90, le=90, description="Latitud, grados norte")]
Longitude = Annotated[float, Query(ge=-180, le=180, description="Longitud, grados este")]


def _sonifier(request: Request) -> Sonifier:
    """El sonificador de la aplicación (lo crea `app.factory.create_app`)."""
    sonifier: Sonifier = request.app.state.sonifier
    return sonifier


def _unavailable(detail: str, retry_seconds: str) -> HTTPException:
    """Respuesta 503 que pide reintentar al cabo de unos segundos."""
    return HTTPException(
        status_code=503,
        detail=detail,
        headers={"Retry-After": retry_seconds, "Cache-Control": "no-store"},
    )


@router.get("", summary="Sonidos disponibles")
def list_sounds(request: Request) -> SoundList:
    """Identificadores de los sonidos, en orden alfabético."""
    return SoundList(sounds=_sonifier(request).ids())


@router.get(
    "/{sound_id}",
    summary="Qué suena en un punto: el dato, su descripción y la dirección del audio",
    response_model_exclude_none=True,
    responses={
        404: {"description": "Sonido desconocido"},
        503: {"description": "Los datos aún se están preparando; reintentar en unos segundos"},
    },
)
def read_sound(
    sound_id: str, lat: Latitude, lon: Longitude, request: Request, response: Response
) -> SoundReading:
    """Lee el punto en el paso más reciente de la escena. No genera el audio, así que es rápido."""
    try:
        reading = _sonifier(request).read(sound_id, lat, lon)
    except UnknownSoundError:
        raise HTTPException(status_code=404, detail="Sonido desconocido.") from None
    except SceneNotReadyError:
        raise _unavailable(
            "Preparando los datos de la NASA; vuelve a intentarlo en unos segundos.", SCENE_RETRY_SECONDS
        ) from None
    response.headers["Cache-Control"] = "no-cache"
    return reading


@router.get(
    "/{sound_id}/{version}.wav",
    summary="El audio de un punto: WAV estéreo de 16 bits a 44,1 kHz",
    response_class=Response,
    responses={
        200: {"content": {"audio/wav": {}}},
        404: {"description": "Sonido o versión no disponible, o punto sin sonido"},
        503: {"description": "Se están generando otros sonidos; reintentar en unos segundos"},
    },
)
def render_sound(sound_id: str, version: str, lat: Latitude, lon: Longitude, request: Request) -> Response:
    """Genera el audio. Es siempre el mismo para la misma dirección, así que se puede cachear."""
    try:
        audio = _sonifier(request).render(sound_id, version, lat, lon)
    except (UnknownSoundError, NoAudioError):
        raise HTTPException(status_code=404, detail="No hay sonido para esa dirección.") from None
    except BusyError:
        raise _unavailable(
            "Se están generando otros sonidos; vuelve a intentarlo en unos segundos.", BUSY_RETRY_SECONDS
        ) from None
    return Response(
        content=audio,
        media_type="audio/wav",
        headers={"Cache-Control": "public, max-age=86400, immutable"},
    )
