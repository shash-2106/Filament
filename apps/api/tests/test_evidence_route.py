"""Automated HTTP integration tests for POST /api/v1/evidence."""

from datetime import datetime, timezone
import hashlib
import logging
from unittest.mock import AsyncMock, patch
import uuid

from fastapi import FastAPI
from httpx import AsyncClient
import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from filament_api.api.dependencies.auth import get_current_agent_context
from filament_api.core.security import hash_api_key
from filament_api.db.session import get_db
from filament_api.models.agent import Agent
from filament_api.models.evidence import Evidence
from filament_api.services.context import TrustedContext
from filament_api.services.exceptions import ValidationDomainError


@pytest.fixture
def auth_agent() -> tuple[str, Agent]:
    """Fixture providing a valid agent and raw bearer secret."""
    raw_secret = "fil_live_test_evidence_key_123"
    agent = Agent(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        name="evidence-agent",
        api_key_hash=hash_api_key(raw_secret),
        is_active=True,
    )
    return raw_secret, agent


# -----------------------------------------------------------------------------
# 1. Successful Evidence Recording
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_record_evidence_success(
    app: FastAPI,
    async_client: AsyncClient,
    auth_agent: tuple[str, Agent],
) -> None:
    """Verifies that authenticated POST /api/v1/evidence returns 201 with expected payload."""
    secret, agent = auth_agent

    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.scalar.return_value = agent

    app.dependency_overrides[get_db] = lambda: mock_session

    raw_snippet = "PostgreSQL version 16.2 was deployed to staging on port 5432."
    computed_hash = hashlib.sha256(raw_snippet.encode("utf-8")).hexdigest()

    payload = {
        "source_type": "git_commit",
        "source_uri": "git://commit/c0ffee12",
        "raw_snippet": raw_snippet,
        "metadata": {"author": "infra@example.com", "env": "staging"},
    }

    response = await async_client.post(
        "/api/v1/evidence",
        json=payload,
        headers={"Authorization": f"Bearer {secret}"},
    )

    assert response.status_code == 201
    data = response.json()

    # Validate schema fields
    assert uuid.UUID(data["id"])
    assert data["workspace_id"] == str(agent.workspace_id)
    assert data["source_type"] == "git_commit"
    assert data["source_uri"] == "git://commit/c0ffee12"
    assert data["content_hash"] == computed_hash
    assert data["raw_snippet"] == raw_snippet
    assert data["collected_by_agent"] == str(agent.id)
    assert data["collected_by_user"] is None
    assert data["metadata"] == {"author": "infra@example.com", "env": "staging"}
    assert datetime.fromisoformat(data["created_at"])

    # Ensure endpoint explicitly commits exactly once and does not roll back
    mock_session.commit.assert_awaited_once()
    mock_session.rollback.assert_not_awaited()

    app.dependency_overrides.clear()


# -----------------------------------------------------------------------------
# 2. Authentication Rejections
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_record_evidence_requires_authentication(
    app: FastAPI,
    async_client: AsyncClient,
) -> None:
    """Verifies 401 when Authorization header is omitted."""
    response = await async_client.post(
        "/api/v1/evidence",
        json={
            "source_type": "file",
            "source_uri": "README.md",
            "raw_snippet": "Valid snippet",
        },
    )
    assert response.status_code == 401
    assert response.headers.get("WWW-Authenticate") == "Bearer"
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


@pytest.mark.asyncio
async def test_record_evidence_rejects_inactive_agent(
    app: FastAPI,
    async_client: AsyncClient,
) -> None:
    """Verifies 401 when the agent exists but is_active is False."""
    secret = "fil_live_inactive_secret"
    inactive_agent = Agent(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        name="inactive-agent",
        api_key_hash=hash_api_key(secret),
        is_active=False,
    )

    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.scalar.return_value = inactive_agent
    app.dependency_overrides[get_db] = lambda: mock_session

    response = await async_client.post(
        "/api/v1/evidence",
        json={
            "source_type": "file",
            "source_uri": "README.md",
            "raw_snippet": "Valid snippet",
        },
        headers={"Authorization": f"Bearer {secret}"},
    )

    assert response.status_code == 401
    assert response.headers.get("WWW-Authenticate") == "Bearer"
    assert response.json()["error"]["message"] == "Invalid API key."

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_record_evidence_rejects_unknown_agent(
    app: FastAPI,
    async_client: AsyncClient,
) -> None:
    """Verifies 401 when key hash does not match any agent."""
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.scalar.return_value = None
    app.dependency_overrides[get_db] = lambda: mock_session

    response = await async_client.post(
        "/api/v1/evidence",
        json={
            "source_type": "file",
            "source_uri": "README.md",
            "raw_snippet": "Valid snippet",
        },
        headers={"Authorization": "Bearer fil_live_unknown_key_000"},
    )

    assert response.status_code == 401
    assert response.headers.get("WWW-Authenticate") == "Bearer"
    assert response.json()["error"]["message"] == "Invalid API key."

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_authentication_failures_are_indistinguishable_in_route(
    app: FastAPI,
    async_client: AsyncClient,
) -> None:
    """Verifies that unknown and inactive credentials produce identical 401 response envelopes."""
    # 1. Unknown agent
    mock_session_unknown = AsyncMock(spec=AsyncSession)
    mock_session_unknown.scalar.return_value = None
    app.dependency_overrides[get_db] = lambda: mock_session_unknown

    unknown_res = await async_client.post(
        "/api/v1/evidence",
        json={"source_type": "file", "source_uri": "doc.txt", "raw_snippet": "test"},
        headers={"Authorization": "Bearer fil_live_unknown_agent_key"},
    )

    # 2. Inactive agent
    inactive_agent = Agent(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        name="disabled-agent",
        api_key_hash=hash_api_key("fil_live_inactive_agent_key"),
        is_active=False,
    )
    mock_session_inactive = AsyncMock(spec=AsyncSession)
    mock_session_inactive.scalar.return_value = inactive_agent
    app.dependency_overrides[get_db] = lambda: mock_session_inactive

    inactive_res = await async_client.post(
        "/api/v1/evidence",
        json={"source_type": "file", "source_uri": "doc.txt", "raw_snippet": "test"},
        headers={"Authorization": "Bearer fil_live_inactive_agent_key"},
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
# 3. Validation Failures
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_record_evidence_rejects_invalid_source_type(
    app: FastAPI,
    async_client: AsyncClient,
    auth_agent: tuple[str, Agent],
) -> None:
    """Verifies 422 when source_type is not an allowed literal."""
    secret, agent = auth_agent
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.scalar.return_value = agent
    app.dependency_overrides[get_db] = lambda: mock_session

    response = await async_client.post(
        "/api/v1/evidence",
        json={
            "source_type": "telepathy",  # Unsupported
            "source_uri": "mind://thought",
            "raw_snippet": "Thought snippet",
        },
        headers={"Authorization": f"Bearer {secret}"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_record_evidence_rejects_whitespace_snippet(
    app: FastAPI,
    async_client: AsyncClient,
    auth_agent: tuple[str, Agent],
) -> None:
    """Verifies 422 when raw_snippet is whitespace-only."""
    secret, agent = auth_agent
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.scalar.return_value = agent
    app.dependency_overrides[get_db] = lambda: mock_session

    response = await async_client.post(
        "/api/v1/evidence",
        json={
            "source_type": "file",
            "source_uri": "file.txt",
            "raw_snippet": "   \n\t  ",
        },
        headers={"Authorization": f"Bearer {secret}"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_record_evidence_rejects_caller_supplied_identity_overrides(
    app: FastAPI,
    async_client: AsyncClient,
    auth_agent: tuple[str, Agent],
) -> None:
    """Verifies 422 when client attempts to inject forbidden identity fields in payload."""
    secret, agent = auth_agent
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.scalar.return_value = agent
    app.dependency_overrides[get_db] = lambda: mock_session

    # Attempt to spoof tenant workspace or collected_by_agent
    response = await async_client.post(
        "/api/v1/evidence",
        json={
            "source_type": "file",
            "source_uri": "README.md",
            "raw_snippet": "Valid snippet",
            "workspace_id": str(uuid.uuid4()),
            "collected_by_agent": str(uuid.uuid4()),
        },
        headers={"Authorization": f"Bearer {secret}"},
    )

    # Extra fields forbidden by RecordEvidenceParams
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_record_evidence_rejects_mismatched_content_hash(
    app: FastAPI,
    async_client: AsyncClient,
    auth_agent: tuple[str, Agent],
) -> None:
    """Verifies 422 when caller supplies an incorrect content_hash for the raw_snippet."""
    secret, agent = auth_agent
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.scalar.return_value = agent
    app.dependency_overrides[get_db] = lambda: mock_session

    response = await async_client.post(
        "/api/v1/evidence",
        json={
            "source_type": "file",
            "source_uri": "README.md",
            "raw_snippet": "Valid snippet content",
            "content_hash": "0" * 64,  # Incorrect hash
        },
        headers={"Authorization": f"Bearer {secret}"},
    )

    assert response.status_code == 422
    data = response.json()
    assert data["error"]["code"] == "VALIDATION_ERROR"
    assert "does not match computed hash" in data["error"]["message"]

    app.dependency_overrides.clear()


# -----------------------------------------------------------------------------
# 4. Service Call & Error Masking Integration
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_record_evidence_delegates_to_service_cleanly(
    app: FastAPI,
    async_client: AsyncClient,
    auth_agent: tuple[str, Agent],
) -> None:
    """Verifies that route passes validated params and trusted context to EvidenceService."""
    secret, agent = auth_agent
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.scalar.return_value = agent
    app.dependency_overrides[get_db] = lambda: mock_session

    expected_evidence = Evidence(
        id=uuid.uuid4(),
        workspace_id=agent.workspace_id,
        source_type="user_turn",
        source_uri="chat://turn/1",
        content_hash="a" * 64,
        raw_snippet="User prompt text",
        collected_by_agent=agent.id,
        collected_by_user=None,
        metadata_={"turn": 1},
        created_at=datetime.now(timezone.utc),
    )

    with patch(
        "filament_api.api.routes.evidence.EvidenceService.record_evidence",
        new_callable=AsyncMock,
    ) as mock_record:
        mock_record.return_value = expected_evidence

        response = await async_client.post(
            "/api/v1/evidence",
            json={
                "source_type": "user_turn",
                "source_uri": "chat://turn/1",
                "raw_snippet": "User prompt text",
                "content_hash": "a" * 64,
                "metadata": {"turn": 1},
            },
            headers={"Authorization": f"Bearer {secret}"},
        )

        assert response.status_code == 201
        assert response.json()["id"] == str(expected_evidence.id)

        # Assert arguments passed to EvidenceService
        mock_record.assert_awaited_once()
        _, kwargs = mock_record.call_args
        context: TrustedContext = kwargs["context"]
        assert context.workspace_id == agent.workspace_id
        assert context.actor_id == agent.id
        assert context.is_agent is True

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_record_evidence_database_failure_does_not_leak_internals(
    app: FastAPI,
    async_client: AsyncClient,
    auth_agent: tuple[str, Agent],
) -> None:
    """Verifies that an unhandled database error returns 500 without leaking SQL or trace."""
    secret, agent = auth_agent
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.scalar.return_value = agent
    app.dependency_overrides[get_db] = lambda: mock_session

    with patch(
        "filament_api.api.routes.evidence.EvidenceService.record_evidence",
        side_effect=RuntimeError("FATAL: connection to server at 'db.internal' failed"),
    ):
        response = await async_client.post(
            "/api/v1/evidence",
            json={
                "source_type": "file",
                "source_uri": "file.txt",
                "raw_snippet": "some content",
            },
            headers={"Authorization": f"Bearer {secret}"},
        )

        assert response.status_code == 500
        # Ensure raw SQL or internal host connection details are suppressed
        assert "db.internal" not in response.text
        assert "FATAL" not in response.text

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_record_evidence_logging_sanitizes_database_exception_and_parameters(
    app: FastAPI,
    async_client: AsyncClient,
    auth_agent: tuple[str, Agent],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Verifies that route-level error logging does not expose SQL statements or bound parameters."""
    secret, agent = auth_agent
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.scalar.return_value = agent
    app.dependency_overrides[get_db] = lambda: mock_session

    secret_canary = "DATABASE_SECRET_PAYLOAD_PARAM_98765"
    db_error = IntegrityError(
        statement="INSERT INTO evidence (raw_snippet) VALUES (:snippet)",
        params={"snippet": secret_canary},
        orig=Exception(f"violates constraint with {secret_canary}"),
    )

    with caplog.at_level(logging.ERROR):
        with patch(
            "filament_api.api.routes.evidence.EvidenceService.record_evidence",
            side_effect=db_error,
        ):
            response = await async_client.post(
                "/api/v1/evidence",
                json={
                    "source_type": "file",
                    "source_uri": "file.txt",
                    "raw_snippet": "valid content",
                },
                headers={"Authorization": f"Bearer {secret}"},
            )

    assert response.status_code == 500
    assert secret_canary not in response.text
    assert secret_canary not in caplog.text

    # Useful diagnostics must still be captured
    assert "sqlalchemy.exc.IntegrityError" in caplog.text
    assert "[message and parameters redacted]" in caplog.text
    assert "File " in caplog.text
    assert "record_evidence" in caplog.text

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_global_unhandled_exception_logging_sanitizes_database_exception(
    app: FastAPI,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Verifies that global exception handler sanitizes database exceptions and redacts secrets."""
    from httpx import ASGITransport

    secret_canary = "GLOBAL_UNHANDLED_SECRET_PAYLOAD_54321"

    @app.get("/test-unhandled-database-failure")
    async def failing_endpoint():
        raise IntegrityError(
            statement="SELECT * FROM secret_table WHERE token = :token",
            params={"token": secret_canary},
            orig=Exception(f"Database deadlocked on {secret_canary}"),
        )

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        with caplog.at_level(logging.ERROR):
            response = await client.get("/test-unhandled-database-failure")

    assert response.status_code == 500
    assert secret_canary not in response.text
    assert secret_canary not in caplog.text

    assert "sqlalchemy.exc.IntegrityError" in caplog.text
    assert "[message and parameters redacted]" in caplog.text
    assert "File " in caplog.text
    assert "failing_endpoint" in caplog.text


@pytest.mark.asyncio
async def test_health_endpoint_remains_public_and_functional(
    async_client: AsyncClient,
) -> None:
    """Verifies GET /api/v1/health continues to operate publicly without auth."""
    response = await async_client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["database"] == "not_checked"


# -----------------------------------------------------------------------------
# 5. Transaction Ownership & Lifecycle Tests
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_record_evidence_commit_failure_returns_500_and_rolls_back(
    app: FastAPI,
    async_client: AsyncClient,
    auth_agent: tuple[str, Agent],
) -> None:
    """Verifies that if explicit commit fails, the client receives 500 (NOT 201) and rollback runs."""
    secret, agent = auth_agent
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.scalar.return_value = agent
    mock_session.commit.side_effect = RuntimeError("FATAL: connection terminated during commit")
    app.dependency_overrides[get_db] = lambda: mock_session

    response = await async_client.post(
        "/api/v1/evidence",
        json={
            "source_type": "file",
            "source_uri": "src/main.py",
            "raw_snippet": "import os",
        },
        headers={"Authorization": f"Bearer {secret}"},
    )

    assert response.status_code == 500
    data = response.json()
    assert data["error"]["code"] == "INTERNAL_SERVER_ERROR"
    assert data["error"]["message"] == "An internal server error occurred."
    assert "connection terminated" not in response.text

    # Rollback must be awaited when commit fails
    mock_session.rollback.assert_awaited()

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_record_evidence_commit_occurs_before_response_returned(
    app: FastAPI,
    async_client: AsyncClient,
    auth_agent: tuple[str, Agent],
) -> None:
    """Verifies that commit is executed before returning response to client."""
    secret, agent = auth_agent
    call_events: list[str] = []

    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.scalar.return_value = agent

    async def tracked_commit() -> None:
        call_events.append("session_committed")

    mock_session.commit.side_effect = tracked_commit
    app.dependency_overrides[get_db] = lambda: mock_session

    response = await async_client.post(
        "/api/v1/evidence",
        json={
            "source_type": "file",
            "source_uri": "src/main.py",
            "raw_snippet": "print('hello')",
        },
        headers={"Authorization": f"Bearer {secret}"},
    )

    assert response.status_code == 201
    assert "session_committed" in call_events
    assert call_events.count("session_committed") == 1

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_record_evidence_response_validation_failure_rolls_back_without_commit(
    app: FastAPI,
    async_client: AsyncClient,
    auth_agent: tuple[str, Agent],
) -> None:
    """Verifies that response preparation failure triggers rollback and NEVER commits."""
    secret, agent = auth_agent
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.scalar.return_value = agent
    app.dependency_overrides[get_db] = lambda: mock_session

    with patch(
        "filament_api.api.routes.evidence.EvidenceResponse.model_validate",
        side_effect=ValueError("Simulated DTO serialization failure"),
    ):
        response = await async_client.post(
            "/api/v1/evidence",
            json={
                "source_type": "file",
                "source_uri": "src/main.py",
                "raw_snippet": "sample code",
            },
            headers={"Authorization": f"Bearer {secret}"},
        )

        assert response.status_code == 500
        # Commit must NOT be called if response preparation fails
        mock_session.commit.assert_not_awaited()
        # Rollback must be triggered
        mock_session.rollback.assert_awaited()

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_session_closed_in_both_success_and_failure_paths() -> None:
    """Verifies that get_db closes the session reliably via context manager in both paths."""
    from contextlib import asynccontextmanager
    from unittest.mock import MagicMock
    from filament_api.db import session as db_session

    # Track lifecycle calls
    events: list[str] = []

    mock_session = AsyncMock(spec=AsyncSession)
    mock_cm = MagicMock()

    async def cm_aenter(*args):
        events.append("enter")
        return mock_session

    async def cm_aexit(*args):
        events.append("exit")
        return None

    mock_cm.__aenter__ = cm_aenter
    mock_cm.__aexit__ = cm_aexit

    mock_factory = MagicMock(return_value=mock_cm)

    # 1. Success path
    with patch.object(db_session, "get_session_factory", return_value=mock_factory):
        async with asynccontextmanager(db_session.get_db)() as s:
            assert s is mock_session
            events.append("used")

    assert events == ["enter", "used", "exit"]

    # 2. Failure path (exception escapes yield as managed by FastAPI AsyncExitStack)
    events.clear()
    with patch.object(db_session, "get_session_factory", return_value=mock_factory):
        with pytest.raises(RuntimeError, match="Endpoint exploded"):
            async with asynccontextmanager(db_session.get_db)() as s:
                events.append("used_err")
                raise RuntimeError("Endpoint exploded")

    assert events == ["enter", "used_err", "exit"]
    mock_session.rollback.assert_awaited()


# -----------------------------------------------------------------------------
# 6. Security & Error Envelope Standardization Tests
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_validation_error_handler_strips_submitted_secret(
    app: FastAPI,
    async_client: AsyncClient,
    auth_agent: tuple[str, Agent],
) -> None:
    """Verifies that raw submitted secrets in invalid parameters are NOT echoed in 422 errors."""
    secret, agent = auth_agent
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.scalar.return_value = agent
    app.dependency_overrides[get_db] = lambda: mock_session

    leak_canary = "VERY_SECRET_PASSPHRASE_DO_NOT_LEAK_INTO_RESPONSES"

    response = await async_client.post(
        "/api/v1/evidence",
        json={
            "source_type": leak_canary,  # Invalid literal enum
            "source_uri": "README.md",
            "raw_snippet": "valid content",
        },
        headers={"Authorization": f"Bearer {secret}"},
    )

    assert response.status_code == 422
    data = response.json()
    assert data["error"]["code"] == "VALIDATION_ERROR"
    assert data["error"]["message"] == "Request validation failed."

    # Crucial security assertion: the raw invalid secret input must NOT appear in response body
    assert leak_canary not in response.text

    # Useful error context must still be present
    details = data["error"]["details"]
    assert len(details) > 0
    assert details[0]["loc"] == ["body", "source_type"]
    assert details[0]["type"] == "literal_error"
    assert "Input should be 'file'" in details[0]["msg"]

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_standardized_http_exceptions_unknown_route_404(
    async_client: AsyncClient,
) -> None:
    """Verifies that Starlette router 404 conforms to the standard error envelope."""
    response = await async_client.get("/api/v1/nonexistent_route_404")
    assert response.status_code == 404
    data = response.json()
    assert data == {
        "error": {
            "code": "NOT_FOUND",
            "message": "Not Found",
        }
    }


@pytest.mark.asyncio
async def test_standardized_http_exceptions_unsupported_method_405(
    async_client: AsyncClient,
) -> None:
    """Verifies that Starlette router 405 preserves Allow headers and standard error envelope."""
    response = await async_client.put("/api/v1/health")
    assert response.status_code == 405
    assert response.headers.get("allow") is not None
    data = response.json()
    assert data == {
        "error": {
            "code": "METHOD_NOT_ALLOWED",
            "message": "Method Not Allowed",
        }
    }
