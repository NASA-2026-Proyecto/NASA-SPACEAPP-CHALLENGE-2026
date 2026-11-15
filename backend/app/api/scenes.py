from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from app.services.scenes import SceneStore

router = APIRouter(prefix="/scenes", tags=["escenas"])


def _store(request: Request, scene_id: str) -> SceneStore:
    store = request.app.state.scenes.get(scene_id)
    if store is None:
        raise HTTPException(status_code=404, detail="Escena desconocida.")
    return store


@router.get("", summary="Escenas disponibles")
def list_scenes(request: Request) -> dict:
    return {"scenes": sorted(request.app.state.scenes)}


@router.get(
    "/{scene_id}/manifest.json",
    summary="Manifiesto de una escena (tiempos, malla y un archivo por especie)",
    responses={503: {"description": "La escena aún se está preparando; reintentar en unos segundos"}},
)
def get_manifest(scene_id: str, request: Request) -> JSONResponse:
    store = _store(request, scene_id)
    scene = store.get()
    if scene is None:
        return JSONResponse(
            status_code=503,
            content={
                "status": "building",
                "detail": store.error or "Preparando los datos de la NASA.",
            },
            headers={"Retry-After": "5", "Cache-Control": "no-store"},
        )
    # El manifiesto cambia con cada actualización; los .f32 llevan la versión en la URL
    return JSONResponse(scene.manifest, headers={"Cache-Control": "no-cache"})


@router.get(
    "/{scene_id}/{version}/{name}.f32",
    summary="Valores de una especie: float32 little-endian, [paso][lat][lon]",
    response_class=Response,
)
def get_values(scene_id: str, version: str, name: str, request: Request) -> Response:
    data = _store(request, scene_id).file(version, f"{name}.f32")
    if data is None:
        raise HTTPException(status_code=404, detail="Versión o especie no disponible.")
    return Response(
        content=data,
        media_type="application/octet-stream",
        headers={"Cache-Control": "public, max-age=86400, immutable"},
    )
