"""Automated HTTP integration tests for POST /api/v1/claims.

DIAGNOSTIC SCOPE & LIMITATIONS:
These tests verify FastAPI routing, agent authentication dependencies, schema validation,
trusted context attribution, pre-commit response serialization, explicit endpoint transaction
ownership, rollback triggers, and sanitized error logging using mocked async sessions.
They DO NOT verify live PostgreSQL triggers, composite foreign keys, or database persistence.
"""

from datetime import datetime, timezone
from decimal import Decimal
import logging
from unittest.mock import AsyncMock, patch
import uuid

from fastapi import FastAPI
from httpx import AsyncClient
import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from filament_api.core.security import hash_api_key
from filament_api.db.session import get_db
from filament_api.models.agent import Agent
from filament_api.models.claim import Claim
from filament_api.services.context import TrustedContext
from filament_api.services.exceptions import (
    FilamentDomainError,
    UnauthorizedActorError,
    ValidationDomainError,
)


@pytest.fixture
def auth_agent() -> tuple[str, Agent]:
    """Fixture providing a valid agent and raw bearer secret."""
    raw_secret = "fil_live_test_claim_key_123"
    agent = Agent(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        name="claim-agent",
        api_key_hash=hash_api_key(raw_secret),
        is_active=True,
    )
    return raw_secret, agent


@pytest.fixture
def valid_claim_payload() -> dict:
    """Fixture providing valid payload parameters for creating a claim."""
    return {
        "subject": "database.persistence",
        "predicate": "engine_type",
        "object_value": {"engine": "postgresql", "driver": "asyncpg", "pool_size": 20},
        "raw_statement": "The project uses PostgreSQL with asyncpg connection pooling.",
        "claim_type": "fact",
        "scope": "team",
        "status": "current",
        "confidence": "0.95",
    }


# -----------------------------------------------------------------------------
# 1. Successful Claim Creation
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_claim_success(
    app: FastAPI,
    async_client: AsyncClient,
    auth_agent: tuple[str, Agent],
    valid_claim_payload: dict,
) -> None:
    """Verifies that authenticated POST /api/v1/claims returns 201 with expected fields."""
    secret, agent = auth_agent

    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.scalar.return_value = agent
    mock_session.is_active = True

    app.dependency_overrides[get_db] = lambda: mock_session

    response = await async_client.post(
        "/api/v1/claims",
        json=valid_claim_payload,
        headers={"Authorization": f"Bearer {secret}"},
    )

    assert response.status_code == 201
    data = response.json()

    # Validate response schema fields
    assert uuid.UUID(data["id"])
    assert data["workspace_id"] == str(agent.workspace_id)
    assert data["agent_id"] == str(agent.id)
    assert data["subject"] == valid_claim_payload["subject"]
    assert data["predicate"] == valid_claim_payload["predicate"]
    assert data["object_value"] == valid_claim_payload["object_value"]
    assert data["raw_statement"] == valid_claim_payload["raw_statement"]
    assert data["claim_type"] == "fact"
    assert data["scope"] == "team"
    assert data["status"] == "current"
    assert data["confidence"] == "0.95"
    assert data["version"] == 1
    assert datetime.fromisoformat(data["created_at"])
    assert datetime.fromisoformat(data["updated_at"])

    # Ensure endpoint explicitly committed once and did not roll back
    mock_session.commit.assert_awaited_once()
    mock_session.rollback.assert_not_awaited()

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_create_claim_with_explicit_matching_agent_id(
    app: FastAPI,
    async_client: AsyncClient,
    auth_agent: tuple[str, Agent],
    valid_claim_payload: dict,
) -> None:
    """Verifies that supplying the caller's own agent_id succeeds."""
    secret, agent = auth_agent

    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.scalar.return_value = agent
    mock_session.is_active = True
    app.dependency_overrides[get_db] = lambda: mock_session

    payload = {**valid_claim_payload, "agent_id": str(agent.id)}

    response = await async_client.post(
        "/api/v1/claims",
        json=payload,
        headers={"Authorization": f"Bearer {secret}"},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["agent_id"] == str(agent.id)
    mock_session.commit.assert_awaited_once()

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_create_claim_with_custom_claim_id(
    app: FastAPI,
    async_client: AsyncClient,
    auth_agent: tuple[str, Agent],
    valid_claim_payload: dict,
) -> None:
    """Verifies that supplying a custom claim_id is preserved in the response."""
    secret, agent = auth_agent

    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.scalar.return_value = agent
    mock_session.is_active = True
    app.dependency_overrides[get_db] = lambda: mock_session

    custom_id = uuid.uuid4()
    payload = {**valid_claim_payload, "claim_id": str(custom_id)}

    response = await async_client.post(
        "/api/v1/claims",
        json=payload,
        headers={"Authorization": f"Bearer {secret}"},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["id"] == str(custom_id)
    mock_session.commit.assert_awaited_once()

    app.dependency_overrides.clear()


# -----------------------------------------------------------------------------
# 2. Trusted Context Attribution & Spoofing Rejections
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_claim_rejects_extra_workspace_id(
    app: FastAPI,
    async_client: AsyncClient,
    auth_agent: tuple[str, Agent],
    valid_claim_payload: dict,
) -> None:
    """Verifies 422 when client attempts to inject a workspace_id in payload."""
    secret, agent = auth_agent
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.scalar.return_value = agent
    app.dependency_overrides[get_db] = lambda: mock_session

    payload = {**valid_claim_payload, "workspace_id": str(uuid.uuid4())}

    response = await async_client.post(
        "/api/v1/claims",
        json=payload,
        headers={"Authorization": f"Bearer {secret}"},
    )

    assert response.status_code == 422
    data = response.json()
    assert data["error"]["code"] == "VALIDATION_ERROR"
    # Extra field forbidden by schema
    assert any("workspace_id" in str(detail.get("loc")) for detail in data["error"]["details"])

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_create_claim_rejects_mismatched_agent_id(
    app: FastAPI,
    async_client: AsyncClient,
    auth_agent: tuple[str, Agent],
    valid_claim_payload: dict,
) -> None:
    """Verifies 403 Forbidden when caller supplies an agent_id different from the authenticated agent."""
    secret, agent = auth_agent
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.scalar.return_value = agent
    mock_session.is_active = True
    app.dependency_overrides[get_db] = lambda: mock_session

    spoofed_agent_id = uuid.uuid4()
    payload = {**valid_claim_payload, "agent_id": str(spoofed_agent_id)}

    response = await async_client.post(
        "/api/v1/claims",
        json=payload,
        headers={"Authorization": f"Bearer {secret}"},
    )

    assert response.status_code == 403
    data = response.json()
    assert data["error"]["code"] == "FORBIDDEN"
    assert "cannot create claims for another agent" in data["error"]["message"]

    # Transaction rolled back and never committed
    mock_session.rollback.assert_awaited()
    mock_session.commit.assert_not_awaited()

    app.dependency_overrides.clear()


# -----------------------------------------------------------------------------
# 3. Authentication & Credential Rejections
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_claim_requires_authentication(
    async_client: AsyncClient,
    valid_claim_payload: dict,
) -> None:
    """Verifies 401 when Authorization header is omitted."""
    response = await async_client.post(
        "/api/v1/claims",
        json=valid_claim_payload,
    )
    assert response.status_code == 401
    assert response.headers.get("WWW-Authenticate") == "Bearer"
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


@pytest.mark.asyncio
async def test_create_claim_rejects_unsupported_auth_scheme(
    async_client: AsyncClient,
    valid_claim_payload: dict,
) -> None:
    """Verifies 401 when Authorization scheme is not Bearer."""
    response = await async_client.post(
        "/api/v1/claims",
        json=valid_claim_payload,
        headers={"Authorization": "Basic dXNlcjpwYXNz"},
    )
    assert response.status_code == 401
    assert response.headers.get("WWW-Authenticate") == "Bearer"
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


@pytest.mark.asyncio
async def test_create_claim_rejects_empty_bearer_token(
    async_client: AsyncClient,
    valid_claim_payload: dict,
) -> None:
    """Verifies 401 when Bearer token is empty."""
    response = await async_client.post(
        "/api/v1/claims",
        json=valid_claim_payload,
        headers={"Authorization": "Bearer "},
    )
    assert response.status_code == 401
    assert response.headers.get("WWW-Authenticate") == "Bearer"
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


@pytest.mark.asyncio
async def test_create_claim_rejects_unknown_agent(
    app: FastAPI,
    async_client: AsyncClient,
    valid_claim_payload: dict,
) -> None:
    """Verifies 401 when API key hash does not match any agent."""
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.scalar.return_value = None
    app.dependency_overrides[get_db] = lambda: mock_session

    response = await async_client.post(
        "/api/v1/claims",
        json=valid_claim_payload,
        headers={"Authorization": "Bearer fil_live_unknown_agent_key_000"},
    )

    assert response.status_code == 401
    assert response.headers.get("WWW-Authenticate") == "Bearer"
    assert response.json()["error"]["message"] == "Invalid API key."

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_create_claim_rejects_inactive_agent(
    app: FastAPI,
    async_client: AsyncClient,
    valid_claim_payload: dict,
) -> None:
    """Verifies 401 when agent exists but is_active is False."""
    secret = "fil_live_inactive_agent_key"
    inactive_agent = Agent(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        name="disabled-agent",
        api_key_hash=hash_api_key(secret),
        is_active=False,
    )

    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.scalar.return_value = inactive_agent
    app.dependency_overrides[get_db] = lambda: mock_session

    response = await async_client.post(
        "/api/v1/claims",
        json=valid_claim_payload,
        headers={"Authorization": f"Bearer {secret}"},
    )

    assert response.status_code == 401
    assert response.headers.get("WWW-Authenticate") == "Bearer"
    assert response.json()["error"]["message"] == "Invalid API key."

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_create_claim_authentication_failures_are_indistinguishable(
    app: FastAPI,
    async_client: AsyncClient,
    valid_claim_payload: dict,
) -> None:
    """Verifies that unknown and inactive credentials produce identical 401 responses."""
    # 1. Unknown agent
    mock_session_unknown = AsyncMock(spec=AsyncSession)
    mock_session_unknown.scalar.return_value = None
    app.dependency_overrides[get_db] = lambda: mock_session_unknown

    unknown_res = await async_client.post(
        "/api/v1/claims",
        json=valid_claim_payload,
        headers={"Authorization": "Bearer fil_live_unknown_key_xyz"},
    )

    # 2. Inactive agent
    inactive_agent = Agent(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        name="disabled-agent",
        api_key_hash=hash_api_key("fil_live_inactive_key_abc"),
        is_active=False,
    )
    mock_session_inactive = AsyncMock(spec=AsyncSession)
    mock_session_inactive.scalar.return_value = inactive_agent
    app.dependency_overrides[get_db] = lambda: mock_session_inactive

    inactive_res = await async_client.post(
        "/api/v1/claims",
        json=valid_claim_payload,
        headers={"Authorization": "Bearer fil_live_inactive_key_abc"},
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

    app.dependency_overrides.clear()


# -----------------------------------------------------------------------------
# 4. Schema & Payload Validation Rejections
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field_name",
    ["subject", "predicate", "raw_statement"],
)
async def test_create_claim_rejects_whitespace_only_fields(
    app: FastAPI,
    async_client: AsyncClient,
    auth_agent: tuple[str, Agent],
    valid_claim_payload: dict,
    field_name: str,
) -> None:
    """Verifies 422 when required text fields contain only whitespace."""
    secret, agent = auth_agent
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.scalar.return_value = agent
    app.dependency_overrides[get_db] = lambda: mock_session

    payload = {**valid_claim_payload, field_name: "   \n\t  "}

    response = await async_client.post(
        "/api/v1/claims",
        json=payload,
        headers={"Authorization": f"Bearer {secret}"},
    )

    assert response.status_code == 422
    data = response.json()
    assert data["error"]["code"] == "VALIDATION_ERROR"

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_create_claim_rejects_unexpected_extra_fields(
    app: FastAPI,
    async_client: AsyncClient,
    auth_agent: tuple[str, Agent],
    valid_claim_payload: dict,
) -> None:
    """Verifies 422 when payload contains unknown fields due to extra='forbid'."""
    secret, agent = auth_agent
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.scalar.return_value = agent
    app.dependency_overrides[get_db] = lambda: mock_session

    payload = {**valid_claim_payload, "malicious_injected_attr": "exploit_value"}

    response = await async_client.post(
        "/api/v1/claims",
        json=payload,
        headers={"Authorization": f"Bearer {secret}"},
    )

    assert response.status_code == 422
    data = response.json()
    assert data["error"]["code"] == "VALIDATION_ERROR"
    assert any("malicious_injected_attr" in str(detail.get("loc")) for detail in data["error"]["details"])

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_create_claim_rejects_invalid_claim_type(
    app: FastAPI,
    async_client: AsyncClient,
    auth_agent: tuple[str, Agent],
    valid_claim_payload: dict,
) -> None:
    """Verifies 422 when claim_type is not an allowed literal."""
    secret, agent = auth_agent
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.scalar.return_value = agent
    app.dependency_overrides[get_db] = lambda: mock_session

    payload = {**valid_claim_payload, "claim_type": "rumor"}

    response = await async_client.post(
        "/api/v1/claims",
        json=payload,
        headers={"Authorization": f"Bearer {secret}"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_create_claim_rejects_invalid_scope(
    app: FastAPI,
    async_client: AsyncClient,
    auth_agent: tuple[str, Agent],
    valid_claim_payload: dict,
) -> None:
    """Verifies 422 when scope is not private, team, or workspace."""
    secret, agent = auth_agent
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.scalar.return_value = agent
    app.dependency_overrides[get_db] = lambda: mock_session

    payload = {**valid_claim_payload, "scope": "global"}

    response = await async_client.post(
        "/api/v1/claims",
        json=payload,
        headers={"Authorization": f"Bearer {secret}"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_create_claim_rejects_invalid_status(
    app: FastAPI,
    async_client: AsyncClient,
    auth_agent: tuple[str, Agent],
    valid_claim_payload: dict,
) -> None:
    """Verifies 422 when status is not an allowed lifecycle status."""
    secret, agent = auth_agent
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.scalar.return_value = agent
    app.dependency_overrides[get_db] = lambda: mock_session

    payload = {**valid_claim_payload, "status": "draft"}

    response = await async_client.post(
        "/api/v1/claims",
        json=payload,
        headers={"Authorization": f"Bearer {secret}"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    app.dependency_overrides.clear()


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_confidence", ["-0.10", "1.05", "2.00"])
async def test_create_claim_rejects_out_of_bounds_confidence(
    app: FastAPI,
    async_client: AsyncClient,
    auth_agent: tuple[str, Agent],
    valid_claim_payload: dict,
    bad_confidence: str,
) -> None:
    """Verifies 422 when confidence is outside [0.00, 1.00]."""
    secret, agent = auth_agent
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.scalar.return_value = agent
    app.dependency_overrides[get_db] = lambda: mock_session

    payload = {**valid_claim_payload, "confidence": bad_confidence}

    response = await async_client.post(
        "/api/v1/claims",
        json=payload,
        headers={"Authorization": f"Bearer {secret}"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    app.dependency_overrides.clear()


# -----------------------------------------------------------------------------
# 5. Domain Exception Mapping
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_claim_maps_validation_domain_error_to_422(
    app: FastAPI,
    async_client: AsyncClient,
    auth_agent: tuple[str, Agent],
    valid_claim_payload: dict,
) -> None:
    """Verifies that ValidationDomainError maps to HTTP 422 with VALIDATION_ERROR code."""
    secret, agent = auth_agent
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.scalar.return_value = agent
    mock_session.is_active = True
    app.dependency_overrides[get_db] = lambda: mock_session

    with patch(
        "filament_api.api.routes.claims.ClaimService.create_claim",
        side_effect=ValidationDomainError("Domain validation failed on predicate format."),
    ):
        response = await async_client.post(
            "/api/v1/claims",
            json=valid_claim_payload,
            headers={"Authorization": f"Bearer {secret}"},
        )

        assert response.status_code == 422
        data = response.json()
        assert data["error"]["code"] == "VALIDATION_ERROR"
        assert data["error"]["message"] == "Domain validation failed on predicate format."
        mock_session.rollback.assert_awaited()

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_create_claim_maps_filament_domain_error_to_400(
    app: FastAPI,
    async_client: AsyncClient,
    auth_agent: tuple[str, Agent],
    valid_claim_payload: dict,
) -> None:
    """Verifies that generic FilamentDomainError maps to HTTP 400 with BAD_REQUEST code."""
    secret, agent = auth_agent
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.scalar.return_value = agent
    mock_session.is_active = True
    app.dependency_overrides[get_db] = lambda: mock_session

    with patch(
        "filament_api.api.routes.claims.ClaimService.create_claim",
        side_effect=FilamentDomainError("Illegal claim operation."),
    ):
        response = await async_client.post(
            "/api/v1/claims",
            json=valid_claim_payload,
            headers={"Authorization": f"Bearer {secret}"},
        )

        assert response.status_code == 400
        data = response.json()
        assert data["error"]["code"] == "BAD_REQUEST"
        assert data["error"]["message"] == "Illegal claim operation."
        mock_session.rollback.assert_awaited()

    app.dependency_overrides.clear()


# -----------------------------------------------------------------------------
# 6. Transaction Ownership & Lifecycle
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_claim_response_validation_failure_rolls_back_without_commit(
    app: FastAPI,
    async_client: AsyncClient,
    auth_agent: tuple[str, Agent],
    valid_claim_payload: dict,
) -> None:
    """Verifies that response preparation failure triggers rollback and NEVER commits."""
    secret, agent = auth_agent
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.scalar.return_value = agent
    mock_session.is_active = True
    app.dependency_overrides[get_db] = lambda: mock_session

    with patch(
        "filament_api.api.routes.claims.ClaimResponse.model_validate",
        side_effect=ValueError("Simulated DTO serialization failure"),
    ):
        response = await async_client.post(
            "/api/v1/claims",
            json=valid_claim_payload,
            headers={"Authorization": f"Bearer {secret}"},
        )

        assert response.status_code == 500
        # Commit must NOT be called if response preparation fails
        mock_session.commit.assert_not_awaited()
        # Rollback must be triggered
        mock_session.rollback.assert_awaited()

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_create_claim_commit_failure_returns_500_and_rolls_back(
    app: FastAPI,
    async_client: AsyncClient,
    auth_agent: tuple[str, Agent],
    valid_claim_payload: dict,
) -> None:
    """Verifies that if explicit commit fails, the client receives 500 and rollback runs."""
    secret, agent = auth_agent
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.scalar.return_value = agent
    mock_session.is_active = True
    mock_session.commit.side_effect = RuntimeError("FATAL: connection terminated during commit")
    app.dependency_overrides[get_db] = lambda: mock_session

    response = await async_client.post(
        "/api/v1/claims",
        json=valid_claim_payload,
        headers={"Authorization": f"Bearer {secret}"},
    )

    assert response.status_code == 500
    data = response.json()
    assert data["error"]["code"] == "INTERNAL_SERVER_ERROR"
    assert data["error"]["message"] == "An internal server error occurred."
    assert "connection terminated" not in response.text

    mock_session.rollback.assert_awaited()

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_create_claim_commit_occurs_before_response_returned(
    app: FastAPI,
    async_client: AsyncClient,
    auth_agent: tuple[str, Agent],
    valid_claim_payload: dict,
) -> None:
    """Verifies that commit is executed before returning response to client."""
    secret, agent = auth_agent
    call_events: list[str] = []

    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.scalar.return_value = agent
    mock_session.is_active = True

    async def tracked_commit() -> None:
        call_events.append("session_committed")

    mock_session.commit.side_effect = tracked_commit
    app.dependency_overrides[get_db] = lambda: mock_session

    response = await async_client.post(
        "/api/v1/claims",
        json=valid_claim_payload,
        headers={"Authorization": f"Bearer {secret}"},
    )

    assert response.status_code == 201
    assert "session_committed" in call_events
    assert call_events.count("session_committed") == 1

    app.dependency_overrides.clear()


# -----------------------------------------------------------------------------
# 7. Safe Exception Logging (SQL & Parameter Sanitization)
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_claim_logging_sanitizes_database_exception_and_parameters(
    app: FastAPI,
    async_client: AsyncClient,
    auth_agent: tuple[str, Agent],
    valid_claim_payload: dict,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Verifies that route-level error logging does not expose SQL statements or bound parameters."""
    secret, agent = auth_agent
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.scalar.return_value = agent
    mock_session.is_active = True
    app.dependency_overrides[get_db] = lambda: mock_session

    secret_canary = "DATABASE_SECRET_PAYLOAD_PARAM_CLAIM_98765"
    db_error = IntegrityError(
        statement="INSERT INTO claims (subject, raw_statement) VALUES (:sub, :stmt)",
        params={"stmt": secret_canary},
        orig=Exception(f"violates constraint with {secret_canary}"),
    )

    with caplog.at_level(logging.ERROR):
        with patch(
            "filament_api.api.routes.claims.ClaimService.create_claim",
            side_effect=db_error,
        ):
            response = await async_client.post(
                "/api/v1/claims",
                json=valid_claim_payload,
                headers={"Authorization": f"Bearer {secret}"},
            )

    assert response.status_code == 500
    assert secret_canary not in response.text
    assert secret_canary not in caplog.text

    # Useful diagnostics must still be captured safely
    assert "sqlalchemy.exc.IntegrityError" in caplog.text
    assert "[message and parameters redacted]" in caplog.text
    assert "File " in caplog.text
    assert "create_claim" in caplog.text

    app.dependency_overrides.clear()

