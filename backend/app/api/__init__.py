from fastapi import APIRouter

from app.api import health, point

router = APIRouter(prefix="/api")
router.include_router(health.router)
router.include_router(point.router)
