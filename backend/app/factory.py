"""Construcción de la aplicación FastAPI.

Está separada de `app.main` para poder crear la aplicación con ajustes y escenas
explícitos (en los tests) sin leer nada del entorno de quien la importa.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api import router as api_router
from app.config import Settings, get_settings
from app.services.aerosol_scene import AerosolSource
from app.services.fire_scene import FireSource
from app.services.geosfp import GeosFpClient
from app.services.pm25_scene import Pm25Source
from app.services.precipitation_scene import PrecipitationSource
from app.services.scenes import SceneStore, SceneStores
from app.services.svs import SvsClient


def default_scenes(settings: Settings) -> SceneStores:
    """Las escenas que sirve la API, cada una en su almacén y aún sin datos."""
    svs = SvsClient()
    return {
        # API casi en tiempo real
        AerosolSource.scene_id: SceneStore(AerosolSource(GeosFpClient(), steps=settings.scene_steps)),
        # Visualizaciones del Earth Information Center
        Pm25Source.scene_id: SceneStore(Pm25Source(svs, steps=settings.scene_steps)),
        FireSource.scene_id: SceneStore(FireSource(svs, steps=settings.scene_steps)),
        PrecipitationSource.scene_id: SceneStore(PrecipitationSource(svs, steps=settings.scene_steps)),
    }


def create_app(settings: Settings | None = None, scenes: SceneStores | None = None) -> FastAPI:
    """Crea la aplicación.

    Args:
        settings: Ajustes; por defecto, los del entorno.
        scenes: Almacenes de escenas; por defecto, los que hablan con la NASA.
    """
    settings = settings or get_settings()
    stores = default_scenes(settings) if scenes is None else scenes

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        """Al arrancar, empieza a preparar las escenas para que la primera visita no espere."""
        if settings.scene_warmup:
            for store in stores.values():
                store.get()  # no espera: lanza la descarga de la NASA en segundo plano
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

    app.state.scenes = stores
    app.include_router(api_router)
    return app
