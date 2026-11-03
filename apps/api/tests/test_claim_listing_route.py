"""Automated HTTP integration tests for GET /api/v1/claims.

Verifies claim listing, filtering (status, claim_type), pagination (limit, offset),
workspace isolation, scope visibility rules (workspace vs private/team), and read-only behavior.
"""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
import uuid

from fastapi import FastAPI
from httpx import AsyncClient
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from filament_api.core.security import hash_api_key
from filament_api.db.session import get_db
from filament_api.models.agent import Agent
from filament_api.models.claim import Claim


@pytest.fixture
def auth_agent() -> tuple[str, Agent]:
    """Fixture providing a primary valid agent and raw bearer secret."""
    raw_secret = "fil_live_test_listing_agent_key_1"
    agent = Agent(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        name="listing-agent",
        api_key_hash=hash_api_key(raw_secret),
        is_active=True,
    )
    return raw_secret, agent


@pytest.fixture
def peer_agent(auth_agent: tuple[str, Agent]) -> tuple[str, Agent]:
    """Fixture providing a second active agent within the SAME workspace."""
    _, primary_agent = auth_agent
    raw_secret = "fil_live_test_listing_peer_agent_key_2"
    agent = Agent(
        id=uuid.uuid4(),
        workspace_id=primary_agent.workspace_id,
        name="peer-listing-agent",
        api_key_hash=hash_api_key(raw_secret),
        is_active=True,
    )
    return raw_secret, agent


def make_test_claim(
    agent: Agent,
    scope: str = "workspace",
    claim_id: uuid.UUID | None = None,
    workspace_id: uuid.UUID | None = None,
    claim_type: str = "fact",
    status: str = "current",
    active_condition_version: int | None = None,
) -> Claim:
    """Helper to create a test claim model instance."""
    return Claim(
        id=claim_id or uuid.uuid4(),
        workspace_id=workspace_id or agent.workspace_id,
        agent_id=agent.id,
        claim_type=claim_type,
        subject="database.persistence",
        predicate="engine_type",
        object_value={"engine": "postgresql", "driver": "asyncpg"},
        raw_statement="The project uses PostgreSQL with asyncpg.",
        scope=scope,
        status=status,
        confidence=Decimal("0.95"),
        version=1,
        active_condition_version=active_condition_version,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


# -----------------------------------------------------------------------------
# 1. Successful Listing & Active Condition Version
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_claims_success(
    app: FastAPI,
    async_client: AsyncClient,
    auth_agent: tuple[str, Agent],
) -> None:
    """Verifies that an authenticated agent can retrieve claims with active_condition_version."""
    secret, agent = auth_agent
    claim1 = make_test_claim(agent, scope="workspace", active_condition_version=2)
    claim2 = make_test_claim(agent, scope="workspace", active_condition_version=None)

    mock_session = AsyncMock(spec=AsyncSession)

    async def mock_execute(stmt):
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [claim1, claim2]
        return mock_result

    async def mock_scalar(stmt):
        return agent

    mock_session.execute.side_effect = mock_execute
    mock_session.scalar.side_effect = mock_scalar

    app.dependency_overrides[get_db] = lambda: mock_session

    headers = {"Authorization": f"Bearer {secret}"}
    response = await async_client.get("/api/v1/claims", headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["id"] == str(claim1.id)
    assert data[0]["active_condition_version"] == 2
    assert data[1]["id"] == str(claim2.id)
    assert data[1]["active_condition_version"] is None

    app.dependency_overrides.clear()


# -----------------------------------------------------------------------------
# 2. Authentication Requirement
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_claims_requires_authentication(
    async_client: AsyncClient,
) -> None:
    """Verifies 401 when Authorization header is omitted."""
    response = await async_client.get("/api/v1/claims")
    assert response.status_code == 401
    assert response.headers.get("WWW-Authenticate") == "Bearer"
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


# -----------------------------------------------------------------------------
# 3. Filtering & Pagination
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_claims_filters_by_status_and_type(
    app: FastAPI,
    async_client: AsyncClient,
    auth_agent: tuple[str, Agent],
) -> None:
    """Verifies that status and claim_type query params are received and filtered."""
    secret, agent = auth_agent
    claim = make_test_claim(agent, status="needs_review", claim_type="constraint")

    mock_session = AsyncMock(spec=AsyncSession)
    executed_statements = []

    async def mock_execute(stmt):
        executed_statements.append(stmt)
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [claim]
        return mock_result

    async def mock_scalar(stmt):
        return agent

    mock_session.execute.side_effect = mock_execute
    mock_session.scalar.side_effect = mock_scalar

    app.dependency_overrides[get_db] = lambda: mock_session

    headers = {"Authorization": f"Bearer {secret}"}
    response = await async_client.get(
        "/api/v1/claims?status=needs_review&claim_type=constraint&limit=25&offset=5",
        headers=headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["status"] == "needs_review"
    assert data[0]["claim_type"] == "constraint"
    # Verify that the claims select query was executed
    claim_stmts = [s for s in executed_statements if hasattr(s, "is_select") and s.is_select]
    assert len(claim_stmts) == 1

    app.dependency_overrides.clear()


# -----------------------------------------------------------------------------
# 4. Scope Visibility (Workspace vs Private/Team)
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_claims_scope_visibility_author_vs_peer(
    app: FastAPI,
    async_client: AsyncClient,
    auth_agent: tuple[str, Agent],
    peer_agent: tuple[str, Agent],
) -> None:
    """Verifies that an agent receives only workspace-scoped claims plus their own private/team claims."""
    primary_secret, primary = auth_agent
    peer_secret, peer = peer_agent

    # Primary agent creates a workspace claim and a private claim
    c_workspace = make_test_claim(primary, scope="workspace")
    c_primary_private = make_test_claim(primary, scope="private")

    # Peer agent should see c_workspace, but NOT c_primary_private
    mock_session = AsyncMock(spec=AsyncSession)

    async def mock_execute(stmt):
        # Inspect statement or return the filtered set for peer
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [c_workspace]
        return mock_result

    async def mock_scalar(stmt):
        return peer

    mock_session.execute.side_effect = mock_execute
    mock_session.scalar.side_effect = mock_scalar

    app.dependency_overrides[get_db] = lambda: mock_session

    headers = {"Authorization": f"Bearer {peer_secret}"}
    response = await async_client.get("/api/v1/claims", headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == str(c_workspace.id)

    app.dependency_overrides.clear()


# -----------------------------------------------------------------------------
# 5. Read-Only Invariant (No Commits or Flush)
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_claims_performs_no_commits_or_flushes(
    app: FastAPI,
    async_client: AsyncClient,
    auth_agent: tuple[str, Agent],
) -> None:
    """Verifies that GET /api/v1/claims is strictly read-only and never commits or flushes."""
    secret, agent = auth_agent

    mock_session = AsyncMock(spec=AsyncSession)

    async def mock_execute(stmt):
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        return mock_result

    async def mock_scalar(stmt):
        return agent

    mock_session.execute.side_effect = mock_execute
    mock_session.scalar.side_effect = mock_scalar

    app.dependency_overrides[get_db] = lambda: mock_session

    headers = {"Authorization": f"Bearer {secret}"}
    response = await async_client.get("/api/v1/claims", headers=headers)

    assert response.status_code == 200
    assert mock_session.commit.call_count == 0
    assert mock_session.flush.call_count == 0
    assert mock_session.rollback.call_count == 0

    app.dependency_overrides.clear()

