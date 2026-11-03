"""Automated HTTP integration tests for GET /api/v1/claims/{claim_id}.

DIAGNOSTIC SCOPE & LIMITATIONS:
These tests verify claim retrieval, scope visibility rules (private, team fail-closed, workspace),
linked evidence provenance formatting, cross-tenant isolation boundaries, read-only guarantees
(no commits or audit event emissions), and safe error logging using mocked async sessions.
They DO NOT verify live PostgreSQL database execution.
"""

from datetime import datetime, timezone
from decimal import Decimal
import logging
from unittest.mock import AsyncMock, MagicMock, patch
import uuid

from fastapi import FastAPI
from httpx import AsyncClient
import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from filament_api.core.security import hash_api_key
from filament_api.db.session import get_db
from filament_api.models.agent import Agent
from filament_api.models.claim import Claim, ClaimEvidence
from filament_api.models.evidence import Evidence


@pytest.fixture
def auth_agent() -> tuple[str, Agent]:
    """Fixture providing a primary valid agent and raw bearer secret."""
    raw_secret = "fil_live_test_retrieval_agent_key_1"
    agent = Agent(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        name="retrieval-agent",
        api_key_hash=hash_api_key(raw_secret),
        is_active=True,
    )
    return raw_secret, agent


@pytest.fixture
def peer_agent(auth_agent: tuple[str, Agent]) -> tuple[str, Agent]:
    """Fixture providing a second active agent within the SAME workspace."""
    _, primary_agent = auth_agent
    raw_secret = "fil_live_test_peer_agent_key_2"
    agent = Agent(
        id=uuid.uuid4(),
        workspace_id=primary_agent.workspace_id,  # Same workspace!
        name="peer-agent",
        api_key_hash=hash_api_key(raw_secret),
        is_active=True,
    )
    return raw_secret, agent


def make_test_claim(
    agent: Agent,
    scope: str = "workspace",
    claim_id: uuid.UUID | None = None,
    workspace_id: uuid.UUID | None = None,
) -> Claim:
    """Helper to create a test claim model instance."""
    return Claim(
        id=claim_id or uuid.uuid4(),
        workspace_id=workspace_id or agent.workspace_id,
        agent_id=agent.id,
        claim_type="fact",
        subject="database.persistence",
        predicate="engine_type",
        object_value={"engine": "postgresql", "driver": "asyncpg"},
        raw_statement="The project uses PostgreSQL with asyncpg.",
        scope=scope,
        status="current",
        confidence=Decimal("0.95"),
        version=1,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def make_test_link(
    claim: Claim,
    evidence_id: uuid.UUID | None = None,
    support_type: str = "supports",
    confidence_weight: Decimal = Decimal("1.00"),
    extraction_notes: str | None = None,
    source_type: str = "git_commit",
) -> ClaimEvidence:
    """Helper to create a test ClaimEvidence model instance with mock Evidence relationship."""
    ev_id = evidence_id or uuid.uuid4()
    mock_evidence = Evidence(
        id=ev_id,
        workspace_id=claim.workspace_id,
        source_type=source_type,
        source_uri="git://commit/123",
        content_hash="f" * 64,
        raw_snippet="Code snippet",
        created_at=datetime.now(timezone.utc),
    )
    link = ClaimEvidence(
        workspace_id=claim.workspace_id,
        claim_id=claim.id,
        evidence_id=ev_id,
        support_type=support_type,
        confidence_weight=confidence_weight,
        extraction_notes=extraction_notes,
        created_at=datetime.now(timezone.utc),
    )
    link.evidence = mock_evidence
    return link


def make_mock_session(agent: Agent, claim: Claim | None = None, links: list[ClaimEvidence] | None = None):
    """Creates a mock AsyncSession that returns agent for auth, claim for lookup, and links."""
    mock_session = AsyncMock(spec=AsyncSession)

    async def scalar_handler(stmt):
        entity_type = stmt.column_descriptions[0]["type"]
        if entity_type == Agent:
            return agent
        if entity_type == Claim:
            return claim
        return None

    mock_session.scalar.side_effect = scalar_handler

    mock_result = MagicMock()
    mock_result.all.return_value = links or []
    mock_session.scalars.return_value = mock_result
    mock_session.is_active = True
    return mock_session


# -----------------------------------------------------------------------------
# 1. Successful Retrieval (No Evidence & With Evidence)
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_claim_success_without_linked_evidence(
    app: FastAPI,
    async_client: AsyncClient,
    auth_agent: tuple[str, Agent],
) -> None:
    """Verifies that an existing claim without linked evidence returns 200 with empty evidence list."""
    secret, agent = auth_agent
    claim = make_test_claim(agent, scope="workspace")

    mock_session = make_mock_session(agent, claim=claim, links=[])
    app.dependency_overrides[get_db] = lambda: mock_session

    response = await async_client.get(
        f"/api/v1/claims/{claim.id}",
        headers={"Authorization": f"Bearer {secret}"},
    )

    assert response.status_code == 200
    data = response.json()

    # Validate claim structure
    assert data["claim"]["id"] == str(claim.id)
    assert data["claim"]["workspace_id"] == str(agent.workspace_id)
    assert data["claim"]["agent_id"] == str(agent.id)
    assert data["claim"]["subject"] == "database.persistence"
    assert data["claim"]["predicate"] == "engine_type"
    assert data["claim"]["object_value"] == {"engine": "postgresql", "driver": "asyncpg"}
    assert data["claim"]["raw_statement"] == "The project uses PostgreSQL with asyncpg."
    assert data["claim"]["scope"] == "workspace"
    assert data["claim"]["status"] == "current"
    assert data["claim"]["confidence"] == "0.95"
    assert data["claim"]["version"] == 1
    assert datetime.fromisoformat(data["claim"]["created_at"])
    assert datetime.fromisoformat(data["claim"]["updated_at"])

    # Validate empty evidence provenance
    assert data["evidence"] == []
    assert data["provenance"] == []

    # Read-only verification: no commit, no rollback, no add
    mock_session.commit.assert_not_awaited()
    mock_session.add.assert_not_called()

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_get_claim_success_with_multiple_linked_evidence(
    app: FastAPI,
    async_client: AsyncClient,
    auth_agent: tuple[str, Agent],
) -> None:
    """Verifies that a claim with multiple linked evidence records returns all links with relationship metadata."""
    secret, agent = auth_agent
    claim = make_test_claim(agent, scope="workspace")

    link1 = make_test_link(
        claim,
        support_type="supports",
        confidence_weight=Decimal("1.00"),
        extraction_notes="Explicit architectural decision record.",
        source_type="file",
    )
    link2 = make_test_link(
        claim,
        support_type="refutes",
        confidence_weight=Decimal("0.60"),
        extraction_notes="Contradictory pull request comment.",
        source_type="git_commit",
    )

    mock_session = make_mock_session(agent, claim=claim, links=[link1, link2])
    app.dependency_overrides[get_db] = lambda: mock_session

    response = await async_client.get(
        f"/api/v1/claims/{claim.id}",
        headers={"Authorization": f"Bearer {secret}"},
    )

    assert response.status_code == 200
    data = response.json()

    assert data["claim"]["id"] == str(claim.id)
    assert len(data["evidence"]) == 2

    ev1 = data["evidence"][0]
    assert ev1["evidence_id"] == str(link1.evidence_id)
    assert ev1["support_type"] == "supports"
    assert ev1["confidence_weight"] == "1.00"
    assert ev1["extraction_notes"] == "Explicit architectural decision record."
    assert ev1["source_type"] == "file"
    assert datetime.fromisoformat(ev1["created_at"])

    # Ensure sensitive fields are NOT exposed in minimal evidence representation
    assert "raw_snippet" not in ev1
    assert "source_uri" not in ev1
    assert "metadata" not in ev1

    ev2 = data["evidence"][1]
    assert ev2["evidence_id"] == str(link2.evidence_id)
    assert ev2["support_type"] == "refutes"
    assert ev2["confidence_weight"] == "0.60"
    assert ev2["extraction_notes"] == "Contradictory pull request comment."
    assert ev2["source_type"] == "git_commit"

    # Confirm read-only operation
    mock_session.commit.assert_not_awaited()
    mock_session.add.assert_not_called()

    app.dependency_overrides.clear()


# -----------------------------------------------------------------------------
# 2. Scope Visibility Rules (Workspace, Private, Team Fail-Closed)
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_claim_workspace_scope_visible_to_peer_agent(
    app: FastAPI,
    async_client: AsyncClient,
    auth_agent: tuple[str, Agent],
    peer_agent: tuple[str, Agent],
) -> None:
    """Verifies that a 'workspace' scoped claim is visible to any peer agent in the same workspace."""
    _, author_agent = auth_agent
    peer_secret, peer_agent_obj = peer_agent

    claim = make_test_claim(author_agent, scope="workspace")

    # Mock session authenticate as PEER agent
    mock_session = make_mock_session(peer_agent_obj, claim=claim, links=[])
    app.dependency_overrides[get_db] = lambda: mock_session

    response = await async_client.get(
        f"/api/v1/claims/{claim.id}",
        headers={"Authorization": f"Bearer {peer_secret}"},
    )

    assert response.status_code == 200
    assert response.json()["claim"]["id"] == str(claim.id)

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_get_claim_private_scope_visible_to_author(
    app: FastAPI,
    async_client: AsyncClient,
    auth_agent: tuple[str, Agent],
) -> None:
    """Verifies that a 'private' claim is readable by its owning author agent."""
    secret, agent = auth_agent
    claim = make_test_claim(agent, scope="private")

    mock_session = make_mock_session(agent, claim=claim, links=[])
    app.dependency_overrides[get_db] = lambda: mock_session

    response = await async_client.get(
        f"/api/v1/claims/{claim.id}",
        headers={"Authorization": f"Bearer {secret}"},
    )

    assert response.status_code == 200
    assert response.json()["claim"]["id"] == str(claim.id)

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_get_claim_private_scope_hidden_from_peer_agent_with_404(
    app: FastAPI,
    async_client: AsyncClient,
    auth_agent: tuple[str, Agent],
    peer_agent: tuple[str, Agent],
) -> None:
    """Verifies that a 'private' claim returns 404 when requested by a different agent in the same workspace."""
    _, author_agent = auth_agent
    peer_secret, peer_agent_obj = peer_agent

    claim = make_test_claim(author_agent, scope="private")

    # Authenticate as peer agent
    mock_session = make_mock_session(peer_agent_obj, claim=claim, links=[])
    app.dependency_overrides[get_db] = lambda: mock_session

    response = await async_client.get(
        f"/api/v1/claims/{claim.id}",
        headers={"Authorization": f"Bearer {peer_secret}"},
    )

    assert response.status_code == 404
    data = response.json()
    assert data["error"]["code"] == "NOT_FOUND"
    assert "Claim" in data["error"]["message"]

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_get_claim_team_scope_visible_to_author(
    app: FastAPI,
    async_client: AsyncClient,
    auth_agent: tuple[str, Agent],
) -> None:
    """Verifies that a 'team' scoped claim is visible to its authoring agent."""
    secret, agent = auth_agent
    claim = make_test_claim(agent, scope="team")

    mock_session = make_mock_session(agent, claim=claim, links=[])
    app.dependency_overrides[get_db] = lambda: mock_session

    response = await async_client.get(
        f"/api/v1/claims/{claim.id}",
        headers={"Authorization": f"Bearer {secret}"},
    )

    assert response.status_code == 200
    assert response.json()["claim"]["id"] == str(claim.id)

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_get_claim_team_scope_fails_closed_for_peer_agent_with_404(
    app: FastAPI,
    async_client: AsyncClient,
    auth_agent: tuple[str, Agent],
    peer_agent: tuple[str, Agent],
) -> None:
    """Verifies that 'team' scope fails closed (returns 404) for peer agents because teams are not in schema."""
    _, author_agent = auth_agent
    peer_secret, peer_agent_obj = peer_agent

    claim = make_test_claim(author_agent, scope="team")

    # Authenticate as peer agent
    mock_session = make_mock_session(peer_agent_obj, claim=claim, links=[])
    app.dependency_overrides[get_db] = lambda: mock_session

    response = await async_client.get(
        f"/api/v1/claims/{claim.id}",
        headers={"Authorization": f"Bearer {peer_secret}"},
    )

    # Fail closed: team membership cannot be verified without team model, returning 404
    assert response.status_code == 404
    data = response.json()
    assert data["error"]["code"] == "NOT_FOUND"

    app.dependency_overrides.clear()


# -----------------------------------------------------------------------------
# 3. Cross-Tenant & Nonexistent Boundary Isolation
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_claim_cross_workspace_returns_404(
    app: FastAPI,
    async_client: AsyncClient,
    auth_agent: tuple[str, Agent],
) -> None:
    """Verifies that querying a claim in another workspace returns generic 404 without leaking existence."""
    secret, agent = auth_agent

    foreign_workspace_id = uuid.uuid4()
    foreign_claim = make_test_claim(
        agent,
        scope="workspace",
        workspace_id=foreign_workspace_id,
    )

    mock_session = make_mock_session(agent, claim=foreign_claim, links=[])
    app.dependency_overrides[get_db] = lambda: mock_session

    response = await async_client.get(
        f"/api/v1/claims/{foreign_claim.id}",
        headers={"Authorization": f"Bearer {secret}"},
    )

    assert response.status_code == 404
    data = response.json()
    assert data["error"]["code"] == "NOT_FOUND"
    assert data["error"]["message"] == "Resource not found."

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_get_claim_nonexistent_returns_404(
    app: FastAPI,
    async_client: AsyncClient,
    auth_agent: tuple[str, Agent],
) -> None:
    """Verifies that querying a nonexistent claim returns 404 Not Found."""
    secret, agent = auth_agent

    mock_session = make_mock_session(agent, claim=None, links=[])
    app.dependency_overrides[get_db] = lambda: mock_session

    random_id = uuid.uuid4()
    response = await async_client.get(
        f"/api/v1/claims/{random_id}",
        headers={"Authorization": f"Bearer {secret}"},
    )

    assert response.status_code == 404
    data = response.json()
    assert data["error"]["code"] == "NOT_FOUND"
    assert "Claim" in data["error"]["message"]

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_get_claim_rejects_malformed_uuid(
    app: FastAPI,
    async_client: AsyncClient,
    auth_agent: tuple[str, Agent],
) -> None:
    """Verifies 422 when claim_id is not a valid UUID."""
    secret, agent = auth_agent
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.scalar.return_value = agent
    app.dependency_overrides[get_db] = lambda: mock_session

    response = await async_client.get(
        "/api/v1/claims/not-a-valid-uuid",
        headers={"Authorization": f"Bearer {secret}"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    app.dependency_overrides.clear()


# -----------------------------------------------------------------------------
# 4. Authentication Failures
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_claim_requires_authentication(
    async_client: AsyncClient,
) -> None:
    """Verifies 401 when Authorization header is missing."""
    response = await async_client.get(f"/api/v1/claims/{uuid.uuid4()}")
    assert response.status_code == 401
    assert response.headers.get("WWW-Authenticate") == "Bearer"
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


@pytest.mark.asyncio
async def test_get_claim_rejects_unknown_agent(
    app: FastAPI,
    async_client: AsyncClient,
) -> None:
    """Verifies 401 when API key hash does not match any agent."""
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.scalar.return_value = None
    app.dependency_overrides[get_db] = lambda: mock_session

    response = await async_client.get(
        f"/api/v1/claims/{uuid.uuid4()}",
        headers={"Authorization": "Bearer fil_live_unknown_key_999"},
    )

    assert response.status_code == 401
    assert response.headers.get("WWW-Authenticate") == "Bearer"
    assert response.json()["error"]["message"] == "Invalid API key."

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_get_claim_rejects_inactive_agent(
    app: FastAPI,
    async_client: AsyncClient,
) -> None:
    """Verifies 401 when agent is disabled."""
    secret = "fil_live_inactive_agent_retrieval"
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

    response = await async_client.get(
        f"/api/v1/claims/{uuid.uuid4()}",
        headers={"Authorization": f"Bearer {secret}"},
    )

    assert response.status_code == 401
    assert response.headers.get("WWW-Authenticate") == "Bearer"
    assert response.json()["error"]["message"] == "Invalid API key."

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_get_claim_authentication_failures_are_indistinguishable(
    app: FastAPI,
    async_client: AsyncClient,
) -> None:
    """Verifies that unknown and inactive credentials produce identical 401 responses."""
    claim_id = uuid.uuid4()

    # 1. Unknown agent
    mock_session_unknown = AsyncMock(spec=AsyncSession)
    mock_session_unknown.scalar.return_value = None
    app.dependency_overrides[get_db] = lambda: mock_session_unknown

    unknown_res = await async_client.get(
        f"/api/v1/claims/{claim_id}",
        headers={"Authorization": "Bearer fil_live_unknown_agent_xyz"},
    )

    # 2. Inactive agent
    inactive_agent = Agent(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        name="disabled-agent",
        api_key_hash=hash_api_key("fil_live_inactive_agent_abc"),
        is_active=False,
    )
    mock_session_inactive = AsyncMock(spec=AsyncSession)
    mock_session_inactive.scalar.return_value = inactive_agent
    app.dependency_overrides[get_db] = lambda: mock_session_inactive

    inactive_res = await async_client.get(
        f"/api/v1/claims/{claim_id}",
        headers={"Authorization": "Bearer fil_live_inactive_agent_abc"},
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
# 5. Safe Error Logging & Sanitization
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_claim_logging_sanitizes_database_exception_and_parameters(
    app: FastAPI,
    async_client: AsyncClient,
    auth_agent: tuple[str, Agent],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Verifies that error logging suppresses sensitive query parameters and SQL text."""
    secret, agent = auth_agent
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.scalar.return_value = agent
    mock_session.is_active = True
    app.dependency_overrides[get_db] = lambda: mock_session

    secret_canary = "DATABASE_SECRET_PAYLOAD_PARAM_GET_CLAIM_98765"
    db_error = IntegrityError(
        statement="SELECT * FROM claims WHERE secret = :sec",
        params={"sec": secret_canary},
        orig=Exception(f"Connection failure with {secret_canary}"),
    )

    with caplog.at_level(logging.ERROR):
        with patch(
            "filament_api.api.routes.claims.ClaimService.get_claim_with_evidence",
            side_effect=db_error,
        ):
            response = await async_client.get(
                f"/api/v1/claims/{uuid.uuid4()}",
                headers={"Authorization": f"Bearer {secret}"},
            )

    assert response.status_code == 500
    assert secret_canary not in response.text
    assert secret_canary not in caplog.text

    assert "sqlalchemy.exc.IntegrityError" in caplog.text
    assert "[message and parameters redacted]" in caplog.text
    assert "File " in caplog.text
    assert "get_claim" in caplog.text

    app.dependency_overrides.clear()


# -----------------------------------------------------------------------------
# 6. Read-Only Transaction & Audit Absence Verification
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_claim_performs_no_writes_commits_or_audit_mutations(
    app: FastAPI,
    async_client: AsyncClient,
    auth_agent: tuple[str, Agent],
) -> None:
    """Verifies that GET /api/v1/claims/{claim_id} performs zero commits, flushes, or audit events."""
    secret, agent = auth_agent
    claim = make_test_claim(agent, scope="workspace")
    link = make_test_link(claim)

    mock_session = make_mock_session(agent, claim=claim, links=[link])
    app.dependency_overrides[get_db] = lambda: mock_session

    response = await async_client.get(
        f"/api/v1/claims/{claim.id}",
        headers={"Authorization": f"Bearer {secret}"},
    )

    assert response.status_code == 200

    # Ensure no write actions were invoked on the session
    mock_session.commit.assert_not_awaited()
    mock_session.rollback.assert_not_awaited()
    mock_session.add.assert_not_called()
    mock_session.flush.assert_not_awaited()

    app.dependency_overrides.clear()
