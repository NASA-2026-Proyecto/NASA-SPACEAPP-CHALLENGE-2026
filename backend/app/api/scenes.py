"""Rutas de las escenas: el manifiesto de cada una y sus archivos de valores."""

from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response

from app.schemas import Manifest, SceneList
from app.services.scenes import SceneStore, SceneStores

router = APIRouter(prefix="/scenes", tags=["escenas"])

RETRY_AFTER_SECONDS = "5"


def _stores(request: Request) -> SceneStores:
    """Almacenes de escenas de la aplicación (los crea `app.factory.create_app`)."""
    stores: SceneStores = request.app.state.scenes
    return stores


def _store(request: Request, scene_id: str) -> SceneStore[Any]:
    """Almacén de una escena, o 404 si no existe."""
    store = _stores(request).get(scene_id)
    if store is None:
        raise HTTPException(status_code=404, detail="Escena desconocida.")
    return store


@router.get("", summary="Escenas disponibles")
def list_scenes(request: Request) -> SceneList:
    """Identificadores de las escenas, en orden alfabético."""
    return SceneList(scenes=sorted(_stores(request)))


@router.get(
    "/{scene_id}/manifest.json",
    summary="Manifiesto de una escena (tiempos, malla y un archivo por especie)",
    response_model_exclude_none=True,
    responses={
        404: {"description": "Escena desconocida"},
        503: {"description": "La escena aún se está preparando; reintentar en unos segundos"},
    },
)
def get_manifest(scene_id: str, request: Request, response: Response) -> Manifest:
    """Manifiesto de la versión actual de la escena.

    Cambia con cada actualización, así que no se cachea; los .f32 llevan la versión en
    la URL y sí. Mientras la escena no está lista responde 503 con `Retry-After`.
    """
    scene = _store(request, scene_id).get()
    if scene is None:
        # El motivo exacto queda en el registro del servidor; al cliente le basta reintentar
        raise HTTPException(
            status_code=503,
            detail="Preparando los datos de la NASA; vuelve a intentarlo en unos segundos.",
            headers={"Retry-After": RETRY_AFTER_SECONDS, "Cache-Control": "no-store"},
        )
    response.headers["Cache-Control"] = "no-cache"
    return scene.manifest


@router.get(
    "/{scene_id}/{version}/{name}.f32",
    summary="Valores de una especie: float32 little-endian, [paso][lat][lon]",
    response_class=Response,
    responses={404: {"description": "Escena, versión o especie no disponible"}},
)
def get_values(scene_id: str, version: str, name: str, request: Request) -> Response:
    """Archivo de valores de una especie para una versión concreta de la escena."""
    data = _store(request, scene_id).file(version, f"{name}.f32")
    if data is None:
        raise HTTPException(status_code=404, detail="Versión o especie no disponible.")
    return Response(
        content=data,
        media_type="application/octet-stream",
        headers={"Cache-Control": "public, max-age=86400, immutable"},
    )
