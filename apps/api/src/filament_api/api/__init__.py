"""API routing module."""

from fastapi import APIRouter

from filament_api.api.routes.audit import router as audit_router
from filament_api.api.routes.claims import router as claims_router
from filament_api.api.routes.evidence import router as evidence_router
from filament_api.api.routes.extraction import router as extraction_router
from filament_api.api.routes.health import router as health_router
from filament_api.api.routes.model_usage import router as model_usage_router
from filament_api.api.routes.snapshots import router as snapshots_router
from filament_api.api.routes.workspaces import router as workspaces_router

api_router = APIRouter()
api_router.include_router(health_router, prefix="", tags=["Health"])
api_router.include_router(workspaces_router, prefix="", tags=["Workspaces"])
api_router.include_router(evidence_router, prefix="", tags=["Evidence"])
api_router.include_router(claims_router, prefix="", tags=["Claims"])
api_router.include_router(snapshots_router, prefix="", tags=["Snapshots"])
api_router.include_router(audit_router, prefix="", tags=["Audit"])
api_router.include_router(model_usage_router, prefix="", tags=["Model Usage & Budget"])
api_router.include_router(extraction_router, prefix="", tags=["Memory Extraction"])

__all__ = ["api_router"]
