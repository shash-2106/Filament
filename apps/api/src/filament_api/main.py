"""Main FastAPI application entrypoint for Filament API."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from filament_api.api import api_router
from filament_api.config import Settings, get_settings
from filament_api.db.session import close_db_engine


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager for graceful startup and shutdown."""
    # Startup tasks (if needed in future stages)
    yield
    # Shutdown tasks: ensure database connection pools are closed cleanly
    await close_db_engine()


def create_app(settings: Optional[Settings] = None) -> FastAPI:
    """Create and configure a FastAPI application instance."""
    cfg = settings or get_settings()

    app = FastAPI(
        title=cfg.PROJECT_NAME,
        version=cfg.VERSION,
        description=(
            "Provenance-aware memory governance system for AI agents. "
            "Enforces server-side policy validation, fine-grained lineage tracking, "
            "and auditable memory boundaries."
        ),
        openapi_url="/openapi.json",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # Configure CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Mount API v1 routes
    app.include_router(api_router, prefix=cfg.API_V1_PREFIX)

    return app


# Default application instance for ASGI servers (e.g. uvicorn filament_api.main:app)
app = create_app()

