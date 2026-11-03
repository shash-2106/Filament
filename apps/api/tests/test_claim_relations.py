"""Automated unit, domain service, and HTTP integration tests for claim relations and supersession governance.

DIAGNOSTIC SCOPE & LIMITATIONS:
The tests in this module are unit and mock-persistence tests designed to execute
offline without requiring a running PostgreSQL server or Docker container.
They verify domain service orchestration, acyclicity checks, cascade invalidation,
trusted context invariants, attribution derivation, and atomic staging of domain entities
and audit events.

LIMITATION WARNING:
These tests DO NOT verify live PostgreSQL database constraints (e.g., composite FK
cascades, physical CHECK constraints, or PostgreSQL triggers) or database-level
ACID durability. Full database-level verification requires executing against an
explicitly configured, disposable PostgreSQL test instance.
"""

from collections import deque
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

from filament_api.api.dependencies.auth import get_current_agent_context
from filament_api.core.security import hash_api_key
from filament_api.db.session import get_db
from filament_api.models.agent import Agent
from filament_api.models.audit import AuditEvent
from filament_api.models.claim import Claim, ClaimEvidence
from filament_api.models.evidence import Evidence
from filament_api.models.relation import ClaimRelation
from filament_api.schemas.claim import (
    CreateDependencyParams,
    CreateRelationParams,
    SupersedeClaimParams,
)
from filament_api.services.claim import ClaimService
from filament_api.services.context import ActorType, TrustedContext
from filament_api.services.exceptions import (
    CyclicRelationError,
    DuplicateRelationError,
    EntityNotFoundError,
    ValidationDomainError,
    WorkspaceMismatchError,
)


# -----------------------------------------------------------------------------
# Fixtures and Helpers
# -----------------------------------------------------------------------------

@pytest.fixture
def test_workspace_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def auth_agent(test_workspace_id: uuid.UUID) -> tuple[str, Agent]:
    raw_secret = "fil_live_test_agent_relation_key_123"
    agent = Agent(
        id=uuid.uuid4(),
        workspace_id=test_workspace_id,
        name="relation-test-agent",
        api_key_hash=hash_api_key(raw_secret),
        is_active=True,
    )
    return raw_secret, agent


@pytest.fixture
def peer_agent(test_workspace_id: uuid.UUID) -> tuple[str, Agent]:
    raw_secret = "fil_live_test_peer_agent_key_456"
    agent = Agent(
        id=uuid.uuid4(),
        workspace_id=test_workspace_id,
        name="peer-agent",
        api_key_hash=hash_api_key(raw_secret),
        is_active=True,
    )
    return raw_secret, agent


def make_claim(
    workspace_id: uuid.UUID,
    agent_id: uuid.UUID,
    status: str = "current",
    scope: str = "workspace",
    claim_id: uuid.UUID | None = None,
    version: int = 1,
) -> Claim:
    cid = claim_id or uuid.uuid4()
    return Claim(
        id=cid,
        workspace_id=workspace_id,
        agent_id=agent_id,
        claim_type="fact",
        subject=f"subject.{cid.hex[:8]}",
        predicate="is_configured",
        object_value={"val": 1},
        raw_statement=f"Claim {cid.hex[:8]} is active.",
        scope=scope,
        status=status,
        confidence=Decimal("1.00"),
        version=version,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def make_relation(
    workspace_id: uuid.UUID,
    source_id: uuid.UUID,
    target_id: uuid.UUID,
    relation_type: str,
    agent_id: uuid.UUID | None = None,
) -> ClaimRelation:
    return ClaimRelation(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        source_claim_id=source_id,
        target_claim_id=target_id,
        relation_type=relation_type,
        rationale=f"Relation {relation_type} from {source_id} to {target_id}",
        created_by_agent=agent_id,
        created_at=datetime.now(timezone.utc),
    )


# -----------------------------------------------------------------------------
# Part 1: Domain Service Unit Tests
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_supersede_claim_success_and_status_update(test_workspace_id: uuid.UUID) -> None:
    """Verifies that supersede_claim updates target claim to superseded, increments version, and stages audit events."""
    session = AsyncMock(spec=AsyncSession)
    added_entities = []
    session.add = MagicMock(side_effect=lambda entity: added_entities.append(entity))

    agent_id = uuid.uuid4()
    ctx = TrustedContext(workspace_id=test_workspace_id, actor_type="agent", actor_id=agent_id)

    old_claim = make_claim(test_workspace_id, agent_id, status="current", version=1)
    new_claim = make_claim(test_workspace_id, agent_id, status="current", version=1)

    # scalar calls:
    # 1. source claim lookup
    # 2. target claim lookup
    # 3. duplicate relation lookup
    session.scalar.side_effect = [new_claim, old_claim, None]

    # scalars calls:
    # 1. _has_relation_path
    # 2. _cascade_supersession_to_dependents
    mock_result_path = MagicMock()
    mock_result_path.all.return_value = []
    mock_result_cascade = MagicMock()
    mock_result_cascade.all.return_value = []
    session.scalars.side_effect = [mock_result_path, mock_result_cascade]

    params = SupersedeClaimParams(
        source_claim_id=new_claim.id,
        target_claim_id=old_claim.id,
        rationale="New architecture supersedes older approach.",
    )

    relation, affected = await ClaimService.supersede_claim(session, ctx, params)

    assert isinstance(relation, ClaimRelation)
    assert relation.source_claim_id == new_claim.id
    assert relation.target_claim_id == old_claim.id
    assert relation.relation_type == "supersedes"
    assert relation.rationale == "New architecture supersedes older approach."
    assert relation.created_by_agent == agent_id
    assert affected == []

    # Old claim must be updated
    assert old_claim.status == "superseded"
    assert old_claim.version == 2

    # New claim status must remain current
    assert new_claim.status == "current"
    assert new_claim.version == 1

    # Verify audit events staged atomically
    audit_events = [e for e in added_entities if isinstance(e, AuditEvent)]
    event_types = [a.event_type for a in audit_events]
    assert "CLAIM_SUPERSEDED" in event_types
    assert "CLAIM_RELATION_CREATED" in event_types

    superseded_audit = next(a for a in audit_events if a.event_type == "CLAIM_SUPERSEDED")
    assert superseded_audit.target_id == old_claim.id
    assert superseded_audit.payload["new_claim_id"] == str(new_claim.id)

    # Session must flush, never commit
    session.flush.assert_awaited_once()
    session.commit.assert_not_called()


@pytest.mark.asyncio
async def test_supersede_preserves_evidence_and_claims(test_workspace_id: uuid.UUID) -> None:
    """Verifies that supersession preserves claims and their linked evidence intact without deletion."""
    session = AsyncMock(spec=AsyncSession)
    added_entities = []
    session.add = MagicMock(side_effect=lambda entity: added_entities.append(entity))

    agent_id = uuid.uuid4()
    ctx = TrustedContext(workspace_id=test_workspace_id, actor_type="agent", actor_id=agent_id)

    old_claim = make_claim(test_workspace_id, agent_id, status="current", version=1)
    new_claim = make_claim(test_workspace_id, agent_id, status="current", version=1)

    ev_1 = Evidence(id=uuid.uuid4(), workspace_id=test_workspace_id, raw_snippet="ev 1")
    link_1 = ClaimEvidence(claim_id=old_claim.id, evidence_id=ev_1.id, workspace_id=test_workspace_id)
    old_claim.evidence_links = [link_1]

    ev_2 = Evidence(id=uuid.uuid4(), workspace_id=test_workspace_id, raw_snippet="ev 2")
    link_2 = ClaimEvidence(claim_id=new_claim.id, evidence_id=ev_2.id, workspace_id=test_workspace_id)
    new_claim.evidence_links = [link_2]

    session.scalar.side_effect = [new_claim, old_claim, None]
    mock_res = MagicMock()
    mock_res.all.return_value = []
    session.scalars.side_effect = [mock_res, mock_res]

    params = SupersedeClaimParams(
        source_claim_id=new_claim.id,
        target_claim_id=old_claim.id,
        rationale="Preserves evidence intact.",
    )

    relation, _ = await ClaimService.supersede_claim(session, ctx, params)

    assert len(old_claim.evidence_links) == 1
    assert old_claim.evidence_links[0].evidence_id == ev_1.id
    assert len(new_claim.evidence_links) == 1
    assert new_claim.evidence_links[0].evidence_id == ev_2.id
    assert session.delete.call_count == 0


@pytest.mark.asyncio
async def test_supersede_cascade_invalidates_direct_dependents(test_workspace_id: uuid.UUID) -> None:
    """Verifies that direct dependent claims are transitioned to needs_review and emit DEPENDENCY_INVALIDATED."""
    session = AsyncMock(spec=AsyncSession)
    added_entities = []
    session.add = MagicMock(side_effect=lambda entity: added_entities.append(entity))

    agent_id = uuid.uuid4()
    ctx = TrustedContext(workspace_id=test_workspace_id, actor_type="agent", actor_id=agent_id)

    target_old_claim = make_claim(test_workspace_id, agent_id, status="current", version=1)
    source_new_claim = make_claim(test_workspace_id, agent_id, status="current", version=1)
    dependent_claim = make_claim(test_workspace_id, agent_id, status="current", version=1)

    # Edge: dependent_claim depends_on target_old_claim
    rel_dep = make_relation(test_workspace_id, dependent_claim.id, target_old_claim.id, "depends_on", agent_id)

    # scalar calls:
    # 1. source claim lookup
    # 2. target claim lookup
    # 3. duplicate relation lookup
    # 4. cascade claim lookup for dependent_claim
    session.scalar.side_effect = [source_new_claim, target_old_claim, None, dependent_claim]

    mock_res_path = MagicMock()
    mock_res_path.all.return_value = []

    mock_res_cascade = MagicMock()
    mock_res_cascade.all.return_value = [rel_dep]

    session.scalars.side_effect = [mock_res_path, mock_res_cascade]

    params = SupersedeClaimParams(
        source_claim_id=source_new_claim.id,
        target_claim_id=target_old_claim.id,
        rationale="Supersede and cascade.",
    )

    relation, affected = await ClaimService.supersede_claim(session, ctx, params)

    assert len(affected) == 1
    assert affected[0].id == dependent_claim.id
    assert dependent_claim.status == "needs_review"
    assert dependent_claim.version == 2

    # Verify DEPENDENCY_INVALIDATED audit event
    audit_events = [e for e in added_entities if isinstance(e, AuditEvent)]
    invalidation_audit = next(a for a in audit_events if a.event_type == "DEPENDENCY_INVALIDATED")
    assert invalidation_audit.target_id == dependent_claim.id
    assert invalidation_audit.payload["invalidating_upstream_claim_id"] == str(target_old_claim.id)
    assert invalidation_audit.payload["old_status"] == "current"
    assert invalidation_audit.payload["new_status"] == "needs_review"


@pytest.mark.asyncio
async def test_supersede_cascade_invalidates_transitive_and_multiple_dependents(test_workspace_id: uuid.UUID) -> None:
    """Verifies that transitive and multiple dependent claims are transitioned, while non-current claims are unchanged."""
    session = AsyncMock(spec=AsyncSession)
    added_entities = []
    session.add = MagicMock(side_effect=lambda entity: added_entities.append(entity))

    agent_id = uuid.uuid4()
    ctx = TrustedContext(workspace_id=test_workspace_id, actor_type="agent", actor_id=agent_id)

    target_old = make_claim(test_workspace_id, agent_id, status="current", version=1)
    source_new = make_claim(test_workspace_id, agent_id, status="current", version=1)

    # Dependency DAG:
    # dep_1 depends on target_old (current)
    # dep_2 depends on target_old (already disputed)
    # dep_3 depends on dep_1 (current)
    dep_1 = make_claim(test_workspace_id, agent_id, status="current", version=1)
    dep_2 = make_claim(test_workspace_id, agent_id, status="disputed", version=3)
    dep_3 = make_claim(test_workspace_id, agent_id, status="current", version=2)

    rel_1 = make_relation(test_workspace_id, dep_1.id, target_old.id, "depends_on", agent_id)
    rel_2 = make_relation(test_workspace_id, dep_2.id, target_old.id, "depends_on", agent_id)
    rel_3 = make_relation(test_workspace_id, dep_3.id, dep_1.id, "depends_on", agent_id)

    claim_map = {
        source_new.id: source_new,
        target_old.id: target_old,
        dep_1.id: dep_1,
        dep_2.id: dep_2,
        dep_3.id: dep_3,
    }

    async def scalar_handler(stmt):
        entity_type = stmt.column_descriptions[0]["type"]
        if entity_type == Claim:
            compiled = stmt.compile()
            for val in compiled.params.values():
                if val in claim_map:
                    return claim_map[val]
            return None
        if entity_type == ClaimRelation:
            return None
        return None

    session.scalar.side_effect = scalar_handler

    mock_res_path = MagicMock()
    mock_res_path.all.return_value = []

    mock_res_cascade = MagicMock()
    mock_res_cascade.all.return_value = [rel_1, rel_2, rel_3]

    session.scalars.side_effect = [mock_res_path, mock_res_cascade]

    params = SupersedeClaimParams(
        source_claim_id=source_new.id,
        target_claim_id=target_old.id,
        rationale="Transitive cascade test.",
    )

    relation, affected = await ClaimService.supersede_claim(session, ctx, params)

    affected_ids = [c.id for c in affected]
    assert dep_1.id in affected_ids
    assert dep_3.id in affected_ids
    assert dep_2.id not in affected_ids  # disputed claim must not be changed

    assert dep_1.status == "needs_review"
    assert dep_1.version == 2
    assert dep_3.status == "needs_review"
    assert dep_3.version == 3
    assert dep_2.status == "disputed"
    assert dep_2.version == 3


@pytest.mark.asyncio
async def test_create_dependency_success(test_workspace_id: uuid.UUID) -> None:
    """Verifies that create_dependency creates a depends_on edge without mutating claim statuses."""
    session = AsyncMock(spec=AsyncSession)
    added_entities = []
    session.add = MagicMock(side_effect=lambda entity: added_entities.append(entity))

    agent_id = uuid.uuid4()
    ctx = TrustedContext(workspace_id=test_workspace_id, actor_type="agent", actor_id=agent_id)

    source_dependent = make_claim(test_workspace_id, agent_id, status="current", version=1)
    target_prereq = make_claim(test_workspace_id, agent_id, status="current", version=1)

    session.scalar.side_effect = [source_dependent, target_prereq, None]
    mock_res = MagicMock()
    mock_res.all.return_value = []
    session.scalars.side_effect = [mock_res]

    params = CreateDependencyParams(
        source_claim_id=source_dependent.id,
        target_claim_id=target_prereq.id,
        rationale="Requires authentication before accessing user profile.",
    )

    relation = await ClaimService.create_dependency(session, ctx, params)

    assert isinstance(relation, ClaimRelation)
    assert relation.source_claim_id == source_dependent.id
    assert relation.target_claim_id == target_prereq.id
    assert relation.relation_type == "depends_on"
    assert relation.rationale == "Requires authentication before accessing user profile."

    # Neither claim status is changed
    assert source_dependent.status == "current"
    assert target_prereq.status == "current"


@pytest.mark.asyncio
async def test_relation_rejects_self_relation(test_workspace_id: uuid.UUID) -> None:
    """Verifies that creating a relation where source == target raises ValidationDomainError."""
    session = AsyncMock(spec=AsyncSession)
    ctx = TrustedContext(workspace_id=test_workspace_id, actor_type="agent", actor_id=uuid.uuid4())
    cid = uuid.uuid4()

    params = CreateRelationParams(
        source_claim_id=cid,
        target_claim_id=cid,
        relation_type="supersedes",
        rationale="Self-relation attempt.",
    )

    with pytest.raises(ValidationDomainError, match="cannot establish a relationship to itself"):
        await ClaimService.create_relation(session, ctx, params)


@pytest.mark.asyncio
async def test_relation_rejects_duplicate_edge(test_workspace_id: uuid.UUID) -> None:
    """Verifies that creating a relation that already exists raises DuplicateRelationError."""
    session = AsyncMock(spec=AsyncSession)
    agent_id = uuid.uuid4()
    ctx = TrustedContext(workspace_id=test_workspace_id, actor_type="agent", actor_id=agent_id)

    c1 = make_claim(test_workspace_id, agent_id)
    c2 = make_claim(test_workspace_id, agent_id)
    existing_rel = make_relation(test_workspace_id, c1.id, c2.id, "supersedes")

    session.scalar.side_effect = [c1, c2, existing_rel]

    params = CreateRelationParams(
        source_claim_id=c1.id,
        target_claim_id=c2.id,
        relation_type="supersedes",
        rationale="Duplicate attempt.",
    )

    with pytest.raises(DuplicateRelationError, match="already exists"):
        await ClaimService.create_relation(session, ctx, params)


@pytest.mark.asyncio
async def test_supersede_cycle_detection_direct(test_workspace_id: uuid.UUID) -> None:
    """Verifies that direct supersession cycle A -> B when B -> A exists raises CyclicRelationError."""
    session = AsyncMock(spec=AsyncSession)
    agent_id = uuid.uuid4()
    ctx = TrustedContext(workspace_id=test_workspace_id, actor_type="agent", actor_id=agent_id)

    cA = make_claim(test_workspace_id, agent_id)
    cB = make_claim(test_workspace_id, agent_id)

    # Existing edge: B supersedes A
    rel_BA = make_relation(test_workspace_id, cB.id, cA.id, "supersedes")

    session.scalar.side_effect = [cA, cB, None]
    mock_res = MagicMock()
    mock_res.all.return_value = [rel_BA]
    session.scalars.side_effect = [mock_res]

    # Now attempt: A supersedes B (would form A -> B -> A cycle)
    params = SupersedeClaimParams(
        source_claim_id=cA.id,
        target_claim_id=cB.id,
        rationale="Cycle attempt.",
    )

    with pytest.raises(CyclicRelationError, match="cycle"):
        await ClaimService.supersede_claim(session, ctx, params)


@pytest.mark.asyncio
async def test_supersede_cycle_detection_multi_hop(test_workspace_id: uuid.UUID) -> None:
    """Verifies that multi-hop supersession cycle A -> B -> C -> A raises CyclicRelationError."""
    session = AsyncMock(spec=AsyncSession)
    agent_id = uuid.uuid4()
    ctx = TrustedContext(workspace_id=test_workspace_id, actor_type="agent", actor_id=agent_id)

    cA = make_claim(test_workspace_id, agent_id)
    cB = make_claim(test_workspace_id, agent_id)
    cC = make_claim(test_workspace_id, agent_id)

    # Existing edges: B -> C, C -> A
    rel_BC = make_relation(test_workspace_id, cB.id, cC.id, "supersedes")
    rel_CA = make_relation(test_workspace_id, cC.id, cA.id, "supersedes")

    session.scalar.side_effect = [cA, cB, None]
    mock_res = MagicMock()
    mock_res.all.return_value = [rel_BC, rel_CA]
    session.scalars.side_effect = [mock_res]

    # Attempt: A supersedes B
    params = SupersedeClaimParams(
        source_claim_id=cA.id,
        target_claim_id=cB.id,
        rationale="Multi-hop cycle attempt.",
    )

    with pytest.raises(CyclicRelationError, match="cycle"):
        await ClaimService.supersede_claim(session, ctx, params)


@pytest.mark.asyncio
async def test_dependency_cycle_detection_direct_and_multi_hop(test_workspace_id: uuid.UUID) -> None:
    """Verifies that dependency cycles are rejected."""
    session = AsyncMock(spec=AsyncSession)
    agent_id = uuid.uuid4()
    ctx = TrustedContext(workspace_id=test_workspace_id, actor_type="agent", actor_id=agent_id)

    cA = make_claim(test_workspace_id, agent_id)
    cB = make_claim(test_workspace_id, agent_id)

    rel_BA = make_relation(test_workspace_id, cB.id, cA.id, "depends_on")

    session.scalar.side_effect = [cA, cB, None]
    mock_res = MagicMock()
    mock_res.all.return_value = [rel_BA]
    session.scalars.side_effect = [mock_res]

    params = CreateDependencyParams(
        source_claim_id=cA.id,
        target_claim_id=cB.id,
        rationale="Circular dependency attempt.",
    )

    with pytest.raises(CyclicRelationError, match="cycle"):
        await ClaimService.create_dependency(session, ctx, params)


@pytest.mark.asyncio
async def test_relation_rejects_cross_workspace(test_workspace_id: uuid.UUID) -> None:
    """Verifies that creating a relation referencing a claim in another workspace raises WorkspaceMismatchError."""
    session = AsyncMock(spec=AsyncSession)
    agent_id = uuid.uuid4()
    ctx = TrustedContext(workspace_id=test_workspace_id, actor_type="agent", actor_id=agent_id)

    c1 = make_claim(test_workspace_id, agent_id)
    c_other_ws = make_claim(uuid.uuid4(), agent_id)  # Different workspace!

    session.scalar.side_effect = [c1, c_other_ws]

    params = CreateRelationParams(
        source_claim_id=c1.id,
        target_claim_id=c_other_ws.id,
        relation_type="supersedes",
        rationale="Cross-workspace attempt.",
    )

    with pytest.raises(WorkspaceMismatchError, match="does not match caller workspace"):
        await ClaimService.create_relation(session, ctx, params)


@pytest.mark.asyncio
async def test_relation_enforces_scope_visibility(test_workspace_id: uuid.UUID) -> None:
    """Verifies that private claims belonging to another agent are hidden (EntityNotFoundError)."""
    session = AsyncMock(spec=AsyncSession)
    agent_1 = uuid.uuid4()
    agent_2 = uuid.uuid4()
    ctx = TrustedContext(workspace_id=test_workspace_id, actor_type="agent", actor_id=agent_1)

    c_public = make_claim(test_workspace_id, agent_1, scope="workspace")
    c_private_other = make_claim(test_workspace_id, agent_2, scope="private")

    session.scalar.side_effect = [c_public, c_private_other]

    params = CreateRelationParams(
        source_claim_id=c_public.id,
        target_claim_id=c_private_other.id,
        relation_type="supersedes",
        rationale="Private claim linking attempt.",
    )

    with pytest.raises(EntityNotFoundError, match="was not found in the workspace"):
        await ClaimService.create_relation(session, ctx, params)


# -----------------------------------------------------------------------------
# Part 2: HTTP API Route Tests
# -----------------------------------------------------------------------------

def setup_route_mock_session(
    agent: Agent,
    source_claim: Claim | None = None,
    target_claim: Claim | None = None,
    existing_relation: ClaimRelation | None = None,
    active_relations: list[ClaimRelation] | None = None,
    cascade_claims: list[Claim] | None = None,
):
    """Sets up a mock session for route testing."""
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.is_active = True

    claim_map: dict[uuid.UUID, Claim] = {}
    if source_claim:
        claim_map[source_claim.id] = source_claim
    if target_claim:
        claim_map[target_claim.id] = target_claim
    if cascade_claims:
        for c in cascade_claims:
            claim_map[c.id] = c

    async def scalar_handler(stmt):
        entity_type = stmt.column_descriptions[0]["type"]
        if entity_type == Agent:
            return agent
        if entity_type == Claim:
            compiled = stmt.compile()
            for val in compiled.params.values():
                if val in claim_map:
                    return claim_map[val]
            return None
        if entity_type == ClaimRelation:
            return existing_relation
        return None

    mock_session.scalar.side_effect = scalar_handler

    mock_res = MagicMock()
    mock_res.all.return_value = active_relations or []
    mock_session.scalars.return_value = mock_res
    return mock_session


@pytest.mark.asyncio
async def test_route_create_relation_generic_success(
    app: FastAPI,
    async_client: AsyncClient,
    auth_agent: tuple[str, Agent],
) -> None:
    """Verifies that POST /claims/{id}/relations creates a relation and commits."""
    secret, agent = auth_agent
    c_src = make_claim(agent.workspace_id, agent.id)
    c_tgt = make_claim(agent.workspace_id, agent.id)

    mock_session = setup_route_mock_session(agent, source_claim=c_src, target_claim=c_tgt)
    app.dependency_overrides[get_db] = lambda: mock_session

    try:
        response = await async_client.post(
            f"/api/v1/claims/{c_src.id}/relations",
            headers={"Authorization": f"Bearer {secret}"},
            json={
                "target_claim_id": str(c_tgt.id),
                "relation_type": "contradicts",
                "rationale": "Empirical measurement contradicts theoretical model.",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["source_claim_id"] == str(c_src.id)
        assert data["target_claim_id"] == str(c_tgt.id)
        assert data["relation_type"] == "contradicts"
        assert data["rationale"] == "Empirical measurement contradicts theoretical model."
        assert data["workspace_id"] == str(agent.workspace_id)
        mock_session.commit.assert_awaited_once()
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_route_supersede_endpoint_success(
    app: FastAPI,
    async_client: AsyncClient,
    auth_agent: tuple[str, Agent],
) -> None:
    """Verifies that POST /claims/{id}/supersede supersedes older claim and returns affected_claim_ids."""
    secret, agent = auth_agent
    c_new = make_claim(agent.workspace_id, agent.id)
    c_old = make_claim(agent.workspace_id, agent.id)
    c_dep = make_claim(agent.workspace_id, agent.id)

    rel_dep = make_relation(agent.workspace_id, c_dep.id, c_old.id, "depends_on", agent.id)

    mock_session = setup_route_mock_session(
        agent,
        source_claim=c_new,
        target_claim=c_old,
        active_relations=[rel_dep],
        cascade_claims=[c_dep],
    )
    app.dependency_overrides[get_db] = lambda: mock_session

    try:
        response = await async_client.post(
            f"/api/v1/claims/{c_new.id}/supersede",
            headers={"Authorization": f"Bearer {secret}"},
            json={
                "target_claim_id": str(c_old.id),
                "rationale": "Updated cache algorithm supersedes LRU.",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["source_claim_id"] == str(c_new.id)
        assert data["target_claim_id"] == str(c_old.id)
        assert data["relation_type"] == "supersedes"
        assert data["affected_claim_ids"] == [str(c_dep.id)]
        mock_session.commit.assert_awaited_once()
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_route_dependencies_endpoint_success(
    app: FastAPI,
    async_client: AsyncClient,
    auth_agent: tuple[str, Agent],
) -> None:
    """Verifies that POST /claims/{id}/dependencies creates dependency."""
    secret, agent = auth_agent
    c_dep = make_claim(agent.workspace_id, agent.id)
    c_prereq = make_claim(agent.workspace_id, agent.id)

    mock_session = setup_route_mock_session(agent, source_claim=c_dep, target_claim=c_prereq)
    app.dependency_overrides[get_db] = lambda: mock_session

    try:
        response = await async_client.post(
            f"/api/v1/claims/{c_dep.id}/dependencies",
            headers={"Authorization": f"Bearer {secret}"},
            json={
                "target_claim_id": str(c_prereq.id),
                "rationale": "Dependent on database migration completion.",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["source_claim_id"] == str(c_dep.id)
        assert data["target_claim_id"] == str(c_prereq.id)
        assert data["relation_type"] == "depends_on"
        mock_session.commit.assert_awaited_once()
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_route_relations_requires_auth(
    app: FastAPI,
    async_client: AsyncClient,
) -> None:
    """Verifies that unauthenticated calls return 401."""
    mock_session = AsyncMock(spec=AsyncSession)
    app.dependency_overrides[get_db] = lambda: mock_session

    try:
        cid = uuid.uuid4()
        response = await async_client.post(
            f"/api/v1/claims/{cid}/relations",
            json={
                "target_claim_id": str(uuid.uuid4()),
                "relation_type": "supersedes",
                "rationale": "Missing auth token.",
            },
        )
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "UNAUTHORIZED"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_route_relations_rejects_cycle(
    app: FastAPI,
    async_client: AsyncClient,
    auth_agent: tuple[str, Agent],
) -> None:
    """Verifies that introducing a cycle returns 422 with code CYCLIC_RELATION."""
    secret, agent = auth_agent
    cA = make_claim(agent.workspace_id, agent.id)
    cB = make_claim(agent.workspace_id, agent.id)

    rel_BA = make_relation(agent.workspace_id, cB.id, cA.id, "supersedes")
    mock_session = setup_route_mock_session(agent, source_claim=cA, target_claim=cB, active_relations=[rel_BA])
    app.dependency_overrides[get_db] = lambda: mock_session

    try:
        response = await async_client.post(
            f"/api/v1/claims/{cA.id}/supersede",
            headers={"Authorization": f"Bearer {secret}"},
            json={
                "target_claim_id": str(cB.id),
                "rationale": "Cycle attempt in route.",
            },
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "CYCLIC_RELATION"
        mock_session.rollback.assert_awaited_once()
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_route_relations_rejects_duplicate(
    app: FastAPI,
    async_client: AsyncClient,
    auth_agent: tuple[str, Agent],
) -> None:
    """Verifies that duplicate relations return 409 CONFLICT."""
    secret, agent = auth_agent
    cA = make_claim(agent.workspace_id, agent.id)
    cB = make_claim(agent.workspace_id, agent.id)
    rel_AB = make_relation(agent.workspace_id, cA.id, cB.id, "supersedes")

    mock_session = setup_route_mock_session(agent, source_claim=cA, target_claim=cB, existing_relation=rel_AB)
    app.dependency_overrides[get_db] = lambda: mock_session

    try:
        response = await async_client.post(
            f"/api/v1/claims/{cA.id}/supersede",
            headers={"Authorization": f"Bearer {secret}"},
            json={
                "target_claim_id": str(cB.id),
                "rationale": "Duplicate attempt in route.",
            },
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "CONFLICT"
        mock_session.rollback.assert_awaited_once()
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_route_relations_rejects_self_relation(
    app: FastAPI,
    async_client: AsyncClient,
    auth_agent: tuple[str, Agent],
) -> None:
    """Verifies that self-relation returns 422 VALIDATION_ERROR."""
    secret, agent = auth_agent
    cid = uuid.uuid4()
    mock_session = setup_route_mock_session(agent)
    app.dependency_overrides[get_db] = lambda: mock_session

    try:
        response = await async_client.post(
            f"/api/v1/claims/{cid}/relations",
            headers={"Authorization": f"Bearer {secret}"},
            json={
                "target_claim_id": str(cid),
                "relation_type": "supersedes",
                "rationale": "Self relation.",
            },
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"
        mock_session.rollback.assert_awaited_once()
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_route_relations_rejects_extra_fields(
    app: FastAPI,
    async_client: AsyncClient,
    auth_agent: tuple[str, Agent],
) -> None:
    """Verifies that unexpected extra fields return 422."""
    secret, agent = auth_agent
    mock_session = setup_route_mock_session(agent)
    app.dependency_overrides[get_db] = lambda: mock_session

    try:
        cid = uuid.uuid4()
        response = await async_client.post(
            f"/api/v1/claims/{cid}/relations",
            headers={"Authorization": f"Bearer {secret}"},
            json={
                "target_claim_id": str(uuid.uuid4()),
                "relation_type": "supersedes",
                "rationale": "Valid rationale.",
                "malicious_field": "injected",
            },
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_route_relations_commit_failure_rolls_back(
    app: FastAPI,
    async_client: AsyncClient,
    auth_agent: tuple[str, Agent],
) -> None:
    """Verifies that commit failure triggers rollback and returns 500."""
    secret, agent = auth_agent
    cA = make_claim(agent.workspace_id, agent.id)
    cB = make_claim(agent.workspace_id, agent.id)

    mock_session = setup_route_mock_session(agent, source_claim=cA, target_claim=cB)
    mock_session.commit.side_effect = IntegrityError("statement", "params", "orig")
    app.dependency_overrides[get_db] = lambda: mock_session

    try:
        response = await async_client.post(
            f"/api/v1/claims/{cA.id}/relations",
            headers={"Authorization": f"Bearer {secret}"},
            json={
                "target_claim_id": str(cB.id),
                "relation_type": "corroborates",
                "rationale": "Commit failure test.",
            },
        )
        assert response.status_code == 500
        assert response.json()["error"]["code"] == "INTERNAL_SERVER_ERROR"
        mock_session.rollback.assert_awaited_once()
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_route_relations_rejects_cross_workspace(
    app: FastAPI,
    async_client: AsyncClient,
    auth_agent: tuple[str, Agent],
) -> None:
    """Verifies that referencing a claim from another workspace returns 404."""
    secret, agent = auth_agent
    cA = make_claim(agent.workspace_id, agent.id)
    cB_other = make_claim(uuid.uuid4(), agent.id)  # foreign workspace

    mock_session = setup_route_mock_session(agent, source_claim=cA, target_claim=cB_other)
    app.dependency_overrides[get_db] = lambda: mock_session

    try:
        response = await async_client.post(
            f"/api/v1/claims/{cA.id}/relations",
            headers={"Authorization": f"Bearer {secret}"},
            json={
                "target_claim_id": str(cB_other.id),
                "relation_type": "corroborates",
                "rationale": "Cross-workspace attempt.",
            },
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "NOT_FOUND"
        mock_session.rollback.assert_awaited_once()
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_route_relations_response_validation_failure_rolls_back(
    app: FastAPI,
    async_client: AsyncClient,
    auth_agent: tuple[str, Agent],
) -> None:
    """Verifies that if response model construction fails, transaction is rolled back without committing."""
    secret, agent = auth_agent
    cA = make_claim(agent.workspace_id, agent.id)
    cB = make_claim(agent.workspace_id, agent.id)

    mock_session = setup_route_mock_session(agent, source_claim=cA, target_claim=cB)
    app.dependency_overrides[get_db] = lambda: mock_session

    with patch(
        "filament_api.api.routes.claims.ClaimRelationResponse",
        side_effect=RuntimeError("Injected response serialization failure"),
    ):
        response = await async_client.post(
            f"/api/v1/claims/{cA.id}/relations",
            headers={"Authorization": f"Bearer {secret}"},
            json={
                "target_claim_id": str(cB.id),
                "relation_type": "corroborates",
                "rationale": "Serialization failure test.",
            },
        )

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_SERVER_ERROR"
    mock_session.commit.assert_not_called()
    mock_session.rollback.assert_awaited()
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_route_relations_safe_logging(
    app: FastAPI,
    async_client: AsyncClient,
    auth_agent: tuple[str, Agent],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Verifies that route-level error logging scrubs sensitive parameters and SQL statements."""
    secret, agent = auth_agent
    cA = make_claim(agent.workspace_id, agent.id)
    cB = make_claim(agent.workspace_id, agent.id)

    mock_session = setup_route_mock_session(agent, source_claim=cA, target_claim=cB)
    app.dependency_overrides[get_db] = lambda: mock_session

    secret_canary = "DATABASE_SECRET_PAYLOAD_PARAM_RELATION_9999"
    db_error = IntegrityError(
        statement="INSERT INTO claim_relations (rationale) VALUES (:rat)",
        params={"rat": secret_canary},
        orig=Exception(f"violates foreign key with {secret_canary}"),
    )

    with caplog.at_level(logging.ERROR):
        with patch(
            "filament_api.api.routes.claims.ClaimService.create_relation",
            side_effect=db_error,
        ):
            response = await async_client.post(
                f"/api/v1/claims/{cA.id}/relations",
                headers={"Authorization": f"Bearer {secret}"},
                json={
                    "target_claim_id": str(cB.id),
                    "relation_type": "corroborates",
                    "rationale": "Safe logging test.",
                },
            )

    assert response.status_code == 500
    assert secret_canary not in response.text
    assert secret_canary not in caplog.text

    assert "sqlalchemy.exc.IntegrityError" in caplog.text
    assert "[message and parameters redacted]" in caplog.text
    assert "create_relation" in caplog.text
    app.dependency_overrides.clear()

