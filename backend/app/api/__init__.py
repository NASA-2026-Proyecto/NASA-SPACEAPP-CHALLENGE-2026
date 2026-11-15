from fastapi import APIRouter

from app.api import health, point, scenes

router = APIRouter(prefix="/api")
router.include_router(health.router)
router.include_router(point.router)
router.include_router(scenes.router)
