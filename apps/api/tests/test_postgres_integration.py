"""Step 26: Live PostgreSQL Integration and Concurrency Verification.

Validates Filament's actual persistence, constraints, transaction behavior,
immutability triggers, and row-level concurrency against a real PostgreSQL instance.
"""

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
import uuid
import pytest
import pytest_asyncio
import httpx
from sqlalchemy import delete, insert, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError, InternalError, ProgrammingError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from filament_api.config import Settings
from filament_api.core import hash_api_key
from filament_api.db.session import get_db
from filament_api.main import create_app
from filament_api.models.agent import Agent
from filament_api.models.audit import AuditEvent
from filament_api.models.claim import Claim, ClaimEvidence
from filament_api.models.relation import ClaimRelation
from filament_api.models.condition import (
    ClaimCondition,
    ClaimConditionSet,
    ClaimVerification,
)
from filament_api.models.evidence import Evidence
from filament_api.models.snapshot import EnvironmentSnapshot
from filament_api.models.user import User
from filament_api.models.workspace import Workspace
from filament_api.services.condition import ConditionService
from filament_api.services.context import TrustedContext
from filament_api.services.exceptions import StaleConditionVersionError
from filament_api.schemas.condition import ReverifyClaimParams, ConditionSpec

TEST_DB_URL = "postgresql+asyncpg://postgres@127.0.0.1:5433/filament_test"


from sqlalchemy.pool import NullPool

_test_engine = create_async_engine(
    TEST_DB_URL,
    poolclass=NullPool,
    echo=False,
)
_test_session_factory = async_sessionmaker(
    bind=_test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


@pytest.fixture
def pg_session_factory() -> async_sessionmaker[AsyncSession]:
    """Provide session factory for live PostgreSQL test database."""
    return _test_session_factory


@pytest_asyncio.fixture
async def pg_session() -> AsyncSession:
    """Provide a dedicated async session for a single test."""
    async with _test_session_factory() as session:
        yield session


@pytest_asyncio.fixture(autouse=True)
async def clean_database():
    """Clean all tables before each test while respecting triggers and foreign keys."""
    async with _test_engine.begin() as conn:
        await conn.execute(
            text(
                "TRUNCATE TABLE "
                "claim_verifications, claim_conditions, claim_condition_sets, environment_snapshots, "
                "claim_relations, claim_evidence, claims, evidence, audit_events, agents, users, workspaces "
                "RESTART IDENTITY CASCADE;"
            )
        )
    yield


# ============================================================================
# Section 1: Migration and Schema Verification
# ============================================================================

@pytest.mark.asyncio
async def test_live_postgres_all_12_tables_exist(pg_session: AsyncSession) -> None:
    """Verify all 12 core tables exist in the public schema of live PostgreSQL."""
    expected_tables = {
        "workspaces",
        "users",
        "agents",
        "evidence",
        "claims",
        "claim_evidence",
        "claim_relations",
        "audit_events",
        "environment_snapshots",
        "claim_condition_sets",
        "claim_conditions",
        "claim_verifications",
        "alembic_version",
    }
    result = await pg_session.execute(
        text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public';")
    )
    actual_tables = {row[0] for row in result.fetchall()}
    for table in expected_tables:
        assert table in actual_tables, f"Expected table '{table}' not found in live PostgreSQL"


@pytest.mark.asyncio
async def test_live_postgres_workspace_isolation_composite_fks(pg_session: AsyncSession) -> None:
    """Verify composite foreign keys strictly enforce workspace tenant isolation."""
    # Create two isolated workspaces
    ws1_id = uuid.uuid4()
    ws2_id = uuid.uuid4()
    pg_session.add_all([
        Workspace(id=ws1_id, name="Workspace Alpha", slug=f"ws-alpha-{ws1_id.hex[:6]}"),
        Workspace(id=ws2_id, name="Workspace Beta", slug=f"ws-beta-{ws2_id.hex[:6]}"),
    ])
    await pg_session.flush()

    # Create agent in Workspace 1
    agent_id = uuid.uuid4()
    agent = Agent(
        id=agent_id,
        workspace_id=ws1_id,
        name="Agent 1",
        api_key_hash=hash_api_key("key-1"),
        default_scope="team",
    )
    pg_session.add(agent)
    await pg_session.flush()

    # Attempt to insert an evidence record belonging to Workspace 2 but referencing Agent in Workspace 1
    # This must be rejected by composite foreign key fk_evidence_agent (workspace_id, collected_by_agent)
    invalid_evidence = Evidence(
        id=uuid.uuid4(),
        workspace_id=ws2_id,  # Workspace 2!
        source_type="file",
        source_uri="src/model.py",
        content_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        raw_snippet="# evidence snippet",
        collected_by_agent=agent_id,  # From Workspace 1!
        metadata={},
    )
    pg_session.add(invalid_evidence)

    with pytest.raises(IntegrityError) as exc_info:
        await pg_session.flush()

    assert "fk_evidence_agent" in str(exc_info.value).lower() or "foreign key" in str(exc_info.value).lower()
    await pg_session.rollback()


@pytest.mark.asyncio
async def test_live_postgres_unique_and_check_constraints(pg_session: AsyncSession) -> None:
    """Verify unique constraints and PostgreSQL check constraints."""
    ws_id = uuid.uuid4()
    pg_session.add(Workspace(id=ws_id, name="Constraint Workspace", slug=f"ws-constr-{ws_id.hex[:6]}"))
    await pg_session.flush()

    # 1. Unique agent name per workspace
    agent1 = Agent(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        name="UniqueAgent",
        api_key_hash=hash_api_key("key-unique-1"),
    )
    agent2 = Agent(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        name="UniqueAgent",  # Duplicate name in same workspace
        api_key_hash=hash_api_key("key-unique-2"),
    )
    pg_session.add(agent1)
    await pg_session.flush()

    pg_session.add(agent2)
    with pytest.raises(IntegrityError) as exc_info:
        await pg_session.flush()
    assert "uq_agents_workspace_name" in str(exc_info.value).lower()
    await pg_session.rollback()

    # Re-insert valid workspace and agent
    pg_session.add(Workspace(id=ws_id, name="Constraint Workspace", slug=f"ws-constr-{ws_id.hex[:6]}"))
    await pg_session.flush()
    agent = Agent(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        name="ValidAgent",
        api_key_hash=hash_api_key("key-valid"),
    )
    pg_session.add(agent)
    await pg_session.flush()

    # 2. Check constraint: invalid claim type
    invalid_claim = Claim(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        agent_id=agent.id,
        claim_type="INVALID_CLAIM_TYPE",  # Invalid!
        subject="test.subject",
        predicate="test.predicate",
        object_value={"val": 1},
        raw_statement="Invalid claim statement",
        scope="team",
        status="current",
    )
    pg_session.add(invalid_claim)
    with pytest.raises(IntegrityError) as exc_info:
        await pg_session.flush()
    assert "ck_claims_claim_type" in str(exc_info.value).lower()
    await pg_session.rollback()


@pytest.mark.asyncio
async def test_live_postgres_circular_claim_condition_set_fk(pg_session: AsyncSession) -> None:
    """Verify circular foreign key from claims to claim_condition_sets.

    Allows claim creation with active_condition_version=None,
    allows condition set creation,
    allows updating claim.active_condition_version,
    and rejects updating to a non-existent condition set version.
    """
    ws_id = uuid.uuid4()
    agent_id = uuid.uuid4()
    pg_session.add_all([
        Workspace(id=ws_id, name="Circular WS", slug=f"ws-circ-{ws_id.hex[:6]}"),
        Agent(id=agent_id, workspace_id=ws_id, name="Circ Agent", api_key_hash=hash_api_key("k")),
    ])
    await pg_session.flush()

    claim_id = uuid.uuid4()
    claim = Claim(
        id=claim_id,
        workspace_id=ws_id,
        agent_id=agent_id,
        claim_type="fact",
        subject="sys.db",
        predicate="uses",
        object_value={"engine": "postgres"},
        raw_statement="Uses Postgres",
        scope="team",
        status="current",
        active_condition_version=None,  # Initially None
    )
    pg_session.add(claim)
    await pg_session.flush()

    # Attempt to point to non-existent condition set version 1 -> rejected by composite FK
    claim.active_condition_version = 1
    with pytest.raises(IntegrityError) as exc_info:
        await pg_session.flush()
    assert "fk_claims_active_condition_set" in str(exc_info.value).lower() or "foreign key" in str(exc_info.value).lower()
    await pg_session.rollback()

    # Re-insert claim cleanly
    pg_session.add_all([
        Workspace(id=ws_id, name="Circular WS", slug=f"ws-circ-{ws_id.hex[:6]}"),
        Agent(id=agent_id, workspace_id=ws_id, name="Circ Agent", api_key_hash=hash_api_key("k")),
    ])
    await pg_session.flush()
    claim = Claim(
        id=claim_id,
        workspace_id=ws_id,
        agent_id=agent_id,
        claim_type="fact",
        subject="sys.db",
        predicate="uses",
        object_value={"engine": "postgres"},
        raw_statement="Uses Postgres",
        scope="team",
        status="current",
        active_condition_version=None,
    )
    pg_session.add(claim)
    await pg_session.flush()

    # Create snapshot and condition set v1
    snap_id = uuid.uuid4()
    pg_session.add(
        EnvironmentSnapshot(
            id=snap_id,
            workspace_id=ws_id,
            collected_by_agent=agent_id,
            source_ref="git:commit:1",
            scan_scope="full_repository",
            snapshot_data={"files": {}, "package_inventories": {}, "runtime_facts": {}},
        )
    )
    await pg_session.flush()

    cset_id = uuid.uuid4()
    pg_session.add(
        ClaimConditionSet(
            id=cset_id,
            workspace_id=ws_id,
            claim_id=claim_id,
            version=1,
            based_on_snapshot_id=snap_id,
            established_by_agent=agent_id,
            rationale="Initial baseline conditions",
        )
    )
    await pg_session.flush()

    # Now update claim.active_condition_version = 1 -> succeeds!
    claim.active_condition_version = 1
    await pg_session.flush()
    await pg_session.commit()

    # Verify persisted in database
    res = await pg_session.execute(select(Claim.active_condition_version).where(Claim.id == claim_id))
    assert res.scalar_one() == 1


# ============================================================================
# Section 2: PostgreSQL Immutability Triggers
# ============================================================================

@pytest.mark.asyncio
async def test_live_postgres_audit_events_immutability_trigger(pg_session: AsyncSession) -> None:
    """Verify trg_protect_audit_events rejects direct UPDATE and DELETE operations."""
    ws_id = uuid.uuid4()
    agent_id = uuid.uuid4()
    event_id = uuid.uuid4()

    pg_session.add_all([
        Workspace(id=ws_id, name="Audit WS", slug=f"ws-audit-{ws_id.hex[:6]}"),
        Agent(id=agent_id, workspace_id=ws_id, name="Audit Agent", api_key_hash=hash_api_key("k")),
    ])
    await pg_session.flush()

    event = AuditEvent(
        id=event_id,
        workspace_id=ws_id,
        actor_type="agent",
        actor_id=agent_id,
        event_type="CLAIM_CREATED",
        target_type="claim",
        target_id=uuid.uuid4(),
        payload={"msg": "initial"},
    )
    pg_session.add(event)
    await pg_session.commit()

    # 1. Attempt UPDATE on audit_events
    with pytest.raises(DBAPIError) as exc_info:
        await pg_session.execute(
            text(f"UPDATE audit_events SET event_type = 'MODIFIED' WHERE id = '{event_id}';")
        )
    assert "append-only" in str(exc_info.value).lower()
    await pg_session.rollback()

    # 2. Attempt DELETE on audit_events
    with pytest.raises(DBAPIError) as exc_info:
        await pg_session.execute(
            text(f"DELETE FROM audit_events WHERE id = '{event_id}';")
        )
    assert "append-only" in str(exc_info.value).lower()
    await pg_session.rollback()


@pytest.mark.asyncio
async def test_live_postgres_condition_history_immutability_triggers(pg_session: AsyncSession) -> None:
    """Verify trg_protect_condition_history rejects UPDATE and DELETE on condition governance tables."""
    ws_id = uuid.uuid4()
    agent_id = uuid.uuid4()
    claim_id = uuid.uuid4()
    snap_id = uuid.uuid4()
    cset_id = uuid.uuid4()
    cond_id = uuid.uuid4()
    verif_id = uuid.uuid4()

    pg_session.add_all([
        Workspace(id=ws_id, name="Immut WS", slug=f"ws-immut-{ws_id.hex[:6]}"),
        Agent(id=agent_id, workspace_id=ws_id, name="Immut Agent", api_key_hash=hash_api_key("k")),
        Claim(
            id=claim_id,
            workspace_id=ws_id,
            agent_id=agent_id,
            claim_type="fact",
            subject="sys",
            predicate="state",
            object_value={"v": 1},
            raw_statement="Raw",
            scope="team",
            status="current",
        ),
        EnvironmentSnapshot(
            id=snap_id,
            workspace_id=ws_id,
            collected_by_agent=agent_id,
            source_ref="git:commit:1",
            scan_scope="full_repository",
            snapshot_data={"files": {}, "package_inventories": {}, "runtime_facts": {}},
        ),
        ClaimConditionSet(
            id=cset_id,
            workspace_id=ws_id,
            claim_id=claim_id,
            version=1,
            based_on_snapshot_id=snap_id,
            established_by_agent=agent_id,
            rationale="Initial baseline conditions",
        ),
        ClaimCondition(
            id=cond_id,
            workspace_id=ws_id,
            claim_id=claim_id,
            condition_set_version=1,
            condition_type="file_hash",
            target_path="config.json",
            comparator="hash_equals",
            expected_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            expected_value={"hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"},
            is_critical=True,
        ),
        ClaimVerification(
            id=verif_id,
            workspace_id=ws_id,
            claim_id=claim_id,
            condition_set_version=1,
            snapshot_id=snap_id,
            verification_type="initial",
            outcome="applicable",
            evaluation_details={"status": "ok"},
            verified_by_agent=agent_id,
            attestation_notes="Initial baseline verification note",
        ),
    ])
    await pg_session.commit()

    # A. EnvironmentSnapshots UPDATE/DELETE
    with pytest.raises(DBAPIError) as exc_info:
        await pg_session.execute(text(f"UPDATE environment_snapshots SET scan_scope = '{{}}' WHERE id = '{snap_id}';"))
    assert "append-only" in str(exc_info.value).lower()
    await pg_session.rollback()

    with pytest.raises(DBAPIError) as exc_info:
        await pg_session.execute(text(f"DELETE FROM environment_snapshots WHERE id = '{snap_id}';"))
    assert "append-only" in str(exc_info.value).lower()
    await pg_session.rollback()

    # B. ClaimConditionSets UPDATE/DELETE
    with pytest.raises(DBAPIError) as exc_info:
        await pg_session.execute(text(f"UPDATE claim_condition_sets SET version = 2 WHERE id = '{cset_id}';"))
    assert "append-only" in str(exc_info.value).lower()
    await pg_session.rollback()

    with pytest.raises(DBAPIError) as exc_info:
        await pg_session.execute(text(f"DELETE FROM claim_condition_sets WHERE id = '{cset_id}';"))
    assert "append-only" in str(exc_info.value).lower()
    await pg_session.rollback()

    # C. ClaimConditions UPDATE/DELETE
    with pytest.raises(DBAPIError) as exc_info:
        await pg_session.execute(text(f"UPDATE claim_conditions SET is_critical = false WHERE id = '{cond_id}';"))
    assert "append-only" in str(exc_info.value).lower()
    await pg_session.rollback()

    with pytest.raises(DBAPIError) as exc_info:
        await pg_session.execute(text(f"DELETE FROM claim_conditions WHERE id = '{cond_id}';"))
    assert "append-only" in str(exc_info.value).lower()
    await pg_session.rollback()

    # D. ClaimVerifications UPDATE/DELETE
    with pytest.raises(DBAPIError) as exc_info:
        await pg_session.execute(text(f"UPDATE claim_verifications SET outcome = 'drifted' WHERE id = '{verif_id}';"))
    assert "append-only" in str(exc_info.value).lower()
    await pg_session.rollback()

    with pytest.raises(DBAPIError) as exc_info:
        await pg_session.execute(text(f"DELETE FROM claim_verifications WHERE id = '{verif_id}';"))
    assert "append-only" in str(exc_info.value).lower()
    await pg_session.rollback()


# ============================================================================
# Section 3: End-to-End Real HTTP API Persistence & Lifecycle Audit
# ============================================================================

@pytest_asyncio.fixture
async def live_api_client(pg_session_factory: async_sessionmaker[AsyncSession]):
    """Create test HTTP client connected to live PostgreSQL."""
    test_settings = Settings(DATABASE_URL=TEST_DB_URL)
    app = create_app(test_settings)

    async def override_get_db():
        async with pg_session_factory() as session:
            try:
                yield session
            except Exception:
                if session.is_active:
                    await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.mark.asyncio
async def test_live_postgres_e2e_lifecycle_and_reconciliation(
    live_api_client: httpx.AsyncClient,
    pg_session: AsyncSession,
) -> None:
    """End-to-end HTTP API lifecycle verification backed by live PostgreSQL.

    Tests:
    1. Evidence recording + AuditEvent persistence
    2. Claim creation + AuditEvent persistence
    3. Evidence linking + AuditEvent persistence
    4. Snapshot ingestion
    5. Initial condition establishment (condition set v1, verification, active_condition_version=1)
    6. Transient evaluation (strictly read-only: 0 writes to any table, claim version unchanged)
    7. Re-verification with verify_existing (verification persisted, pointer unchanged)
    8. Re-verification with adopt_new_conditions (pointer advanced to 2, condition set v2 persisted)
    9. Rollback on invalid proposed condition (0 partial writes, pointer remains 2)
    10. Reconciled lifecycle semantics (needs_review and disputed never produce applicable outcome)
    """
    # 0. Seed Workspace and Agent in live PostgreSQL
    ws_id = uuid.uuid4()
    agent_id = uuid.uuid4()
    raw_api_key = "live-test-agent-key-12345"
    key_hash = hash_api_key(raw_api_key)

    ws = Workspace(id=ws_id, name="E2E Workspace", slug=f"ws-e2e-{ws_id.hex[:6]}")
    agent = Agent(
        id=agent_id,
        workspace_id=ws_id,
        name="E2E Agent",
        api_key_hash=key_hash,
        default_scope="team",
        is_active=True,
    )
    pg_session.add_all([ws, agent])
    await pg_session.commit()

    headers = {"Authorization": f"Bearer {raw_api_key}"}

    # 1. Evidence ingestion via API
    ev_res = await live_api_client.post(
        "/api/v1/evidence",
        json={
            "source_type": "file",
            "source_uri": "src/app.py",
            "raw_snippet": "print('hello world')",
            "metadata": {"author": "agent"},
        },
        headers=headers,
    )
    assert ev_res.status_code == 201, ev_res.text
    evidence_id = ev_res.json()["id"]

    # Verify evidence and audit event in DB
    ev_row = (await pg_session.execute(select(Evidence).where(Evidence.id == uuid.UUID(evidence_id)))).scalar_one()
    assert ev_row.source_uri == "src/app.py"
    audit_ev = (await pg_session.execute(
        select(AuditEvent).where(AuditEvent.target_id == uuid.UUID(evidence_id), AuditEvent.event_type == "EVIDENCE_RECORDED")
    )).scalar_one()
    assert audit_ev.actor_id == agent_id

    # 2. Claim creation via API
    claim_res = await live_api_client.post(
        "/api/v1/claims",
        json={
            "claim_type": "fact",
            "subject": "service.auth",
            "predicate": "enabled",
            "object_value": {"mfa": True},
            "raw_statement": "MFA is enabled on authentication service.",
            "scope": "team",
            "confidence": 0.95,
        },
        headers=headers,
    )
    assert claim_res.status_code == 201, claim_res.text
    claim_id = claim_res.json()["id"]

    # Verify claim in DB
    claim_row = (await pg_session.execute(select(Claim).where(Claim.id == uuid.UUID(claim_id)))).scalar_one()
    assert claim_row.subject == "service.auth"
    assert claim_row.active_condition_version is None

    # 3. Evidence linking via API
    link_res = await live_api_client.post(
        f"/api/v1/claims/{claim_id}/evidence",
        json={
            "evidence_id": evidence_id,
            "support_type": "supports",
            "confidence_weight": 0.90,
            "extraction_notes": "Code snippet confirms MFA.",
        },
        headers=headers,
    )
    assert link_res.status_code == 201, link_res.text

    # 4. Snapshot ingestion via API
    dummy_hash = "a" * 64
    snap_res = await live_api_client.post(
        "/api/v1/snapshots",
        json={
            "source_ref": "git:main:commit1",
            "source_type": "agent_client",
            "verification_level": "agent_reported",
            "scan_scope": "full_repository",
            "snapshot_data": {
                "scanned_roots": ["."],
                "files": {
                    "config.json": dummy_hash,
                },
                "packages": {
                    "pypi:fastapi": {"version": "0.115.0"},
                },
                "packages_scope": "complete",
                "runtime": {
                    "python": {"version": "3.12.0"},
                },
                "runtime_scope": "complete",
            },
        },
        headers=headers,
    )
    assert snap_res.status_code == 201, snap_res.text
    snapshot_id = snap_res.json()["id"]

    # 5. Initial condition establishment via API
    cond_est_res = await live_api_client.post(
        f"/api/v1/claims/{claim_id}/conditions",
        json={
            "based_on_snapshot_id": snapshot_id,
            "rationale": "Initial baseline conditions",
            "conditions": [
                {
                    "condition_type": "file_hash",
                    "target_path": "config.json",
                    "comparator": "hash_equals",
                    "expected_hash": dummy_hash,
                    "is_critical": True,
                },
                {
                    "condition_type": "package_version",
                    "target_path": "pypi:fastapi",
                    "comparator": "version_equals",
                    "expected_value": {"version": "0.115.0"},
                    "is_critical": True,
                },
            ],
        },
        headers=headers,
    )
    assert cond_est_res.status_code == 201, cond_est_res.text
    assert cond_est_res.json()["version"] == 1

    # Verify claim updated in DB
    await pg_session.refresh(claim_row)
    assert claim_row.active_condition_version == 1
    assert claim_row.version == 2

    # 6. Transient Condition Evaluation (strictly read-only)
    # Record table row counts before evaluation
    counts_before = {}
    for table_name in ["claims", "claim_condition_sets", "claim_conditions", "claim_verifications", "audit_events"]:
        counts_before[table_name] = (await pg_session.execute(text(f"SELECT COUNT(*) FROM {table_name};"))).scalar_one()

    eval_res = await live_api_client.post(
        f"/api/v1/claims/{claim_id}/evaluate",
        json={"snapshot_id": snapshot_id},
        headers=headers,
    )
    assert eval_res.status_code == 200, eval_res.text
    eval_json = eval_res.json()
    assert eval_json["outcome"] == "applicable"
    assert eval_json["is_applicable"] is True

    # Assert 0 writes to any table occurred during transient evaluation
    for table_name, count_before in counts_before.items():
        count_after = (await pg_session.execute(text(f"SELECT COUNT(*) FROM {table_name};"))).scalar_one()
        assert count_after == count_before, f"Table '{table_name}' was modified during transient evaluation!"

    # 7. Re-verification with verify_existing
    reverify_res = await live_api_client.post(
        f"/api/v1/claims/{claim_id}/reverify",
        json={
            "snapshot_id": snapshot_id,
            "action": "verify_existing",
            "expected_condition_version": 1,
            "attestation_notes": "Routine weekly reverification",
        },
        headers=headers,
    )
    assert reverify_res.status_code == 200, reverify_res.text
    reverify_json = reverify_res.json()
    assert reverify_json["outcome"] == "applicable"
    assert reverify_json["is_applicable"] is True
    assert reverify_json["active_condition_version"] == 1
    assert reverify_json["condition_set_version"] == 1

    # Verify verification persisted in DB
    verif_id = uuid.UUID(reverify_json["verification_id"])
    verif_row = (await pg_session.execute(select(ClaimVerification).where(ClaimVerification.id == verif_id))).scalar_one()
    assert verif_row.outcome == "applicable"
    assert verif_row.condition_set_version == 1

    # 8. Re-verification with adopt_new_conditions (advancing to version 2)
    new_hash = "b" * 64
    snap2_res = await live_api_client.post(
        "/api/v1/snapshots",
        json={
            "source_ref": "git:main:commit2",
            "source_type": "agent_client",
            "verification_level": "agent_reported",
            "scan_scope": "full_repository",
            "snapshot_data": {
                "scanned_roots": ["."],
                "files": {
                    "config.json": new_hash,
                },
                "packages": {
                    "pypi:fastapi": {"version": "0.115.1"},
                },
                "packages_scope": "complete",
                "runtime": {
                    "python": {"version": "3.12.0"},
                },
                "runtime_scope": "complete",
            },
        },
        headers=headers,
    )
    assert snap2_res.status_code == 201
    snapshot2_id = snap2_res.json()["id"]

    adopt_res = await live_api_client.post(
        f"/api/v1/claims/{claim_id}/reverify",
        json={
            "snapshot_id": snapshot2_id,
            "action": "adopt_new_conditions",
            "expected_condition_version": 1,
            "adopt_rationale": "Upgraded fastapi dependency and modified config",
            "attestation_notes": "Adopting v2 conditions based on updated snapshot",
            "proposed_conditions": [
                {
                    "condition_type": "file_hash",
                    "target_path": "config.json",
                    "comparator": "hash_equals",
                    "expected_hash": new_hash,
                    "is_critical": True,
                },
                {
                    "condition_type": "package_version",
                    "target_path": "pypi:fastapi",
                    "comparator": "version_equals",
                    "expected_value": {"version": "0.115.1"},
                    "is_critical": True,
                },
            ],
        },
        headers=headers,
    )
    assert adopt_res.status_code == 200, adopt_res.text
    adopt_json = adopt_res.json()
    assert adopt_json["active_condition_version"] == 2
    assert adopt_json["condition_set_version"] == 2
    assert adopt_json["outcome"] == "applicable"
    assert adopt_json["is_applicable"] is True

    # Verify claim in DB has pointer 2 and incremented version
    await pg_session.refresh(claim_row)
    assert claim_row.active_condition_version == 2
    assert claim_row.version == 3

    # 9. Failed Adoption Rollback (verify 0 partial writes)
    csets_before = (await pg_session.execute(select(ClaimConditionSet).where(ClaimConditionSet.claim_id == claim_row.id))).scalars().all()
    conds_before = (await pg_session.execute(select(ClaimCondition).where(ClaimCondition.claim_id == claim_row.id))).scalars().all()

    fail_res = await live_api_client.post(
        f"/api/v1/claims/{claim_id}/reverify",
        json={
            "snapshot_id": snapshot2_id,
            "action": "adopt_new_conditions",
            "expected_condition_version": 2,
            "adopt_rationale": "Attempting invalid adoption",
            "attestation_notes": "Attempting invalid adoption notes",
            "proposed_conditions": [
                {
                    "condition_type": "package_version",
                    "target_path": "pypi:nonexistent",
                    "comparator": "version_equals",
                    "expected_value": {"version": "9.9.9"},
                    "is_critical": True,
                }
            ],
        },
        headers=headers,
    )
    assert fail_res.status_code == 422, fail_res.text

    # Verify DB state: no new condition sets or conditions were added
    csets_after = (await pg_session.execute(select(ClaimConditionSet).where(ClaimConditionSet.claim_id == claim_row.id))).scalars().all()
    conds_after = (await pg_session.execute(select(ClaimCondition).where(ClaimCondition.claim_id == claim_row.id))).scalars().all()
    assert len(csets_after) == len(csets_before)
    assert len(conds_after) == len(conds_before)
    await pg_session.refresh(claim_row)
    assert claim_row.active_condition_version == 2

    # 10. Reconciled Lifecycle Semantics Audit
    # Mutate claim status to "disputed" directly in PostgreSQL
    await pg_session.execute(text(f"UPDATE claims SET status = 'disputed' WHERE id = '{claim_id}';"))
    await pg_session.commit()

    disputed_reverify = await live_api_client.post(
        f"/api/v1/claims/{claim_id}/reverify",
        json={
            "snapshot_id": snapshot2_id,
            "action": "verify_existing",
            "expected_condition_version": 2,
            "attestation_notes": "Reverifying disputed claim",
        },
        headers=headers,
    )
    assert disputed_reverify.status_code == 200
    disputed_json = disputed_reverify.json()
    # Outcome MUST be indeterminate and is_applicable MUST be False
    assert disputed_json["outcome"] == "indeterminate"
    assert disputed_json["is_applicable"] is False

    # Check verification details in PostgreSQL
    disputed_verif = (await pg_session.execute(
        select(ClaimVerification).where(ClaimVerification.id == uuid.UUID(disputed_json["verification_id"]))
    )).scalar_one()
    assert disputed_verif.outcome == "indeterminate"
    assert disputed_verif.evaluation_details["conditions_match"] is True
    assert disputed_verif.evaluation_details["lifecycle_status"] == "disputed"


# ============================================================================
# Section 4: Real PostgreSQL Row-Level Concurrency & Lock Blocking
# ============================================================================

@pytest.mark.asyncio
async def test_live_postgres_row_level_concurrency_and_stale_detection(
    pg_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Validate true PostgreSQL row-level locking via SELECT ... FOR UPDATE across two connections.

    Simulates two concurrent agent requests attempting to adopt conditions on the same claim:
    1. Connection 1 starts transaction, locks claim with SELECT ... FOR UPDATE.
    2. Connection 2 attempts SELECT ... FOR UPDATE in a concurrent task and is physically blocked
       at the PostgreSQL engine level.
    3. Connection 1 creates condition set v2, verification, updates active_condition_version=2, commits.
    4. Connection 2 unblocks immediately upon Connection 1's commit.
    5. Connection 2 inspects claim.active_condition_version, observes it is now 2 (not expected 1),
       detects stale version mismatch, and aborts cleanly.
    6. Confirms PostgreSQL state: exactly one condition set v2, exactly one verification, pointer = 2.
    """
    ws_id = uuid.uuid4()
    agent_id = uuid.uuid4()
    claim_id = uuid.uuid4()
    snap_id = uuid.uuid4()
    cset1_id = uuid.uuid4()

    dummy_hash = "c" * 64

    # Seed baseline in PostgreSQL
    async with pg_session_factory() as setup_session:
        setup_session.add_all([
            Workspace(id=ws_id, name="Concurrency WS", slug=f"ws-conc-{ws_id.hex[:6]}"),
            Agent(id=agent_id, workspace_id=ws_id, name="Conc Agent", api_key_hash=hash_api_key("k")),
            Claim(
                id=claim_id,
                workspace_id=ws_id,
                agent_id=agent_id,
                claim_type="fact",
                subject="service.concurrency",
                predicate="lock_tested",
                object_value={"test": True},
                raw_statement="Testing row locks",
                scope="team",
                status="current",
                active_condition_version=None,
            ),
            EnvironmentSnapshot(
                id=snap_id,
                workspace_id=ws_id,
                collected_by_agent=agent_id,
                source_ref="git:commit:1",
                scan_scope="full_repository",
                snapshot_data={
                    "files": {"app.py": {"hash": dummy_hash, "size_bytes": 100, "status": "scanned"}},
                    "package_inventories": {},
                    "runtime_facts": {},
                },
            ),
        ])
        await setup_session.flush()

        setup_session.add(
            ClaimConditionSet(
                id=cset1_id,
                workspace_id=ws_id,
                claim_id=claim_id,
                version=1,
                based_on_snapshot_id=snap_id,
                established_by_agent=agent_id,
                rationale="Concurrency baseline v1",
            )
        )
        await setup_session.flush()

        claim = (await setup_session.execute(select(Claim).where(Claim.id == claim_id))).scalar_one()
        claim.active_condition_version = 1
        await setup_session.commit()

    # Now simulate two independent database sessions/connections
    session1: AsyncSession = pg_session_factory()
    session2: AsyncSession = pg_session_factory()

    conn2_started = asyncio.Event()
    conn2_acquired_lock = asyncio.Event()
    conn2_error: list[Exception] = []

    async def worker_conn2():
        """Connection 2 worker attempting concurrent adoption."""
        try:
            async with session2:
                # Signal ready to attempt lock
                conn2_started.set()

                # Attempt to acquire row lock on claim
                # This call will physically block until session1 commits!
                claim_stmt = select(Claim).where(Claim.id == claim_id).with_for_update()
                res = await session2.execute(claim_stmt)
                locked_claim = res.scalar_one()

                # Lock acquired!
                conn2_acquired_lock.set()

                context = TrustedContext(
                    actor_id=agent_id,
                    actor_type="agent",
                    workspace_id=ws_id,
                )
                params = ReverifyClaimParams(
                    snapshot_id=snap_id,
                    action="adopt_new_conditions",
                    expected_condition_version=1,  # Stale! Expecting 1, but session1 advanced to 2
                    adopt_rationale="Worker 2 adoption rationale",
                    attestation_notes="Worker 2 attestation notes",
                    proposed_conditions=[
                        ConditionSpec(
                            condition_type="file_hash",
                            target_path="app.py",
                            comparator="hash_equals",
                            expected_hash=dummy_hash,
                            is_critical=True,
                        )
                    ],
                )

                # Check expected condition version against locked claim
                if locked_claim.active_condition_version != params.expected_condition_version:
                    raise StaleConditionVersionError(
                        claim_id=claim_id,
                        expected_version=params.expected_condition_version,
                        actual_version=locked_claim.active_condition_version,
                    )
        except Exception as e:
            conn2_error.append(e)

    # 1. Connection 1 acquires row lock
    async with session1:
        claim_stmt = select(Claim).where(Claim.id == claim_id).with_for_update()
        res1 = await session1.execute(claim_stmt)
        locked_claim_1 = res1.scalar_one()
        assert locked_claim_1.active_condition_version == 1

        # 2. Launch Connection 2 worker in background task
        task2 = asyncio.create_task(worker_conn2())
        await conn2_started.wait()

        # Give Connection 2 time to reach the SELECT ... FOR UPDATE statement
        await asyncio.sleep(0.1)

        # Connection 2 must NOT have acquired the lock because Connection 1 holds it!
        assert not conn2_acquired_lock.is_set(), "Connection 2 acquired lock while Connection 1 held it!"

        # 3. Connection 1 performs adoption to version 2
        now = datetime.now(timezone.utc)
        cset2 = ClaimConditionSet(
            id=uuid.uuid4(),
            workspace_id=ws_id,
            claim_id=claim_id,
            version=2,
            based_on_snapshot_id=snap_id,
            established_by_agent=agent_id,
            rationale="Adopt v2 in concurrency test",
            created_at=now,
        )
        session1.add(cset2)
        cond2 = ClaimCondition(
            id=uuid.uuid4(),
            workspace_id=ws_id,
            claim_id=claim_id,
            condition_set_version=2,
            condition_type="file_hash",
            target_path="app.py",
            comparator="hash_equals",
            expected_hash=dummy_hash,
            expected_value={"hash": dummy_hash},
            is_critical=True,
            created_at=now,
        )
        session1.add(cond2)
        verif2 = ClaimVerification(
            id=uuid.uuid4(),
            workspace_id=ws_id,
            claim_id=claim_id,
            condition_set_version=2,
            snapshot_id=snap_id,
            verification_type="reverification",
            outcome="applicable",
            evaluation_details={"status": "adopted"},
            verified_by_agent=agent_id,
            attestation_notes="Adopted v2 in concurrency test",
            created_at=now,
        )
        session1.add(verif2)
        await session1.flush()

        locked_claim_1.active_condition_version = 2
        locked_claim_1.version += 1
        locked_claim_1.updated_at = now

        # Commit Connection 1 transaction -> releases row lock!
        await session1.commit()

    # 4. Wait for Connection 2 worker to complete
    await task2

    # Verify Connection 2 unblocked and detected the stale version mismatch
    assert conn2_acquired_lock.is_set(), "Connection 2 failed to acquire lock after Connection 1 committed"
    assert len(conn2_error) == 1, f"Expected 1 error, got: {conn2_error}"
    assert isinstance(conn2_error[0], StaleConditionVersionError)
    assert "expected active version 1, but current active version is 2" in str(conn2_error[0])

    # 5. Verify final PostgreSQL state
    async with pg_session_factory() as check_session:
        final_claim = (await check_session.execute(select(Claim).where(Claim.id == claim_id))).scalar_one()
        assert final_claim.active_condition_version == 2
        assert final_claim.version == 2

        csets = (await check_session.execute(
            select(ClaimConditionSet).where(ClaimConditionSet.claim_id == claim_id)
        )).scalars().all()
        assert len(csets) == 2  # v1 and v2
        assert {c.version for c in csets} == {1, 2}

        verifs = (await check_session.execute(
            select(ClaimVerification).where(ClaimVerification.claim_id == claim_id)
        )).scalars().all()
        assert len(verifs) == 1  # exactly 1 verification from Connection 1
