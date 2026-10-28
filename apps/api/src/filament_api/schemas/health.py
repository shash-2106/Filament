"""Health check schemas for system operational status."""

from typing import Optional
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Schema representing the health and operational metadata of the API process."""

    status: str = Field(
        default="ok",
        description="Overall service health status indicator",
        examples=["ok"],
    )
    environment: str = Field(
        description="Active runtime environment tier",
        examples=["development"],
    )
    version: str = Field(
        description="Filament API release version",
        examples=["0.1.0"],
    )
    database: Optional[str] = Field(
        default="not_checked",
        description="Database connectivity check status (optional; not evaluated during light process probe)",
        examples=["not_checked"],
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "status": "ok",
                "environment": "development",
                "version": "0.1.0",
                "database": "not_checked",
            }
        }
    }

