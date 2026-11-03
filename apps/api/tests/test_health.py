"""Tests for the Filament API health endpoint and application initialization."""

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from pydantic import ValidationError

from filament_api.config import Settings
from filament_api.schemas.health import HealthResponse


@pytest.mark.asyncio
async def test_health_endpoint_success(async_client: AsyncClient) -> None:
    """Verifies that GET /api/v1/health returns 200 OK and conforms to HealthResponse schema."""
    response = await async_client.get("/api/v1/health")

    assert response.status_code == 200
    data = response.json()

    # Validate directly against Pydantic schema
    validated = HealthResponse.model_validate(data)
    assert validated.status == "ok"
    assert validated.environment == "test"
    assert validated.version == "0.1.0"
    assert validated.database == "not_checked"


@pytest.mark.asyncio
async def test_openapi_documentation_accessible(async_client: AsyncClient) -> None:
    """Verifies that OpenAPI documentation and JSON schema are exposed properly."""
    response = await async_client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()

    assert schema["info"]["title"] == "Filament API"
    assert "/api/v1/health" in schema["paths"]
    assert "get" in schema["paths"]["/api/v1/health"]

    # Verify interactive Swagger docs return 200
    docs_response = await async_client.get("/docs")
    assert docs_response.status_code == 200


def test_production_settings_enforce_security_guards() -> None:
    """Ensures that production mode strictly disallows placeholder secrets or local DB URLs."""
    with pytest.raises(ValidationError, match="AUTH_SECRET_KEY must be configured"):
        Settings(
            ENVIRONMENT="production",
            AUTH_SECRET_KEY="replace_with_a_secure_random_key_for_local_dev",
            DATABASE_URL="postgresql+asyncpg://prod_user:secret@prod-db.example.com:5432/filament_prod",
        )

    with pytest.raises(ValidationError, match="AUTH_SECRET_KEY must be configured"):
        Settings(
            ENVIRONMENT="production",
            AUTH_SECRET_KEY="short_key",
            DATABASE_URL="postgresql+asyncpg://prod_user:secret@prod-db.example.com:5432/filament_prod",
        )

    with pytest.raises(ValidationError, match="Production DATABASE_URL cannot reference local dev database"):
        Settings(
            ENVIRONMENT="production",
            AUTH_SECRET_KEY="a_legitimate_production_secret_key_12345",
            DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:5432/filament_dev",
        )

    with pytest.raises(ValidationError, match="Wildcard CORS origins"):
        Settings(
            ENVIRONMENT="production",
            AUTH_SECRET_KEY="a_legitimate_production_secret_key_12345",
            DATABASE_URL="postgresql+asyncpg://prod_user:secret@prod-db.example.com:5432/filament_prod",
            CORS_ORIGINS=["*"],
        )


def test_development_settings_allow_local_defaults() -> None:
    """Ensures local developer settings construct without error using standard defaults."""
    dev_settings = Settings(ENVIRONMENT="development")
    assert dev_settings.ENVIRONMENT == "development"
    assert dev_settings.API_PORT == 8000
    assert dev_settings.API_V1_PREFIX == "/api/v1"


@pytest.mark.asyncio
async def test_get_db_does_not_commit_automatically(app: FastAPI, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifies that get_db yields session without committing automatically upon request completion."""
    from unittest.mock import AsyncMock, MagicMock
    from filament_api.db import session as db_session
    from fastapi import Depends
    from httpx import ASGITransport, AsyncClient

    mock_session = AsyncMock()
    mock_session.is_active = True
    mock_session.in_transaction = MagicMock(return_value=True)

    mock_factory = MagicMock()
    mock_factory.return_value.__aenter__.return_value = mock_session

    monkeypatch.setattr(db_session, "get_session_factory", lambda: mock_factory)

    @app.get("/test-db-no-auto-commit")
    async def route_no_commit(db = Depends(db_session.get_db)) -> dict:
        return {"result": "ok"}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        res = await client.get("/test-db-no-auto-commit")
        assert res.status_code == 200

    mock_session.commit.assert_not_awaited()
    mock_session.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_db_transaction_rollback_on_error(app: FastAPI, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifies that get_db rolls back active transactions when an unhandled exception is raised in route."""
    from unittest.mock import AsyncMock, MagicMock
    from filament_api.db import session as db_session
    from fastapi import Depends
    from httpx import ASGITransport, AsyncClient

    mock_session = AsyncMock()
    mock_session.is_active = True
    mock_session.in_transaction = MagicMock(return_value=True)

    mock_factory = MagicMock()
    mock_factory.return_value.__aenter__.return_value = mock_session

    monkeypatch.setattr(db_session, "get_session_factory", lambda: mock_factory)

    @app.get("/test-db-error")
    async def route_error(db = Depends(db_session.get_db)) -> dict:
        raise RuntimeError("Simulated route error")

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        res = await client.get("/test-db-error")
        assert res.status_code == 500

    mock_session.rollback.assert_awaited_once()
    mock_session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_database_engine_cleanup_lifecycle() -> None:
    """Verifies that close_db_engine handles uninitialized and disposed states gracefully."""
    from filament_api.db.session import close_db_engine
    # When already None
    await close_db_engine()
    # No exception raised

