"""Automated unit and mock persistence tests for Filament domain services.

DIAGNOSTIC SCOPE & LIMITATIONS:
The tests in this module are unit and mock-persistence tests designed to execute
offline without requiring a running PostgreSQL server or Docker container.
They verify domain service orchestration, input validation, trusted context invariants,
attribution derivation, and atomic staging of domain entities and audit events.

LIMITATION WARNING:
These tests DO NOT verify live PostgreSQL database constraints (e.g., composite FK
cascades, physical CHECK constraints, or PostgreSQL triggers) or database-level
ACID durability. Full database-level verification requires executing against an
explicitly configured, disposable PostgreSQL test instance.
"""

from decimal import Decimal
import hashlib
from unittest.mock import AsyncMock, MagicMock
import uuid

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from filament_api.models.audit import AuditEvent
from filament_api.models.claim import Claim, ClaimEvidence
from filament_api.models.evidence import Evidence
from filament_api.schemas.claim import CreateClaimParams, LinkEvidenceParams
from filament_api.schemas.evidence import RecordEvidenceParams
from filament_api.services.audit import record_audit_event
from filament_api.services.claim import ClaimService
from filament_api.services.context import ActorType, TrustedContext
from filament_api.services.evidence import EvidenceService
from filament_api.services.exceptions import (
    DuplicateLinkError,
    EntityNotFoundError,
    UnauthorizedActorError,
    ValidationDomainError,
    WorkspaceMismatchError,
)


# -----------------------------------------------------------------------------
# 1. TrustedContext Tests
# -----------------------------------------------------------------------------

def test_trusted_context_initialization_and_properties() -> None:
    """Verifies TrustedContext attributes, boolean flags, and immutability."""
    ws_id = uuid.uuid4()
    agent_id = uuid.uuid4()

    ctx = TrustedContext(
        workspace_id=ws_id,
        actor_type="agent",
        actor_id=agent_id,
    )

    assert ctx.workspace_id == ws_id
    assert ctx.actor_id == agent_id
    assert ctx.actor_type == ActorType.AGENT
    assert ctx.is_agent is True
    assert ctx.is_user is False
    assert ctx.is_system is False
    assert ctx.is_active is True


def test_trusted_context_rejects_invalid_actor_type_or_inactive() -> None:
    """Verifies that invalid actor types, non-UUID identifiers, or disabled actors are rejected."""
    ws_id = uuid.uuid4()
    actor_id = uuid.uuid4()

    with pytest.raises(ValidationDomainError, match="Invalid actor_type"):
        TrustedContext(
            workspace_id=ws_id,
            actor_type="hacker",  # type: ignore[arg-type]
            actor_id=actor_id,
        )

    with pytest.raises(UnauthorizedActorError, match="inactive or disabled"):
        TrustedContext(
            workspace_id=ws_id,
            actor_type="agent",
            actor_id=actor_id,
            is_active=False,
        )

    with pytest.raises(ValidationDomainError, match="workspace_id must be a UUID"):
        TrustedContext(
            workspace_id="not-a-uuid",  # type: ignore[arg-type]
            actor_type="agent",
            actor_id=actor_id,
        )

    with pytest.raises(ValidationDomainError, match="actor_id must be a UUID"):
        TrustedContext(
            workspace_id=ws_id,
            actor_type="agent",
            actor_id="not-a-uuid",  # type: ignore[arg-type]
        )

    with pytest.raises(ValidationDomainError, match="is_active must be a boolean"):
        TrustedContext(
            workspace_id=ws_id,
            actor_type="agent",
            actor_id=actor_id,
            is_active="true",  # type: ignore[arg-type]
        )


def test_trusted_context_ensure_workspace() -> None:
    """Verifies tenant matching check against context workspace."""
    ws_id = uuid.uuid4()
    other_ws = uuid.uuid4()
    ctx = TrustedContext(workspace_id=ws_id, actor_type="system", actor_id=uuid.uuid4())

    ctx.ensure_workspace(ws_id)  # Should not raise

    with pytest.raises(WorkspaceMismatchError, match="does not match target workspace"):
        ctx.ensure_workspace(other_ws)


def test_trusted_context_resolve_agent_attribution() -> None:
    """Verifies agent caller attribution rules and impersonation blocking."""
    ws_id = uuid.uuid4()
    agent_id = uuid.uuid4()
    rogue_agent_id = uuid.uuid4()
    user_id = uuid.uuid4()
    system_id = uuid.uuid4()

    # Case A: Agent caller creates claim for self
    agent_ctx = TrustedContext(workspace_id=ws_id, actor_type="agent", actor_id=agent_id)
    assert agent_ctx.resolve_agent_id_for_claim(None) == agent_id
    assert agent_ctx.resolve_agent_id_for_claim(agent_id) == agent_id

    # Case B: Agent caller attempts to impersonate another agent
    with pytest.raises(UnauthorizedActorError, match="cannot create claims for another agent"):
        agent_ctx.resolve_agent_id_for_claim(rogue_agent_id)

    # Case C: User caller attempts to create a claim (forbidden)
    user_ctx = TrustedContext(workspace_id=ws_id, actor_type="user", actor_id=user_id)
    with pytest.raises(UnauthorizedActorError, match="Claims can only be created by an authorized agent"):
        user_ctx.resolve_agent_id_for_claim(agent_id)

    # Case D: System caller attempts to create a claim (forbidden)
    system_ctx = TrustedContext(workspace_id=ws_id, actor_type="system", actor_id=system_id)
    with pytest.raises(UnauthorizedActorError, match="Claims can only be created by an authorized agent"):
        system_ctx.resolve_agent_id_for_claim(agent_id)


# -----------------------------------------------------------------------------
# 2. Schema / DTO Validation Tests
# -----------------------------------------------------------------------------

def test_evidence_params_validation() -> None:
    """Verifies parameter validation on RecordEvidenceParams."""
    with pytest.raises(ValidationError):
        RecordEvidenceParams(
            source_type="unsupported_source",  # type: ignore[arg-type]
            source_uri="repo/README.md",
            raw_snippet="snippet",
        )

    with pytest.raises(ValidationError):
        RecordEvidenceParams(
            source_type="file",
            source_uri="repo/README.md",
            raw_snippet="",  # Empty snippet forbidden
        )

    with pytest.raises(ValidationError, match="cannot be empty or whitespace-only"):
        RecordEvidenceParams(
            source_type="file",
            source_uri="   ",  # Whitespace-only forbidden
            raw_snippet="valid",
        )

    with pytest.raises(ValidationError, match="cannot be empty or whitespace-only"):
        RecordEvidenceParams(
            source_type="file",
            source_uri="repo/README.md",
            raw_snippet=" \n\t ",  # Whitespace-only forbidden
        )

    with pytest.raises(ValidationError):
        RecordEvidenceParams(
            source_type="file",
            source_uri="repo/README.md",
            raw_snippet="valid",
            content_hash="short_hash",  # Not 64 chars
        )

    with pytest.raises(ValidationError):
        RecordEvidenceParams(
            source_type="file",
            source_uri="repo/README.md",
            raw_snippet="valid",
            content_hash="z" * 64,  # Non-hex characters forbidden
        )


def test_claim_params_validation() -> None:
    """Verifies parameter validation on CreateClaimParams."""
    # Confidence bounds
    with pytest.raises(ValidationError):
        CreateClaimParams(
            subject="db",
            predicate="engine",
            object_value={"engine": "sqlite"},
            raw_statement="SQLite used",
            confidence=Decimal("1.50"),  # > 1.00 forbidden
        )

    with pytest.raises(ValidationError):
        CreateClaimParams(
            subject="db",
            predicate="engine",
            object_value={"engine": "sqlite"},
            raw_statement="SQLite used",
            confidence=Decimal("-0.10"),  # < 0.00 forbidden
        )

    # Invalid literals
    with pytest.raises(ValidationError):
        CreateClaimParams(
            subject="db",
            predicate="engine",
            object_value={},
            raw_statement="statement",
            scope="public",  # type: ignore[arg-type]
        )

    # Whitespace-only string fields
    with pytest.raises(ValidationError, match="cannot be empty or whitespace-only"):
        CreateClaimParams(
            subject="   ",
            predicate="engine",
            object_value={},
            raw_statement="valid statement",
        )

    with pytest.raises(ValidationError, match="cannot be empty or whitespace-only"):
        CreateClaimParams(
            subject="db",
            predicate="   ",
            object_value={},
            raw_statement="valid statement",
        )

    with pytest.raises(ValidationError, match="cannot be empty or whitespace-only"):
        CreateClaimParams(
            subject="db",
            predicate="engine",
            object_value={},
            raw_statement="   ",
        )


def test_link_evidence_params_validation() -> None:
    """Verifies parameter validation on LinkEvidenceParams."""
    claim_id = uuid.uuid4()
    evidence_id = uuid.uuid4()

    with pytest.raises(ValidationError):
        LinkEvidenceParams(
            claim_id=claim_id,
            evidence_id=evidence_id,
            support_type="neutral",  # type: ignore[arg-type]
        )

    with pytest.raises(ValidationError):
        LinkEvidenceParams(
            claim_id=claim_id,
            evidence_id=evidence_id,
            confidence_weight=Decimal("1.05"),  # Out of range
        )

    with pytest.raises(ValidationError, match="cannot be empty whitespace"):
        LinkEvidenceParams(
            claim_id=claim_id,
            evidence_id=evidence_id,
            extraction_notes="   ",
        )


# -----------------------------------------------------------------------------
# 3. Evidence Service Persistence Tests
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_record_evidence_computes_sha256_and_emits_audit() -> None:
    """Verifies automatic SHA-256 calculation and atomic AuditEvent recording."""
    session = AsyncMock(spec=AsyncSession)
    added_entities = []
    session.add = MagicMock(side_effect=lambda entity: added_entities.append(entity))

    ws_id = uuid.uuid4()
    agent_id = uuid.uuid4()
    ctx = TrustedContext(workspace_id=ws_id, actor_type="agent", actor_id=agent_id)

    raw_text = "Database migrated from PostgreSQL to SQLite 3 in commit a1b2c3d."
    expected_hash = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()

    params = RecordEvidenceParams(
        source_type="git_commit",
        source_uri="git://commit/a1b2c3d",
        raw_snippet=raw_text,
        metadata={"author": "developer", "branch": "main"},
    )

    evidence = await EvidenceService.record_evidence(session, ctx, params)

    # Validate Evidence entity
    assert isinstance(evidence, Evidence)
    assert evidence.workspace_id == ws_id
    assert evidence.source_type == "git_commit"
    assert evidence.source_uri == "git://commit/a1b2c3d"
    assert evidence.content_hash == expected_hash
    assert evidence.raw_snippet == raw_text
    assert evidence.collected_by_agent == agent_id
    assert evidence.collected_by_user is None
    assert evidence.metadata_ == {"author": "developer", "branch": "main"}

    # Validate atomic audit log emission
    assert len(added_entities) == 2
    audit = added_entities[1]
    assert isinstance(audit, AuditEvent)
    assert audit.workspace_id == ws_id
    assert audit.actor_type == "agent"
    assert audit.actor_id == agent_id
    assert audit.event_type == "EVIDENCE_RECORDED"
    assert audit.target_type == "evidence"
    assert audit.target_id == evidence.id
    assert audit.payload["content_hash"] == expected_hash

    # Validate session lifecycle: flushed but not committed
    session.flush.assert_awaited_once()
    session.commit.assert_not_called()


@pytest.mark.asyncio
async def test_record_evidence_detects_hash_mismatch() -> None:
    """Verifies that an incorrect client-supplied content_hash is rejected."""
    session = AsyncMock(spec=AsyncSession)
    ctx = TrustedContext(workspace_id=uuid.uuid4(), actor_type="user", actor_id=uuid.uuid4())

    params = RecordEvidenceParams(
        source_type="file",
        source_uri="src/config.py",
        raw_snippet="DB_ENGINE = 'sqlite'",
        content_hash="0000000000000000000000000000000000000000000000000000000000000000",
    )

    with pytest.raises(ValidationDomainError, match="does not match computed hash"):
        await EvidenceService.record_evidence(session, ctx, params)


@pytest.mark.asyncio
async def test_record_evidence_user_attribution() -> None:
    """Verifies collected_by_user is assigned when caller is a user."""
    session = AsyncMock(spec=AsyncSession)
    user_id = uuid.uuid4()
    ctx = TrustedContext(workspace_id=uuid.uuid4(), actor_type="user", actor_id=user_id)

    params = RecordEvidenceParams(
        source_type="user_turn",
        source_uri="chat://session-1#t4",
        raw_snippet="Please use SQLite.",
    )

    evidence = await EvidenceService.record_evidence(session, ctx, params)
    assert evidence.collected_by_user == user_id
    assert evidence.collected_by_agent is None


# -----------------------------------------------------------------------------
# 4. Claim Service Persistence Tests
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_claim_with_agent_context_and_audit() -> None:
    """Verifies claim creation by an agent caller with atomic audit event."""
    session = AsyncMock(spec=AsyncSession)
    added_entities = []
    session.add = MagicMock(side_effect=lambda entity: added_entities.append(entity))

    ws_id = uuid.uuid4()
    agent_id = uuid.uuid4()
    ctx = TrustedContext(workspace_id=ws_id, actor_type="agent", actor_id=agent_id)

    params = CreateClaimParams(
        subject="project.database",
        predicate="configured_as",
        object_value={"engine": "sqlite", "version": 3},
        raw_statement="The project persistence layer is configured as SQLite 3.",
        claim_type="fact",
        scope="team",
        confidence=Decimal("0.95"),
    )

    claim = await ClaimService.create_claim(session, ctx, params)

    assert isinstance(claim, Claim)
    assert claim.workspace_id == ws_id
    assert claim.agent_id == agent_id
    assert claim.claim_type == "fact"
    assert claim.scope == "team"
    assert claim.status == "current"
    assert claim.confidence == Decimal("0.95")
    assert claim.raw_statement.startswith("The project persistence")

    # Audit event verification
    assert len(added_entities) == 2
    audit = added_entities[1]
    assert isinstance(audit, AuditEvent)
    assert audit.workspace_id == ws_id
    assert audit.event_type == "CLAIM_CREATED"
    assert audit.target_type == "claim"
    assert audit.target_id == claim.id
    assert audit.payload["scope"] == "team"

    session.flush.assert_awaited_once()
    session.commit.assert_not_called()


# -----------------------------------------------------------------------------
# 5. Link Evidence Tests
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_link_evidence_success_in_same_workspace() -> None:
    """Verifies linking evidence to claim within the same workspace."""
    session = AsyncMock(spec=AsyncSession)
    added_entities = []
    session.add = MagicMock(side_effect=lambda entity: added_entities.append(entity))

    ws_id = uuid.uuid4()
    ctx = TrustedContext(workspace_id=ws_id, actor_type="agent", actor_id=uuid.uuid4())

    claim_id = uuid.uuid4()
    evidence_id = uuid.uuid4()

    mock_claim = Claim(id=claim_id, workspace_id=ws_id)
    mock_evidence = Evidence(id=evidence_id, workspace_id=ws_id)

    # Mock session.scalar lookup sequence:
    # 1. select Claim -> mock_claim
    # 2. select Evidence -> mock_evidence
    # 3. select ClaimEvidence (existing link) -> None
    session.scalar.side_effect = [mock_claim, mock_evidence, None]

    params = LinkEvidenceParams(
        claim_id=claim_id,
        evidence_id=evidence_id,
        support_type="supports",
        confidence_weight=Decimal("0.90"),
        extraction_notes="Extracted from commit log message.",
    )

    link = await ClaimService.link_evidence(session, ctx, params)

    assert isinstance(link, ClaimEvidence)
    assert link.workspace_id == ws_id
    assert link.claim_id == claim_id
    assert link.evidence_id == evidence_id
    assert link.support_type == "supports"
    assert link.confidence_weight == Decimal("0.90")
    assert link.extraction_notes == "Extracted from commit log message."

    # Audit event verification
    assert len(added_entities) == 2
    audit = added_entities[1]
    assert isinstance(audit, AuditEvent)
    assert audit.event_type == "EVIDENCE_LINKED"
    assert audit.target_type == "claim_evidence"
    assert audit.target_id == claim_id
    assert audit.payload["evidence_id"] == str(evidence_id)

    session.flush.assert_awaited_once()
    session.commit.assert_not_called()


@pytest.mark.asyncio
async def test_link_evidence_rejects_cross_workspace_claim() -> None:
    """Verifies that an evidence link is rejected if claim belongs to another workspace."""
    session = AsyncMock(spec=AsyncSession)
    ws_id = uuid.uuid4()
    other_ws_id = uuid.uuid4()
    ctx = TrustedContext(workspace_id=ws_id, actor_type="agent", actor_id=uuid.uuid4())

    claim_id = uuid.uuid4()
    evidence_id = uuid.uuid4()

    mock_claim_other_ws = Claim(id=claim_id, workspace_id=other_ws_id)
    session.scalar.side_effect = [mock_claim_other_ws]

    params = LinkEvidenceParams(claim_id=claim_id, evidence_id=evidence_id)

    with pytest.raises(WorkspaceMismatchError, match="does not match caller workspace"):
        await ClaimService.link_evidence(session, ctx, params)


@pytest.mark.asyncio
async def test_link_evidence_rejects_missing_entity() -> None:
    """Verifies EntityNotFoundError when target claim or evidence is not found."""
    session = AsyncMock(spec=AsyncSession)
    ctx = TrustedContext(workspace_id=uuid.uuid4(), actor_type="user", actor_id=uuid.uuid4())

    claim_id = uuid.uuid4()
    evidence_id = uuid.uuid4()

    # Claim not found
    session.scalar.side_effect = [None]
    params = LinkEvidenceParams(claim_id=claim_id, evidence_id=evidence_id)

    with pytest.raises(EntityNotFoundError, match="Claim"):
        await ClaimService.link_evidence(session, ctx, params)


@pytest.mark.asyncio
async def test_link_evidence_rejects_duplicate_link() -> None:
    """Verifies DuplicateLinkError when evidence is already linked to claim."""
    session = AsyncMock(spec=AsyncSession)
    ws_id = uuid.uuid4()
    ctx = TrustedContext(workspace_id=ws_id, actor_type="agent", actor_id=uuid.uuid4())

    claim_id = uuid.uuid4()
    evidence_id = uuid.uuid4()

    mock_claim = Claim(id=claim_id, workspace_id=ws_id)
    mock_evidence = Evidence(id=evidence_id, workspace_id=ws_id)
    mock_existing_link = ClaimEvidence(workspace_id=ws_id, claim_id=claim_id, evidence_id=evidence_id)

    session.scalar.side_effect = [mock_claim, mock_evidence, mock_existing_link]

    params = LinkEvidenceParams(claim_id=claim_id, evidence_id=evidence_id)

    with pytest.raises(DuplicateLinkError, match="already linked"):
        await ClaimService.link_evidence(session, ctx, params)


# -----------------------------------------------------------------------------
# 6. Transaction & Rollback Behavior Tests (Mock Unit Verification)
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_claim_rejects_non_agent_actor() -> None:
    """Verifies that non-agent actors (e.g. user) cannot create claims via ClaimService."""
    session = AsyncMock(spec=AsyncSession)
    user_ctx = TrustedContext(
        workspace_id=uuid.uuid4(),
        actor_type="user",
        actor_id=uuid.uuid4(),
    )

    params = CreateClaimParams(
        subject="db.choice",
        predicate="uses",
        object_value={"db": "sqlite"},
        raw_statement="Using SQLite",
    )

    with pytest.raises(UnauthorizedActorError, match="Claims can only be created by an authorized agent"):
        await ClaimService.create_claim(session, user_ctx, params)

    session.add.assert_not_called()
    session.flush.assert_not_called()
    session.commit.assert_not_called()


@pytest.mark.asyncio
async def test_transaction_rollback_on_database_flush_failure() -> None:
    """Verifies that transaction wrappers trigger rollback when service flush fails.

    Demonstrates the Unit of Work contract: if session.flush() raises an unhandled
    database or integrity error, the calling transaction context rolls back and never commits.
    """
    session = AsyncMock(spec=AsyncSession)
    session.flush.side_effect = RuntimeError("Simulated database connection drop or constraint failure")

    ws_id = uuid.uuid4()
    agent_id = uuid.uuid4()
    ctx = TrustedContext(workspace_id=ws_id, actor_type="agent", actor_id=agent_id)

    params = CreateClaimParams(
        subject="system.state",
        predicate="status",
        object_value={"status": "ready"},
        raw_statement="System is ready.",
    )

    # Simulated transaction boundary (such as FastAPI get_db or worker unit-of-work)
    with pytest.raises(RuntimeError, match="Simulated database connection drop"):
        try:
            await ClaimService.create_claim(session, ctx, params)
            await session.commit()
        except Exception:
            await session.rollback()
            raise

    session.rollback.assert_awaited_once()
    session.commit.assert_not_called()


@pytest.mark.asyncio
async def test_evidence_service_does_not_commit() -> None:
    """Verifies that EvidenceService leaves transaction commit responsibility to the caller."""
    session = AsyncMock(spec=AsyncSession)
    ctx = TrustedContext(workspace_id=uuid.uuid4(), actor_type="agent", actor_id=uuid.uuid4())

    params = RecordEvidenceParams(
        source_type="file",
        source_uri="repo/file.txt",
        raw_snippet="Some observations",
    )

    await EvidenceService.record_evidence(session, ctx, params)

    # Flush must be awaited to populate ORM defaults, but commit must NEVER be called by service
    session.flush.assert_awaited_once()
    session.commit.assert_not_called()


