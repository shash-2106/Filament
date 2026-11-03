"""Automated unit and endpoint tests for FastAPI agent authentication dependency.

DIAGNOSTIC SCOPE & LIMITATIONS:
These tests verify credential extraction, scheme validation, SHA-256 hash lookup,
constant-time verification, active status enforcement, and TrustedContext construction
using in-memory mocked sessions and ASGI test transports.
They DO NOT verify PostgreSQL index lookup performance, live connection handling,
or PostgreSQL runtime database behavior.
"""

import hashlib
from unittest.mock import AsyncMock
import uuid

from fastapi import Depends, FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
import pytest

from filament_api.api.dependencies.auth import get_current_agent_context
from filament_api.core.security import MAX_TOKEN_LENGTH, hash_api_key, verify_api_key_hash
from filament_api.db.session import get_db
from filament_api.models.agent import Agent
from filament_api.services.context import TrustedContext


# -----------------------------------------------------------------------------
# 1. Cryptographic Primitive Tests
# -----------------------------------------------------------------------------

def test_hash_api_key_consistent_and_lowercase() -> None:
    """Verifies SHA-256 calculation format and determinism."""
    raw_token = "fil_live_abc123secret"
    expected = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

    assert hash_api_key(raw_token) == expected
    assert len(hash_api_key(raw_token)) == 64
    assert hash_api_key(raw_token) == hash_api_key(raw_token).lower()


def test_verify_api_key_hash_constant_time() -> None:
    """Verifies constant-time comparison against matching and non-matching hashes."""
    raw_token = "fil_live_secret_key"
    correct_hash = hash_api_key(raw_token)
    wrong_hash = "0" * 64

    assert verify_api_key_hash(raw_token, correct_hash) is True
    assert verify_api_key_hash(raw_token, wrong_hash) is False
    assert verify_api_key_hash("wrong_token", correct_hash) is False


# -----------------------------------------------------------------------------
# 2. Test Fixtures & App for Dependency Integration
# -----------------------------------------------------------------------------

@pytest.fixture
def test_app() -> FastAPI:
    """Create a minimal test FastAPI application with protected probe route and error handler."""
    from fastapi.responses import JSONResponse

    app = FastAPI()

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request, exc: HTTPException) -> JSONResponse:
        content = exc.detail if isinstance(exc.detail, dict) and "error" in exc.detail else {
            "error": {"code": "UNAUTHORIZED", "message": str(exc.detail)}
        }
        return JSONResponse(status_code=exc.status_code, content=content, headers=exc.headers)

    @app.post("/test-protected-probe")
    async def probe_endpoint(
        body: dict,
        context: TrustedContext = Depends(get_current_agent_context),
    ) -> dict:
        # Return only the verified context to inspect derived identities
        return {
            "authenticated_workspace_id": str(context.workspace_id),
            "authenticated_agent_id": str(context.actor_id),
            "is_agent": context.is_agent,
        }

    return app


# -----------------------------------------------------------------------------
# 3. HTTP Authentication Tests
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_missing_authorization_header(test_app: FastAPI) -> None:
    """Verifies 401 when Authorization header is omitted."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/test-protected-probe", json={})

    assert response.status_code == 401
    assert response.headers.get("WWW-Authenticate") == "Bearer"
    data = response.json()
    assert data["error"]["code"] == "UNAUTHORIZED"
    assert "Missing Authorization header" in data["error"]["message"]


@pytest.mark.asyncio
async def test_unsupported_authorization_scheme(test_app: FastAPI) -> None:
    """Verifies 401 when a non-Bearer scheme is provided (e.g. Basic, Token)."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/test-protected-probe",
            json={},
            headers={"Authorization": "Basic dXNlcjpwYXNz"},
        )

    assert response.status_code == 401
    assert response.headers.get("WWW-Authenticate") == "Bearer"
    data = response.json()
    assert data["error"]["code"] == "UNAUTHORIZED"
    assert "Expected 'Bearer <token>'" in data["error"]["message"]


@pytest.mark.asyncio
async def test_empty_or_whitespace_bearer_token(test_app: FastAPI) -> None:
    """Verifies 401 when Bearer scheme is present but token string is empty."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Empty token
        res1 = await client.post(
            "/test-protected-probe",
            json={},
            headers={"Authorization": "Bearer"},
        )
        assert res1.status_code == 401
        assert res1.headers.get("WWW-Authenticate") == "Bearer"

        # Whitespace-only token
        res2 = await client.post(
            "/test-protected-probe",
            json={},
            headers={"Authorization": "Bearer    "},
        )
        assert res2.status_code == 401
        assert res2.headers.get("WWW-Authenticate") == "Bearer"
        assert "empty" in res2.json()["error"]["message"]


@pytest.mark.asyncio
async def test_excessively_long_token_rejected(test_app: FastAPI) -> None:
    """Verifies 401 when token length exceeds MAX_TOKEN_LENGTH (DoS mitigation)."""
    transport = ASGITransport(app=test_app)
    oversized_token = "a" * (MAX_TOKEN_LENGTH + 10)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/test-protected-probe",
            json={},
            headers={"Authorization": f"Bearer {oversized_token}"},
        )

    assert response.status_code == 401
    assert "maximum permitted length" in response.json()["error"]["message"]


@pytest.mark.asyncio
async def test_unknown_api_key_returns_generic_401(test_app: FastAPI) -> None:
    """Verifies 401 when token hash does not match any registered agent."""
    mock_session = AsyncMock()
    mock_session.scalar.return_value = None  # Agent not found

    test_app.dependency_overrides[get_db] = lambda: mock_session

    secret_key = "fil_live_unknown_key_999"
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/test-protected-probe",
            json={},
            headers={"Authorization": f"Bearer {secret_key}"},
        )

    assert response.status_code == 401
    assert response.headers.get("WWW-Authenticate") == "Bearer"
    data = response.json()
    assert data["error"]["code"] == "UNAUTHORIZED"
    assert data["error"]["message"] == "Invalid API key."

    # Verify no credential leakage in error body or headers
    assert secret_key not in response.text
    assert hash_api_key(secret_key) not in response.text

    test_app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_inactive_agent_rejected_with_401(test_app: FastAPI) -> None:
    """Verifies 401 when agent exists but is_active is False."""
    secret_key = "fil_live_inactive_agent_key"
    key_hash = hash_api_key(secret_key)

    mock_agent = Agent(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        name="disabled-worker",
        api_key_hash=key_hash,
        is_active=False,  # Disabled account
    )

    mock_session = AsyncMock()
    mock_session.scalar.return_value = mock_agent

    test_app.dependency_overrides[get_db] = lambda: mock_session

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/test-protected-probe",
            json={},
            headers={"Authorization": f"Bearer {secret_key}"},
        )

    assert response.status_code == 401
    assert response.headers.get("WWW-Authenticate") == "Bearer"
    data = response.json()
    assert data["error"]["code"] == "UNAUTHORIZED"
    assert data["error"]["message"] == "Invalid API key."
    assert secret_key not in response.text

    test_app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_unknown_and_inactive_agents_produce_indistinguishable_responses(test_app: FastAPI) -> None:
    """Verifies that unknown and inactive credentials produce identical external responses."""
    # 1. Unknown agent
    mock_session_unknown = AsyncMock()
    mock_session_unknown.scalar.return_value = None
    test_app.dependency_overrides[get_db] = lambda: mock_session_unknown

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        unknown_res = await client.post(
            "/test-protected-probe",
            json={},
            headers={"Authorization": "Bearer fil_live_unknown_token"},
        )

    # 2. Inactive agent
    mock_agent = Agent(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        name="disabled-worker",
        api_key_hash=hash_api_key("fil_live_inactive_token"),
        is_active=False,
    )
    mock_session_inactive = AsyncMock()
    mock_session_inactive.scalar.return_value = mock_agent
    test_app.dependency_overrides[get_db] = lambda: mock_session_inactive

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        inactive_res = await client.post(
            "/test-protected-probe",
            json={},
            headers={"Authorization": "Bearer fil_live_inactive_token"},
        )

    assert unknown_res.status_code == 401
    assert inactive_res.status_code == 401
    assert unknown_res.headers.get("WWW-Authenticate") == inactive_res.headers.get("WWW-Authenticate") == "Bearer"
    assert unknown_res.json() == inactive_res.json() == {
        "error": {
            "code": "UNAUTHORIZED",
            "message": "Invalid API key.",
        }
    }

    test_app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_active_agent_produces_trusted_context(test_app: FastAPI) -> None:
    """Verifies 200 OK and database-derived TrustedContext for valid active agent."""
    secret_key = "fil_live_valid_agent_key_456"
    key_hash = hash_api_key(secret_key)

    expected_agent_id = uuid.uuid4()
    expected_workspace_id = uuid.uuid4()

    mock_agent = Agent(
        id=expected_agent_id,
        workspace_id=expected_workspace_id,
        name="architect-agent",
        api_key_hash=key_hash,
        is_active=True,
    )

    mock_session = AsyncMock()
    mock_session.scalar.return_value = mock_agent

    test_app.dependency_overrides[get_db] = lambda: mock_session

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/test-protected-probe",
            json={},
            headers={"Authorization": f"Bearer {secret_key}"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["authenticated_workspace_id"] == str(expected_workspace_id)
    assert data["authenticated_agent_id"] == str(expected_agent_id)
    assert data["is_agent"] is True

    test_app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_caller_supplied_identity_values_ignored(test_app: FastAPI) -> None:
    """Verifies that client cannot override workspace_id or agent_id via payload."""
    secret_key = "fil_live_valid_agent_key_789"
    key_hash = hash_api_key(secret_key)

    legitimate_agent_id = uuid.uuid4()
    legitimate_workspace_id = uuid.uuid4()

    mock_agent = Agent(
        id=legitimate_agent_id,
        workspace_id=legitimate_workspace_id,
        name="coder-agent",
        api_key_hash=key_hash,
        is_active=True,
    )

    mock_session = AsyncMock()
    mock_session.scalar.return_value = mock_agent

    test_app.dependency_overrides[get_db] = lambda: mock_session

    spoofed_workspace_id = str(uuid.uuid4())
    spoofed_agent_id = str(uuid.uuid4())

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Client attempts to spoof tenant and agent identity in request body
        response = await client.post(
            "/test-protected-probe",
            json={
                "workspace_id": spoofed_workspace_id,
                "agent_id": spoofed_agent_id,
                "actor_type": "user",
            },
            headers={"Authorization": f"Bearer {secret_key}"},
        )

    assert response.status_code == 200
    data = response.json()

    # Authenticated identities MUST match the database record, NOT the spoofed payload
    assert data["authenticated_workspace_id"] == str(legitimate_workspace_id)
    assert data["authenticated_agent_id"] == str(legitimate_agent_id)
    assert data["authenticated_workspace_id"] != spoofed_workspace_id
    assert data["authenticated_agent_id"] != spoofed_agent_id

    test_app.dependency_overrides.clear()
