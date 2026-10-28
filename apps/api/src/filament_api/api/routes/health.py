"""Health check route handlers."""

from fastapi import APIRouter, Depends

from filament_api.config import Settings, get_settings
from filament_api.schemas.health import HealthResponse

router = APIRouter()


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="API Health Status",
    description=(
        "Returns the operational status of the API process, active environment, "
        "and version. This endpoint does not require a database connection, allowing "
        "reliable container or service process liveliness checks."
    ),
    response_description="Process liveliness confirmation",
)
async def get_health(settings: Settings = Depends(get_settings)) -> HealthResponse:
    """Return light process health probe status."""
    return HealthResponse(
        status="ok",
        environment=settings.ENVIRONMENT,
        version=settings.VERSION,
        database="not_checked",
    )

