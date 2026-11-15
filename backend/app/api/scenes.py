from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from app.services.scenes import SCENE_ID, SceneStore

router = APIRouter(prefix=f"/scenes/{SCENE_ID}", tags=["escenas"])


def _store(request: Request) -> SceneStore:
    return request.app.state.scenes


@router.get(
    "/manifest.json",
    summary="Manifiesto de la escena de aerosoles más reciente (GEOS-FP)",
    responses={503: {"description": "La escena aún se está preparando; reintentar en unos segundos"}},
)
def get_manifest(request: Request) -> JSONResponse:
    store = _store(request)
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
    # El manifiesto cambia cada 3 h; los .f32 llevan la versión en la URL y sí se cachean
    return JSONResponse(scene.manifest, headers={"Cache-Control": "no-cache"})


@router.get(
    "/{version}/{name}.f32",
    summary="Valores de una especie: float32 little-endian, [paso][lat][lon]",
    response_class=Response,
)
def get_values(version: str, name: str, request: Request) -> Response:
    data = _store(request).file(version, f"{name}.f32")
    if data is None:
        raise HTTPException(status_code=404, detail="Escena o especie no disponible.")
    return Response(
        content=data,
        media_type="application/octet-stream",
        headers={"Cache-Control": "public, max-age=86400, immutable"},
    )
