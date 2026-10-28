"""Shared test fixtures for Filament API test suite."""

from collections.abc import AsyncGenerator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from filament_api.config import Settings, get_settings
from filament_api.main import create_app


@pytest.fixture(scope="session")
def test_settings() -> Settings:
    """Fixture providing dedicated test settings."""
    return Settings(
        ENVIRONMENT="test",
        DEBUG=True,
        DATABASE_URL="postgresql+asyncpg://mock_user:mock_pass@localhost:5432/mock_filament_test",
        AUTH_SECRET_KEY="test_secret_key_only_for_automated_test_runs",
    )


@pytest.fixture
def app(test_settings: Settings) -> FastAPI:
    """Fixture creating a test FastAPI application with overridden settings."""
    app_instance = create_app(settings=test_settings)
    app_instance.dependency_overrides[get_settings] = lambda: test_settings
    return app_instance


@pytest.fixture
async def async_client(app: FastAPI) -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP client fixture bound to the ASGI application for zero-network testing."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client

