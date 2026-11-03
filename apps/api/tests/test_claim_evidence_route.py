"""Automated HTTP integration tests for POST /api/v1/claims/{claim_id}/evidence.

DIAGNOSTIC SCOPE & LIMITATIONS:
These tests verify FastAPI routing, agent authentication dependencies, schema validation,
tenant isolation boundaries, duplicate link prevention, atomic audit event staging,
pre-commit response serialization, explicit endpoint transaction ownership, rollback triggers,
and sanitized error logging using mocked async sessions.
They DO NOT verify live PostgreSQL composite foreign key constraints or PL/pgSQL triggers.
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
from filament_api.models.audit import AuditEvent
from filament_api.models.claim import Claim, ClaimEvidence
from filament_api.models.evidence import Evidence
from filament_api.services.exceptions import (
    DuplicateLinkError,
    EntityNotFoundError,
    FilamentDomainError,
    UnauthorizedActorError,
    ValidationDomainError,
    WorkspaceMismatchError,
)


@pytest.fixture
def auth_agent() -> tuple[str, Agent]:
    """Fixture providing a valid agent and raw bearer secret."""
    raw_secret = "fil_live_test_claim_evidence_key_123"
    agent = Agent(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        name="evidence-linker-agent",
        api_key_hash=hash_api_key(raw_secret),
        is_active=True,
    )
    return raw_secret, agent


@pytest.fixture
def test_claim(auth_agent: tuple[str, Agent]) -> Claim:
    """Fixture providing a valid claim belonging to the authenticated agent's workspace."""
    _, agent = auth_agent
    return Claim(
        id=uuid.uuid4(),
        workspace_id=agent.workspace_id,
        agent_id=agent.id,
        claim_type="fact",
        subject="database.persistence",
        predicate="engine_type",
        object_value={"engine": "postgresql"},
        raw_statement="The project uses PostgreSQL.",
        scope="team",
        status="current",
        confidence=Decimal("0.95"),
        version=1,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def test_evidence(auth_agent: tuple[str, Agent]) -> Evidence:
    """Fixture providing a valid evidence record belonging to the authenticated agent's workspace."""
    _, agent = auth_agent
    return Evidence(
        id=uuid.uuid4(),
        workspace_id=agent.workspace_id,
        source_type="git_commit",
        source_uri="git://commit/a1b2c3d4",
        content_hash="2" * 64,
        raw_snippet="Configured PostgreSQL with asyncpg.",
        collected_by_agent=agent.id,
        collected_by_user=None,
        metadata_={"commit": "a1b2c3d4"},
        created_at=datetime.now(timezone.utc),
    )


def make_mock_scalar(
    agent: Agent,
    claim: Claim | None = None,
    evidence: Evidence | None = None,
    existing_link: ClaimEvidence | None = None,
):
    """Helper that routes session.scalar() queries to the corresponding mock model."""
    async def scalar_handler(stmt):
        entity_type = stmt.column_descriptions[0]["type"]
        if entity_type == Agent:
            return agent
        if entity_type == Claim:
            return claim
        if entity_type == Evidence:
            return evidence
        if entity_type == ClaimEvidence:
            return existing_link
        return None

    return scalar_handler


# -----------------------------------------------------------------------------
# 1. Successful Evidence Linking
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_link_evidence_success(
    app: FastAPI,
    async_client: AsyncClient,
    auth_agent: tuple[str, Agent],
    test_claim: Claim,
    test_evidence: Evidence,
) -> None:
    """Verifies that authenticated POST /api/v1/claims/{id}/evidence returns 201 with expected fields."""
    secret, agent = auth_agent

    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.scalar.side_effect = make_mock_scalar(agent, test_claim, test_evidence, None)
    mock_session.is_active = True

    app.dependency_overrides[get_db] = lambda: mock_session

    payload = {
        "evidence_id": str(test_evidence.id),
        "support_type": "supports",
        "confidence_weight": "0.90",
        "extraction_notes": "Commit message explicitly documents asyncpg configuration.",
    }

    response = await async_client.post(
        f"/api/v1/claims/{test_claim.id}/evidence",
        json=payload,
        headers={"Authorization": f"Bearer {secret}"},
    )

    assert response.status_code == 201
    data = response.json()

    # Validate response schema fields
    assert data["workspace_id"] == str(agent.workspace_id)
    assert data["claim_id"] == str(test_claim.id)
    assert data["evidence_id"] == str(test_evidence.id)
    assert data["support_type"] == "supports"
    assert data["confidence_weight"] == "0.90"
    assert data["extraction_notes"] == "Commit message explicitly documents asyncpg configuration."
    assert datetime.fromisoformat(data["created_at"])

    # Ensure endpoint explicitly committed once and did not roll back
    mock_session.commit.assert_awaited_once()
    mock_session.rollback.assert_not_awaited()

    app.dependency_overrides.clear()


@pytest.mark.asyncio
@pytest.mark.parametrize("support_type", ["supports", "refutes", "mentions"])
async def test_link_evidence_supported_polarity_types(
    app: FastAPI,
    async_client: AsyncClient,
    auth_agent: tuple[str, Agent],
    test_claim: Claim,
    test_evidence: Evidence,
    support_type: str,
) -> None:
    """Verifies that all three supported polarity types ('supports', 'refutes', 'mentions') succeed."""
    secret, agent = auth_agent

    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.scalar.side_effect = make_mock_scalar(agent, test_claim, test_evidence, None)
    mock_session.is_active = True
    app.dependency_overrides[get_db] = lambda: mock_session

    payload = {
        "evidence_id": str(test_evidence.id),
        "support_type": support_type,
        "confidence_weight": "1.00",
    }

    response = await async_client.post(
        f"/api/v1/claims/{test_claim.id}/evidence",
        json=payload,
        headers={"Authorization": f"Bearer {secret}"},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["support_type"] == support_type

    app.dependency_overrides.clear()


# -----------------------------------------------------------------------------
# 2. Atomic Audit Trail Staging
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_link_evidence_stages_audit_event_atomically(
    app: FastAPI,
    async_client: AsyncClient,
    auth_agent: tuple[str, Agent],
    test_claim: Claim,
    test_evidence: Evidence,
) -> None:
    """Verifies that an EVIDENCE_LINKED audit event is staged atomically in the session."""
    secret, agent = auth_agent

    added_entities = []
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.scalar.side_effect = make_mock_scalar(agent, test_claim, test_evidence, None)
    mock_session.is_active = True
    mock_session.add = MagicMock(side_effect=lambda entity: added_entities.append(entity))
    app.dependency_overrides[get_db] = lambda: mock_session

    payload = {
        "evidence_id": str(test_evidence.id),
        "support_type": "refutes",
        "confidence_weight": "0.75",
        "extraction_notes": "Benchmark demonstrates failure under load.",
    }

    response = await async_client.post(
        f"/api/v1/claims/{test_claim.id}/evidence",
        json=payload,
        headers={"Authorization": f"Bearer {secret}"},
    )

    assert response.status_code == 201

    # Verify staged entities: ClaimEvidence junction and AuditEvent
    assert len(added_entities) == 2
    link_entity = added_entities[0]
    audit_entity = added_entities[1]

    assert isinstance(link_entity, ClaimEvidence)
    assert link_entity.claim_id == test_claim.id
    assert link_entity.evidence_id == test_evidence.id
    assert link_entity.support_type == "refutes"

    assert isinstance(audit_entity, AuditEvent)
    assert audit_entity.workspace_id == agent.workspace_id
    assert audit_entity.actor_type == "agent"
    assert audit_entity.actor_id == agent.id
    assert audit_entity.event_type == "EVIDENCE_LINKED"
    assert audit_entity.target_type == "claim_evidence"
    assert audit_entity.target_id == test_claim.id
    assert audit_entity.payload == {
        "claim_id": str(test_claim.id),
        "evidence_id": str(test_evidence.id),
        "support_type": "refutes",
        "confidence_weight": "0.75",
    }

    mock_session.commit.assert_awaited_once()

    app.dependency_overrides.clear()


# -----------------------------------------------------------------------------
# 3. Authentication & Credential Rejections
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_link_evidence_requires_authentication(
    async_client: AsyncClient,
) -> None:
    """Verifies 401 when Authorization header is omitted."""
    random_claim_id = uuid.uuid4()
    response = await async_client.post(
        f"/api/v1/claims/{random_claim_id}/evidence",
        json={"evidence_id": str(uuid.uuid4())},
    )
    assert response.status_code == 401
    assert response.headers.get("WWW-Authenticate") == "Bearer"
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


@pytest.mark.asyncio
async def test_link_evidence_rejects_malformed_auth_header(
    async_client: AsyncClient,
) -> None:
    """Verifies 401 when Authorization scheme is invalid or empty."""
    random_claim_id = uuid.uuid4()
    response = await async_client.post(
        f"/api/v1/claims/{random_claim_id}/evidence",
        json={"evidence_id": str(uuid.uuid4())},
        headers={"Authorization": "Basic dXNlcjpwYXNz"},
    )
    assert response.status_code == 401
    assert response.headers.get("WWW-Authenticate") == "Bearer"
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


@pytest.mark.asyncio
async def test_link_evidence_rejects_unknown_agent(
    app: FastAPI,
    async_client: AsyncClient,
) -> None:
    """Verifies 401 when API key hash does not match any agent."""
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.scalar.return_value = None
    app.dependency_overrides[get_db] = lambda: mock_session

    response = await async_client.post(
        f"/api/v1/claims/{uuid.uuid4()}/evidence",
        json={"evidence_id": str(uuid.uuid4())},
        headers={"Authorization": "Bearer fil_live_unknown_key_999"},
    )

    assert response.status_code == 401
    assert response.headers.get("WWW-Authenticate") == "Bearer"
    assert response.json()["error"]["message"] == "Invalid API key."

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_link_evidence_rejects_inactive_agent(
    app: FastAPI,
    async_client: AsyncClient,
) -> None:
    """Verifies 401 when agent exists but is_active is False."""
    secret = "fil_live_inactive_agent_key_evidence"
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
        f"/api/v1/claims/{uuid.uuid4()}/evidence",
        json={"evidence_id": str(uuid.uuid4())},
        headers={"Authorization": f"Bearer {secret}"},
    )

    assert response.status_code == 401
    assert response.headers.get("WWW-Authenticate") == "Bearer"
    assert response.json()["error"]["message"] == "Invalid API key."

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_link_evidence_authentication_failures_are_indistinguishable(
    app: FastAPI,
    async_client: AsyncClient,
) -> None:
    """Verifies that unknown and inactive credentials produce identical 401 responses."""
    # 1. Unknown agent
    mock_session_unknown = AsyncMock(spec=AsyncSession)
    mock_session_unknown.scalar.return_value = None
    app.dependency_overrides[get_db] = lambda: mock_session_unknown

    claim_id = uuid.uuid4()
    ev_id = uuid.uuid4()

    unknown_res = await async_client.post(
        f"/api/v1/claims/{claim_id}/evidence",
        json={"evidence_id": str(ev_id)},
        headers={"Authorization": "Bearer fil_live_unknown_key_abc"},
    )

    # 2. Inactive agent
    inactive_agent = Agent(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        name="disabled-agent",
        api_key_hash=hash_api_key("fil_live_inactive_key_def"),
        is_active=False,
    )
    mock_session_inactive = AsyncMock(spec=AsyncSession)
    mock_session_inactive.scalar.return_value = inactive_agent
    app.dependency_overrides[get_db] = lambda: mock_session_inactive

    inactive_res = await async_client.post(
        f"/api/v1/claims/{claim_id}/evidence",
        json={"evidence_id": str(ev_id)},
        headers={"Authorization": "Bearer fil_live_inactive_key_def"},
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
# 4. Entity Existence & Tenant Isolation (404 Not Found)
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_link_evidence_returns_404_when_claim_not_found(
    app: FastAPI,
    async_client: AsyncClient,
    auth_agent: tuple[str, Agent],
    test_evidence: Evidence,
) -> None:
    """Verifies 404 when target claim_id does not exist."""
    secret, agent = auth_agent

    mock_session = AsyncMock(spec=AsyncSession)
    # Claim lookup returns None
    mock_session.scalar.side_effect = make_mock_scalar(agent, None, test_evidence, None)
    mock_session.is_active = True
    app.dependency_overrides[get_db] = lambda: mock_session

    missing_claim_id = uuid.uuid4()
    response = await async_client.post(
        f"/api/v1/claims/{missing_claim_id}/evidence",
        json={"evidence_id": str(test_evidence.id)},
        headers={"Authorization": f"Bearer {secret}"},
    )

    assert response.status_code == 404
    data = response.json()
    assert data["error"]["code"] == "NOT_FOUND"
    assert "Claim" in data["error"]["message"]
    mock_session.rollback.assert_awaited()

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_link_evidence_returns_404_when_evidence_not_found(
    app: FastAPI,
    async_client: AsyncClient,
    auth_agent: tuple[str, Agent],
    test_claim: Claim,
) -> None:
    """Verifies 404 when target evidence_id does not exist."""
    secret, agent = auth_agent

    mock_session = AsyncMock(spec=AsyncSession)
    # Evidence lookup returns None
    mock_session.scalar.side_effect = make_mock_scalar(agent, test_claim, None, None)
    mock_session.is_active = True
    app.dependency_overrides[get_db] = lambda: mock_session

    missing_ev_id = uuid.uuid4()
    response = await async_client.post(
        f"/api/v1/claims/{test_claim.id}/evidence",
        json={"evidence_id": str(missing_ev_id)},
        headers={"Authorization": f"Bearer {secret}"},
    )

    assert response.status_code == 404
    data = response.json()
    assert data["error"]["code"] == "NOT_FOUND"
    assert "Evidence" in data["error"]["message"]
    mock_session.rollback.assert_awaited()

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_link_evidence_rejects_cross_workspace_claim(
    app: FastAPI,
    async_client: AsyncClient,
    auth_agent: tuple[str, Agent],
    test_evidence: Evidence,
) -> None:
    """Verifies 404 when claim exists but belongs to a different workspace."""
    secret, agent = auth_agent

    # Foreign workspace claim
    foreign_claim = Claim(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),  # Different workspace!
        agent_id=uuid.uuid4(),
        claim_type="fact",
        subject="foreign.subject",
        predicate="foreign.predicate",
        object_value={},
        raw_statement="Foreign claim.",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.scalar.side_effect = make_mock_scalar(agent, foreign_claim, test_evidence, None)
    mock_session.is_active = True
    app.dependency_overrides[get_db] = lambda: mock_session

    response = await async_client.post(
        f"/api/v1/claims/{foreign_claim.id}/evidence",
        json={"evidence_id": str(test_evidence.id)},
        headers={"Authorization": f"Bearer {secret}"},
    )

    # Cross-tenant mismatch returns 404 to avoid enumeration
    assert response.status_code == 404
    data = response.json()
    assert data["error"]["code"] == "NOT_FOUND"
    assert data["error"]["message"] == "Resource not found."
    mock_session.rollback.assert_awaited()

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_link_evidence_rejects_cross_workspace_evidence(
    app: FastAPI,
    async_client: AsyncClient,
    auth_agent: tuple[str, Agent],
    test_claim: Claim,
) -> None:
    """Verifies 404 when evidence exists but belongs to a different workspace."""
    secret, agent = auth_agent

    # Foreign workspace evidence
    foreign_evidence = Evidence(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),  # Different workspace!
        source_type="file",
        source_uri="foreign.txt",
        content_hash="3" * 64,
        raw_snippet="Foreign snippet.",
        created_at=datetime.now(timezone.utc),
    )

    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.scalar.side_effect = make_mock_scalar(agent, test_claim, foreign_evidence, None)
    mock_session.is_active = True
    app.dependency_overrides[get_db] = lambda: mock_session

    response = await async_client.post(
        f"/api/v1/claims/{test_claim.id}/evidence",
        json={"evidence_id": str(foreign_evidence.id)},
        headers={"Authorization": f"Bearer {secret}"},
    )

    assert response.status_code == 404
    data = response.json()
    assert data["error"]["code"] == "NOT_FOUND"
    assert data["error"]["message"] == "Resource not found."
    mock_session.rollback.assert_awaited()

    app.dependency_overrides.clear()


# -----------------------------------------------------------------------------
# 5. Duplicate Relationship Rejection (409 Conflict)
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_link_evidence_rejects_duplicate_relationship(
    app: FastAPI,
    async_client: AsyncClient,
    auth_agent: tuple[str, Agent],
    test_claim: Claim,
    test_evidence: Evidence,
) -> None:
    """Verifies 409 Conflict when the claim-evidence junction already exists."""
    secret, agent = auth_agent

    existing_junction = ClaimEvidence(
        workspace_id=agent.workspace_id,
        claim_id=test_claim.id,
        evidence_id=test_evidence.id,
        support_type="supports",
        confidence_weight=Decimal("1.00"),
        created_at=datetime.now(timezone.utc),
    )

    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.scalar.side_effect = make_mock_scalar(
        agent, test_claim, test_evidence, existing_junction
    )
    mock_session.is_active = True
    app.dependency_overrides[get_db] = lambda: mock_session

    response = await async_client.post(
        f"/api/v1/claims/{test_claim.id}/evidence",
        json={"evidence_id": str(test_evidence.id)},
        headers={"Authorization": f"Bearer {secret}"},
    )

    assert response.status_code == 409
    data = response.json()
    assert data["error"]["code"] == "CONFLICT"
    assert "already linked" in data["error"]["message"]
    mock_session.rollback.assert_awaited()

    app.dependency_overrides.clear()


# -----------------------------------------------------------------------------
# 6. Schema & Payload Validation Rejections (422)
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_link_evidence_rejects_invalid_support_type(
    app: FastAPI,
    async_client: AsyncClient,
    auth_agent: tuple[str, Agent],
    test_claim: Claim,
    test_evidence: Evidence,
) -> None:
    """Verifies 422 when support_type is not 'supports', 'refutes', or 'mentions'."""
    secret, agent = auth_agent
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.scalar.side_effect = make_mock_scalar(agent, test_claim, test_evidence, None)
    app.dependency_overrides[get_db] = lambda: mock_session

    payload = {
        "evidence_id": str(test_evidence.id),
        "support_type": "corroborates",  # Invalid for ClaimEvidence
    }

    response = await async_client.post(
        f"/api/v1/claims/{test_claim.id}/evidence",
        json=payload,
        headers={"Authorization": f"Bearer {secret}"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    app.dependency_overrides.clear()


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_weight", ["-0.01", "1.01", "5.00"])
async def test_link_evidence_rejects_out_of_bounds_confidence_weight(
    app: FastAPI,
    async_client: AsyncClient,
    auth_agent: tuple[str, Agent],
    test_claim: Claim,
    test_evidence: Evidence,
    bad_weight: str,
) -> None:
    """Verifies 422 when confidence_weight is outside [0.00, 1.00]."""
    secret, agent = auth_agent
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.scalar.side_effect = make_mock_scalar(agent, test_claim, test_evidence, None)
    app.dependency_overrides[get_db] = lambda: mock_session

    payload = {
        "evidence_id": str(test_evidence.id),
        "confidence_weight": bad_weight,
    }

    response = await async_client.post(
        f"/api/v1/claims/{test_claim.id}/evidence",
        json=payload,
        headers={"Authorization": f"Bearer {secret}"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_link_evidence_rejects_extra_fields(
    app: FastAPI,
    async_client: AsyncClient,
    auth_agent: tuple[str, Agent],
    test_claim: Claim,
    test_evidence: Evidence,
) -> None:
    """Verifies 422 when payload contains forbidden extra fields (e.g. workspace_id)."""
    secret, agent = auth_agent
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.scalar.side_effect = make_mock_scalar(agent, test_claim, test_evidence, None)
    app.dependency_overrides[get_db] = lambda: mock_session

    payload = {
        "evidence_id": str(test_evidence.id),
        "workspace_id": str(uuid.uuid4()),  # Forbidden
        "claim_id": str(test_claim.id),     # Path-bound, forbidden in body
    }

    response = await async_client.post(
        f"/api/v1/claims/{test_claim.id}/evidence",
        json=payload,
        headers={"Authorization": f"Bearer {secret}"},
    )

    assert response.status_code == 422
    data = response.json()
    assert data["error"]["code"] == "VALIDATION_ERROR"

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_link_evidence_rejects_whitespace_extraction_notes(
    app: FastAPI,
    async_client: AsyncClient,
    auth_agent: tuple[str, Agent],
    test_claim: Claim,
    test_evidence: Evidence,
) -> None:
    """Verifies 422 when extraction_notes contains only whitespace."""
    secret, agent = auth_agent
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.scalar.side_effect = make_mock_scalar(agent, test_claim, test_evidence, None)
    app.dependency_overrides[get_db] = lambda: mock_session

    payload = {
        "evidence_id": str(test_evidence.id),
        "extraction_notes": "   \n\t  ",
    }

    response = await async_client.post(
        f"/api/v1/claims/{test_claim.id}/evidence",
        json=payload,
        headers={"Authorization": f"Bearer {secret}"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_link_evidence_rejects_invalid_uuid_in_path(
    app: FastAPI,
    async_client: AsyncClient,
    auth_agent: tuple[str, Agent],
) -> None:
    """Verifies 422 when claim_id in URL path is not a valid UUID."""
    secret, agent = auth_agent
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.scalar.return_value = agent
    app.dependency_overrides[get_db] = lambda: mock_session

    response = await async_client.post(
        "/api/v1/claims/not-a-valid-uuid/evidence",
        json={"evidence_id": str(uuid.uuid4())},
        headers={"Authorization": f"Bearer {secret}"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    app.dependency_overrides.clear()


# -----------------------------------------------------------------------------
# 7. Domain Exception Mapping
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_link_evidence_maps_validation_domain_error_to_422(
    app: FastAPI,
    async_client: AsyncClient,
    auth_agent: tuple[str, Agent],
    test_claim: Claim,
    test_evidence: Evidence,
) -> None:
    """Verifies that ValidationDomainError maps to HTTP 422."""
    secret, agent = auth_agent
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.scalar.side_effect = make_mock_scalar(agent, test_claim, test_evidence, None)
    mock_session.is_active = True
    app.dependency_overrides[get_db] = lambda: mock_session

    with patch(
        "filament_api.api.routes.claims.ClaimService.link_evidence",
        side_effect=ValidationDomainError("Invalid relationship metadata."),
    ):
        response = await async_client.post(
            f"/api/v1/claims/{test_claim.id}/evidence",
            json={"evidence_id": str(test_evidence.id)},
            headers={"Authorization": f"Bearer {secret}"},
        )

        assert response.status_code == 422
        data = response.json()
        assert data["error"]["code"] == "VALIDATION_ERROR"
        assert data["error"]["message"] == "Invalid relationship metadata."
        mock_session.rollback.assert_awaited()

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_link_evidence_maps_unauthorized_actor_error_to_403(
    app: FastAPI,
    async_client: AsyncClient,
    auth_agent: tuple[str, Agent],
    test_claim: Claim,
    test_evidence: Evidence,
) -> None:
    """Verifies that UnauthorizedActorError maps to HTTP 403."""
    secret, agent = auth_agent
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.scalar.side_effect = make_mock_scalar(agent, test_claim, test_evidence, None)
    mock_session.is_active = True
    app.dependency_overrides[get_db] = lambda: mock_session

    with patch(
        "filament_api.api.routes.claims.ClaimService.link_evidence",
        side_effect=UnauthorizedActorError("Actor not permitted to link evidence."),
    ):
        response = await async_client.post(
            f"/api/v1/claims/{test_claim.id}/evidence",
            json={"evidence_id": str(test_evidence.id)},
            headers={"Authorization": f"Bearer {secret}"},
        )

        assert response.status_code == 403
        data = response.json()
        assert data["error"]["code"] == "FORBIDDEN"
        assert data["error"]["message"] == "Actor not permitted to link evidence."
        mock_session.rollback.assert_awaited()

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_link_evidence_maps_filament_domain_error_to_400(
    app: FastAPI,
    async_client: AsyncClient,
    auth_agent: tuple[str, Agent],
    test_claim: Claim,
    test_evidence: Evidence,
) -> None:
    """Verifies that generic FilamentDomainError maps to HTTP 400."""
    secret, agent = auth_agent
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.scalar.side_effect = make_mock_scalar(agent, test_claim, test_evidence, None)
    mock_session.is_active = True
    app.dependency_overrides[get_db] = lambda: mock_session

    with patch(
        "filament_api.api.routes.claims.ClaimService.link_evidence",
        side_effect=FilamentDomainError("Generic link operation failure."),
    ):
        response = await async_client.post(
            f"/api/v1/claims/{test_claim.id}/evidence",
            json={"evidence_id": str(test_evidence.id)},
            headers={"Authorization": f"Bearer {secret}"},
        )

        assert response.status_code == 400
        data = response.json()
        assert data["error"]["code"] == "BAD_REQUEST"
        assert data["error"]["message"] == "Generic link operation failure."
        mock_session.rollback.assert_awaited()

    app.dependency_overrides.clear()


# -----------------------------------------------------------------------------
# 8. Transaction Ownership & Lifecycle
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_link_evidence_response_validation_failure_rolls_back_without_commit(
    app: FastAPI,
    async_client: AsyncClient,
    auth_agent: tuple[str, Agent],
    test_claim: Claim,
    test_evidence: Evidence,
) -> None:
    """Verifies that response preparation failure triggers rollback and NEVER commits."""
    secret, agent = auth_agent
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.scalar.side_effect = make_mock_scalar(agent, test_claim, test_evidence, None)
    mock_session.is_active = True
    app.dependency_overrides[get_db] = lambda: mock_session

    with patch(
        "filament_api.api.routes.claims.ClaimEvidenceResponse.model_validate",
        side_effect=ValueError("Simulated DTO serialization failure"),
    ):
        response = await async_client.post(
            f"/api/v1/claims/{test_claim.id}/evidence",
            json={"evidence_id": str(test_evidence.id)},
            headers={"Authorization": f"Bearer {secret}"},
        )

        assert response.status_code == 500
        # Commit must NOT be called if response preparation fails
        mock_session.commit.assert_not_awaited()
        # Rollback must be triggered
        mock_session.rollback.assert_awaited()

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_link_evidence_commit_failure_returns_500_and_rolls_back(
    app: FastAPI,
    async_client: AsyncClient,
    auth_agent: tuple[str, Agent],
    test_claim: Claim,
    test_evidence: Evidence,
) -> None:
    """Verifies that if explicit commit fails, the client receives 500 and rollback runs."""
    secret, agent = auth_agent
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.scalar.side_effect = make_mock_scalar(agent, test_claim, test_evidence, None)
    mock_session.is_active = True
    mock_session.commit.side_effect = RuntimeError("FATAL: connection terminated during commit")
    app.dependency_overrides[get_db] = lambda: mock_session

    response = await async_client.post(
        f"/api/v1/claims/{test_claim.id}/evidence",
        json={"evidence_id": str(test_evidence.id)},
        headers={"Authorization": f"Bearer {secret}"},
    )

    assert response.status_code == 500
    data = response.json()
    assert data["error"]["code"] == "INTERNAL_SERVER_ERROR"
    assert data["error"]["message"] == "An internal server error occurred."
    assert "connection terminated" not in response.text

    mock_session.rollback.assert_awaited()

    app.dependency_overrides.clear()


# -----------------------------------------------------------------------------
# 9. Safe Logging Verification
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_link_evidence_logging_sanitizes_database_exception_and_parameters(
    app: FastAPI,
    async_client: AsyncClient,
    auth_agent: tuple[str, Agent],
    test_claim: Claim,
    test_evidence: Evidence,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Verifies that route-level error logging does not expose SQL statements or bound parameters."""
    secret, agent = auth_agent
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.scalar.side_effect = make_mock_scalar(agent, test_claim, test_evidence, None)
    mock_session.is_active = True
    app.dependency_overrides[get_db] = lambda: mock_session

    secret_canary = "DATABASE_SECRET_PAYLOAD_PARAM_CLAIM_EVIDENCE_54321"
    db_error = IntegrityError(
        statement="INSERT INTO claim_evidence (extraction_notes) VALUES (:notes)",
        params={"notes": secret_canary},
        orig=Exception(f"violates constraint with {secret_canary}"),
    )

    with caplog.at_level(logging.ERROR):
        with patch(
            "filament_api.api.routes.claims.ClaimService.link_evidence",
            side_effect=db_error,
        ):
            response = await async_client.post(
                f"/api/v1/claims/{test_claim.id}/evidence",
                json={"evidence_id": str(test_evidence.id)},
                headers={"Authorization": f"Bearer {secret}"},
            )

    assert response.status_code == 500
    assert secret_canary not in response.text
    assert secret_canary not in caplog.text

    # Useful diagnostics must still be captured safely
    assert "sqlalchemy.exc.IntegrityError" in caplog.text
    assert "[message and parameters redacted]" in caplog.text
    assert "File " in caplog.text
    assert "link_evidence" in caplog.text

    app.dependency_overrides.clear()
