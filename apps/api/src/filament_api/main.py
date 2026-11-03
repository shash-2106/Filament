"""Main FastAPI application entrypoint for Filament API."""

from contextlib import asynccontextmanager
import logging
from typing import Any, AsyncGenerator, Optional

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from filament_api.api import api_router
from filament_api.config import Settings, get_settings
from filament_api.core import log_safe_exception
from filament_api.db.session import close_db_engine

logger = logging.getLogger(__name__)


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

    # Register standardized error response handlers
    @app.exception_handler(StarletteHTTPException)
    async def custom_http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        if isinstance(exc.detail, dict) and "error" in exc.detail:
            content = exc.detail
        else:
            code_mapping = {
                400: "BAD_REQUEST",
                401: "UNAUTHORIZED",
                403: "FORBIDDEN",
                404: "NOT_FOUND",
                405: "METHOD_NOT_ALLOWED",
                409: "CONFLICT",
                422: "VALIDATION_ERROR",
                500: "INTERNAL_SERVER_ERROR",
            }
            code = code_mapping.get(exc.status_code, "HTTP_ERROR")
            content = {"error": {"code": code, "message": str(exc.detail)}}
        return JSONResponse(status_code=exc.status_code, content=content, headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        sanitized_details = []
        for err in exc.errors():
            detail: dict[str, Any] = {
                "loc": list(err.get("loc", [])),
                "msg": err.get("msg", ""),
                "type": err.get("type", ""),
            }
            ctx = err.get("ctx")
            if isinstance(ctx, dict):
                safe_ctx = {}
                for k, v in ctx.items():
                    # Omit raw submitted input values and internal exception objects
                    if k not in ("error", "input") and isinstance(v, (str, int, float, bool, list)):
                        safe_ctx[k] = v
                if safe_ctx:
                    detail["ctx"] = safe_ctx
            sanitized_details.append(detail)

        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "Request validation failed.",
                    "details": sanitized_details,
                }
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        log_safe_exception(
            logger,
            f"Unhandled server exception processing {request.method} {request.url.path}",
            exc,
        )
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL_SERVER_ERROR",
                    "message": "An internal server error occurred.",
                }
            },
        )

    # Mount API v1 routes
    app.include_router(api_router, prefix=cfg.API_V1_PREFIX)

    return app


# Default application instance for ASGI servers (e.g. uvicorn filament_api.main:app)
app = create_app()

