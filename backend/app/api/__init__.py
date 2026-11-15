"""Rutas HTTP de la API. Todas cuelgan de /api, que es lo que nginx reenvía."""

from fastapi import APIRouter

from app.api import health, scenes, sounds

router = APIRouter(prefix="/api")
router.include_router(health.router)
router.include_router(scenes.router)
router.include_router(sounds.router)
