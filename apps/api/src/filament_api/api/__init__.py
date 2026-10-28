"""API routing module."""

from fastapi import APIRouter

from filament_api.api.routes.health import router as health_router

api_router = APIRouter()
api_router.include_router(health_router, prefix="", tags=["Health"])

__all__ = ["api_router"]

