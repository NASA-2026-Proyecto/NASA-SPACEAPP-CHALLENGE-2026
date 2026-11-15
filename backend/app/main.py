"""Punto de entrada de la API. Todas las rutas cuelgan de /api.

El front se sirve aparte (nginx) y le reenvía /api/*, así navegador, front y API
comparten origen y no hace falta CORS. `app` es también la entrada que espera Vercel.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api import router as api_router
from app.config import Settings, get_settings
from app.services.geosfp import GeosFpClient
from app.services.scenes import SceneStore


def create_app(settings: Settings | None = None, scenes: SceneStore | None = None) -> FastAPI:
    settings = settings or get_settings()
    scenes = scenes or SceneStore(GeosFpClient(), steps=settings.scene_steps)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if settings.scene_warmup:
            scenes.get()  # no espera: lanza la descarga de la NASA en segundo plano
        yield

    app = FastAPI(
        title="Earth Jukebox API",
        version=__version__,
        description="Datos de observación de la Tierra preparados para sonificación.",
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )

    # Solo si se llama a la API desde otro origen (p. ej., front y API en dominios distintos)
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_methods=["GET"],
            allow_headers=["*"],
        )

    app.state.scenes = scenes
    app.include_router(api_router)
    return app


app = create_app()
