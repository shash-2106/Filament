"""API routing module."""

from fastapi import APIRouter

from filament_api.api.routes.claims import router as claims_router
from filament_api.api.routes.evidence import router as evidence_router
from filament_api.api.routes.health import router as health_router
from filament_api.api.routes.snapshots import router as snapshots_router

api_router = APIRouter()
api_router.include_router(health_router, prefix="", tags=["Health"])
api_router.include_router(evidence_router, prefix="", tags=["Evidence"])
api_router.include_router(claims_router, prefix="", tags=["Claims"])
api_router.include_router(snapshots_router, prefix="", tags=["Snapshots"])

__all__ = ["api_router"]

