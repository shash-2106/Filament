"""Step 28: Local Restricted-Role Verification and Supabase RLS Integration Tests.

Validates the full security architecture against a live PostgreSQL 16 instance:
1. Dedicated runtime role `filament_app` with NOBYPASSRLS and least-privilege grants.
2. Authentication bootstrap via SECURITY DEFINER function `public.filament_lookup_agent`.
3. Row-Level Security (RLS) policies across all 12 tables enforcing workspace isolation.
4. Fail-closed behavior on missing or malformed workspace context.
5. Prevention of cross-workspace reads and writes.
6. Immutability triggers and Zero-DELETE enforcement.
7. Column-level UPDATE permission boundaries (immutable business facts protected).
8. Absence of DDL and administrative privileges for the runtime role.
9. Threat boundary verification: custom session variable boundary limitations.
"""

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
import uuid
import pytest
import pytest_asyncio
import httpx
from sqlalchemy import delete, insert, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError, ProgrammingError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

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

ADMIN_DB_URL = "postgresql+asyncpg://postgres@127.0.0.1:5433/filament_test"
RUNTIME_USER = "filament_app"
RUNTIME_PASSWORD = "test_filament_runtime_password_123"
RUNTIME_DB_URL = f"postgresql+asyncpg://{RUNTIME_USER}:{RUNTIME_PASSWORD}@127.0.0.1:5433/filament_test"


@pytest_asyncio.fixture(autouse=True)
async def setup_test_runtime_role():
    """Idempotently configure the local test runtime role and grants."""
    admin_engine = create_async_engine(ADMIN_DB_URL, poolclass=NullPool)
    async with admin_engine.connect() as conn:
        # 1. Create runtime role with NOBYPASSRLS if not exists
        await conn.execute(
            text(
                f"""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{RUNTIME_USER}') THEN
                    CREATE ROLE {RUNTIME_USER} WITH LOGIN NOBYPASSRLS PASSWORD '{RUNTIME_PASSWORD}';
                ELSE
                    ALTER ROLE {RUNTIME_USER} WITH LOGIN NOBYPASSRLS PASSWORD '{RUNTIME_PASSWORD}';
                END IF;
            END
            $$;
        """
            )
        )
        await conn.commit()

        # 2. Grant schema usage and revoke creation
        await conn.execute(text(f"GRANT USAGE ON SCHEMA public TO {RUNTIME_USER};"))
        await conn.execute(text(f"REVOKE CREATE ON SCHEMA public FROM {RUNTIME_USER};"))

        # 3. Grant SELECT, INSERT on all 12 tables
        tables = [
            "workspaces", "users", "agents", "claims", "evidence", "claim_evidence",
            "claim_relations", "audit_events", "environment_snapshots",
            "claim_condition_sets", "claim_conditions", "claim_verifications"
        ]
        for t in tables:
            await conn.execute(text(f"GRANT SELECT, INSERT ON TABLE public.{t} TO {RUNTIME_USER};"))

        # 4. Column-level UPDATE grants
        await conn.execute(
            text(f"GRANT UPDATE (email, role, updated_at) ON TABLE public.users TO {RUNTIME_USER};")
        )
        await conn.execute(
            text(f"GRANT UPDATE (name, default_scope, is_active, updated_at) ON TABLE public.agents TO {RUNTIME_USER};")
        )
        await conn.execute(
            text(f"GRANT UPDATE (status, version, updated_at, active_condition_version) ON TABLE public.claims TO {RUNTIME_USER};")
        )

        # 5. Revoke DELETE everywhere
        await conn.execute(text(f"REVOKE DELETE ON ALL TABLES IN SCHEMA public FROM {RUNTIME_USER};"))

        # 6. Grant EXECUTE on lookup function
        await conn.execute(
            text(f"GRANT EXECUTE ON FUNCTION public.filament_lookup_agent(text) TO {RUNTIME_USER};")
        )
        await conn.commit()

    await admin_engine.dispose()
    yield


@pytest_asyncio.fixture
async def admin_session() -> AsyncSession:
    """Session running as superuser (postgres) for test setup and verification."""
    engine = create_async_engine(ADMIN_DB_URL, poolclass=NullPool)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def runtime_session() -> AsyncSession:
    """Session running strictly as the restricted runtime role (filament_app)."""
    engine = create_async_engine(RUNTIME_DB_URL, poolclass=NullPool)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture(autouse=True)
async def clean_database():
    """Truncate tables before each test using admin connection."""
    admin_engine = create_async_engine(ADMIN_DB_URL, poolclass=NullPool)
    async with admin_engine.begin() as conn:
        await conn.execute(
            text(
                "TRUNCATE TABLE "
                "claim_verifications, claim_conditions, claim_condition_sets, environment_snapshots, "
                "claim_relations, claim_evidence, claims, evidence, audit_events, agents, users, workspaces "
                "RESTART IDENTITY CASCADE;"
            )
        )
    await admin_engine.dispose()
    yield


# ==============================================================================
# 1. Role Attributes & Authentication Bootstrap Verification
# ==============================================================================

@pytest.mark.asyncio
async def test_runtime_role_has_nobypassrls_and_cannot_create_tables(runtime_session: AsyncSession):
    """Verify filament_app has NOBYPASSRLS and is blocked from DDL operations."""
    # Check NOBYPASSRLS
    res = await runtime_session.execute(
        text("SELECT rolbypassrls, rolsuper FROM pg_roles WHERE rolname = CURRENT_USER;")
    )
    row = res.first()
    assert row is not None
    assert row[0] is False, "Runtime role must have NOBYPASSRLS"
    assert row[1] is False, "Runtime role must not be superuser"

    # Verify DDL is denied
    with pytest.raises(ProgrammingError) as exc_info:
        await runtime_session.execute(text("CREATE TABLE public.unauthorized_test (id int);"))
    assert "permission denied" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_filament_lookup_agent_execution_and_security(admin_session: AsyncSession, runtime_session: AsyncSession):
    """Verify public.filament_lookup_agent functionality under runtime role."""
    ws_id = uuid.uuid4()
    agent_id = uuid.uuid4()
    raw_key = "fil_live_lookup_key_valid_123"
    key_hash = hash_api_key(raw_key)

    ws = Workspace(id=ws_id, name="Lookup WS", slug="lookup-ws")
    active_agent = Agent(
        id=agent_id,
        workspace_id=ws_id,
        name="Lookup Worker",
        api_key_hash=key_hash,
        default_scope="private",
        is_active=True,
    )
    inactive_agent = Agent(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        name="Inactive Worker",
        api_key_hash=hash_api_key("fil_live_inactive_key_456"),
        default_scope="private",
        is_active=False,
    )
    admin_session.add_all([ws, active_agent, inactive_agent])
    await admin_session.commit()

    # 1. Valid key lookup returns correct metadata without hash
    res = await runtime_session.execute(
        text("SELECT id, workspace_id, name, default_scope, is_active FROM public.filament_lookup_agent(:h)"),
        {"h": key_hash},
    )
    row = res.first()
    assert row is not None
    assert row[0] == agent_id
    assert row[1] == ws_id
    assert row[2] == "Lookup Worker"
    assert row[3] == "private"
    assert row[4] is True

    # 2. Inactive agent returns 0 rows (indistinguishable from invalid key)
    res_inactive = await runtime_session.execute(
        text("SELECT id FROM public.filament_lookup_agent(:h)"),
        {"h": hash_api_key("fil_live_inactive_key_456")},
    )
    assert res_inactive.first() is None

    # 3. Invalid key hash returns 0 rows
    res_unknown = await runtime_session.execute(
        text("SELECT id FROM public.filament_lookup_agent(:h)"),
        {"h": "a" * 64},
    )
    assert res_unknown.first() is None

    # 4. Malformed hash (not 64 hex chars) returns 0 rows immediately
    res_malformed = await runtime_session.execute(
        text("SELECT id FROM public.filament_lookup_agent(:h)"),
        {"h": "short_hash_or_sql_injection' OR '1'='1"},
    )
    assert res_malformed.first() is None


# ==============================================================================
# 2. Row-Level Security (RLS) Workspace Isolation Verification
# ==============================================================================

@pytest.mark.asyncio
async def test_rls_workspace_isolation_and_cross_workspace_blocking(
    admin_session: AsyncSession,
    runtime_session: AsyncSession,
):
    """Verify Workspace A cannot read or write records belonging to Workspace B."""
    ws_a = uuid.uuid4()
    ws_b = uuid.uuid4()
    agent_a = uuid.uuid4()
    agent_b = uuid.uuid4()

    # Seed data across two workspaces via admin session
    admin_session.add_all([
        Workspace(id=ws_a, name="Workspace A", slug="ws-a"),
        Workspace(id=ws_b, name="Workspace B", slug="ws-b"),
        Agent(id=agent_a, workspace_id=ws_a, name="Agent A", api_key_hash=hash_api_key("key_a"), is_active=True),
        Agent(id=agent_b, workspace_id=ws_b, name="Agent B", api_key_hash=hash_api_key("key_b"), is_active=True),
        Claim(id=uuid.uuid4(), workspace_id=ws_a, agent_id=agent_a, claim_type="fact", subject="Claim A", predicate="is", object_value={"val": 1}, raw_statement="Claim A is 1"),
        Claim(id=uuid.uuid4(), workspace_id=ws_b, agent_id=agent_b, claim_type="fact", subject="Claim B", predicate="is", object_value={"val": 2}, raw_statement="Claim B is 2"),
    ])
    await admin_session.commit()

    # 1. Unset workspace context -> FAILS CLOSED (0 claims returned)
    res_empty = await runtime_session.execute(text("SELECT id, subject FROM public.claims;"))
    assert len(res_empty.fetchall()) == 0

    # 2. Set context to Workspace A
    await runtime_session.execute(
        text("SELECT set_config('app.current_workspace_id', :ws, true);"),
        {"ws": str(ws_a)},
    )
    res_a = await runtime_session.execute(text("SELECT id, subject FROM public.claims;"))
    claims_a = res_a.fetchall()
    assert len(claims_a) == 1
    assert claims_a[0][1] == "Claim A"

    # 3. Attempt to insert a claim into Workspace B while scoped to Workspace A -> BLOCKED BY RLS WITH CHECK
    with pytest.raises(DBAPIError) as exc_info:
        await runtime_session.execute(
            text(
                "INSERT INTO public.claims (id, workspace_id, agent_id, subject, predicate, object_value, scope, status, confidence, version) "
                "VALUES (:id, :ws, :agent, 'Cross-WS Claim', 'is', '{\"val\": 9}', 'private', 'current', 1.0, 1);"
            ),
            {"id": str(uuid.uuid4()), "ws": str(ws_b), "agent": str(agent_a)},
        )
    assert "new row violates row-level security policy for table \"claims\"" in str(exc_info.value).lower()
    await runtime_session.rollback()

    # 4. Verify context does not leak after rollback
    res_after_rollback = await runtime_session.execute(text("SELECT id FROM public.claims;"))
    assert len(res_after_rollback.fetchall()) == 0, "After rollback, transaction context must be cleared"


@pytest.mark.asyncio
async def test_rls_all_12_tables_fail_closed_without_context(
    admin_session: AsyncSession,
    runtime_session: AsyncSession,
):
    """Verify that every single one of the 12 tables fails closed when workspace context is missing."""
    ws_id = uuid.uuid4()
    agent_id = uuid.uuid4()
    claim_id = uuid.uuid4()
    claim2_id = uuid.uuid4()
    ev_id = uuid.uuid4()
    snap_id = uuid.uuid4()

    # Seed 1 record in every table via admin session
    admin_session.add_all([
        Workspace(id=ws_id, name="Test WS", slug="test-ws"),
        User(id=uuid.uuid4(), workspace_id=ws_id, email="u@test.com", display_name="Test User", role="member"),
        Agent(id=agent_id, workspace_id=ws_id, name="A1", api_key_hash="0" * 64, is_active=True),
        Evidence(
            id=ev_id,
            workspace_id=ws_id,
            collected_by_agent=agent_id,
            source_type="file",
            source_uri="file:///test.py",
            raw_snippet="print('x')",
            content_hash="h1",
            metadata_={"key": "val"},
        ),
        Claim(id=claim_id, workspace_id=ws_id, agent_id=agent_id, claim_type="fact", subject="s", predicate="p", object_value={"o": 1}, raw_statement="raw statement"),
        Claim(id=claim2_id, workspace_id=ws_id, agent_id=agent_id, claim_type="fact", subject="s2", predicate="p2", object_value={"o": 2}, raw_statement="raw statement 2"),
        ClaimEvidence(claim_id=claim_id, evidence_id=ev_id, workspace_id=ws_id, support_type="supports"),
        ClaimRelation(id=uuid.uuid4(), workspace_id=ws_id, source_claim_id=claim_id, target_claim_id=claim2_id, relation_type="depends_on", rationale="Test link rationale"),
        AuditEvent(
            id=uuid.uuid4(),
            workspace_id=ws_id,
            actor_type="agent",
            actor_id=agent_id,
            event_type="claim_created",
            target_type="claim",
            target_id=claim_id,
            payload={"action": "test"},
        ),
        EnvironmentSnapshot(
            id=snap_id,
            workspace_id=ws_id,
            collected_by_agent=agent_id,
            source_type="agent_client",
            verification_level="agent_reported",
            source_ref="git:main",
            scan_scope="full_repository",
            snapshot_data={},
        ),
        ClaimConditionSet(
            id=uuid.uuid4(),
            workspace_id=ws_id,
            claim_id=claim_id,
            version=1,
            based_on_snapshot_id=snap_id,
            established_by_agent=agent_id,
            rationale="Initial baseline",
        ),
        ClaimCondition(
            id=uuid.uuid4(),
            workspace_id=ws_id,
            claim_id=claim_id,
            condition_set_version=1,
            condition_type="file_hash",
            target_path="config.json",
            comparator="hash_equals",
            expected_hash="a" * 64,
            is_critical=True,
        ),
        ClaimVerification(
            id=uuid.uuid4(),
            workspace_id=ws_id,
            claim_id=claim_id,
            snapshot_id=snap_id,
            condition_set_version=1,
            verification_type="initial",
            outcome="applicable",
            verified_by_agent=agent_id,
            attestation_notes="Initial test verification",
            evaluation_details={},
        ),
    ])
    await admin_session.commit()

    # Without setting app.current_workspace_id, all tables must return 0 rows
    tables = [
        "workspaces", "users", "agents", "claims", "evidence", "claim_evidence",
        "claim_relations", "audit_events", "environment_snapshots",
        "claim_condition_sets", "claim_conditions", "claim_verifications"
    ]
    for table in tables:
        res = await runtime_session.execute(text(f"SELECT * FROM public.{table};"))
        rows = res.fetchall()
        assert len(rows) == 0, f"Table {table} must return 0 rows when workspace context is unset"


# ==============================================================================
# 3. Immutability Triggers, Grants, & Column-Level UPDATE Verification
# ==============================================================================

@pytest.mark.asyncio
async def test_zero_delete_and_column_level_updates(
    admin_session: AsyncSession,
    runtime_session: AsyncSession,
):
    """Verify zero-DELETE enforcement and column-level UPDATE permissions under runtime role."""
    ws_id = uuid.uuid4()
    agent_id = uuid.uuid4()
    claim_id = uuid.uuid4()

    admin_session.add_all([
        Workspace(id=ws_id, name="Test WS", slug="test-ws"),
        Agent(id=agent_id, workspace_id=ws_id, name="Test Agent", api_key_hash=hash_api_key("tok"), is_active=True),
        Claim(id=claim_id, workspace_id=ws_id, agent_id=agent_id, claim_type="fact", subject="Original Subject", predicate="is", object_value={"v": 1}, raw_statement="original statement"),
    ])
    await admin_session.commit()

    # Establish workspace context
    await runtime_session.execute(
        text("SELECT set_config('app.current_workspace_id', :ws, true);"),
        {"ws": str(ws_id)},
    )

    # 1. DELETE is denied by PostgreSQL grant permissions
    with pytest.raises(ProgrammingError) as exc_del:
        await runtime_session.execute(text("DELETE FROM public.claims WHERE id = :id;"), {"id": str(claim_id)})
    assert "permission denied for table claims" in str(exc_del.value).lower()
    await runtime_session.rollback()

    # Re-establish context after rollback
    await runtime_session.execute(
        text("SELECT set_config('app.current_workspace_id', :ws, true);"),
        {"ws": str(ws_id)},
    )

    # 2. Permitted UPDATE: status, version, updated_at on claims succeeds
    await runtime_session.execute(
        text("UPDATE public.claims SET status = 'needs_review', version = 2, updated_at = now() WHERE id = :id;"),
        {"id": str(claim_id)},
    )
    await runtime_session.commit()

    # 3. Prohibited UPDATE: Attempting to modify immutable business facts (subject) is denied by column grant
    await runtime_session.execute(
        text("SELECT set_config('app.current_workspace_id', :ws, true);"),
        {"ws": str(ws_id)},
    )
    with pytest.raises(ProgrammingError) as exc_subj:
        await runtime_session.execute(
            text("UPDATE public.claims SET subject = 'Tampered Subject' WHERE id = :id;"),
            {"id": str(claim_id)},
        )
    assert "permission denied" in str(exc_subj.value).lower()
    await runtime_session.rollback()

    # 4. Prohibited UPDATE on Agent api_key_hash is denied by column grant
    await runtime_session.execute(
        text("SELECT set_config('app.current_workspace_id', :ws, true);"),
        {"ws": str(ws_id)},
    )
    with pytest.raises(ProgrammingError) as exc_hash:
        await runtime_session.execute(
            text("UPDATE public.agents SET api_key_hash = 'tampered_hash_00000000000000000000000000000000000000000000000000' WHERE id = :id;"),
            {"id": str(agent_id)},
        )
    assert "permission denied" in str(exc_hash.value).lower()
    await runtime_session.rollback()


# ==============================================================================
# 4. End-to-End HTTP API Execution Under Restricted Runtime Role
# ==============================================================================

@pytest.mark.asyncio
async def test_e2e_http_api_under_restricted_runtime_role():
    """Verify that the FastAPI application executes completely under the restricted runtime role."""
    # Seed workspace and agent via admin connection
    admin_engine = create_async_engine(ADMIN_DB_URL, poolclass=NullPool)
    ws_id = uuid.uuid4()
    agent_id = uuid.uuid4()
    raw_key = "fil_live_e2e_runtime_key_999"
    key_hash = hash_api_key(raw_key)

    async with admin_engine.begin() as conn:
        await conn.execute(
            text("INSERT INTO public.workspaces (id, name, slug) VALUES (:id, 'Runtime WS', 'runtime-ws');"),
            {"id": str(ws_id)},
        )
        await conn.execute(
            text(
                "INSERT INTO public.agents (id, workspace_id, name, api_key_hash, default_scope, is_active) "
                "VALUES (:id, :ws, 'Runtime Worker', :h, 'team', true);"
            ),
            {"id": str(agent_id), "ws": str(ws_id), "h": key_hash},
        )
    await admin_engine.dispose()

    # Configure FastAPI app with runtime database session factory
    runtime_engine = create_async_engine(RUNTIME_DB_URL, poolclass=NullPool)
    runtime_session_factory = async_sessionmaker(bind=runtime_engine, class_=AsyncSession, expire_on_commit=False)

    runtime_settings = Settings(DATABASE_URL=RUNTIME_DB_URL, CORS_ORIGINS=["*"])
    app = create_app(runtime_settings)

    async def override_get_db():
        async with runtime_session_factory() as session:
            try:
                yield session
            except Exception:
                if session.is_active:
                    await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        headers = {"Authorization": f"Bearer {raw_key}"}

        # 1. Create a claim
        claim_res = await client.post(
            "/api/v1/claims",
            json={
                "claim_type": "fact",
                "subject": "System.Runtime",
                "predicate": "runs_on",
                "object_value": {"runtime": "python-3.12"},
                "raw_statement": "System runtime is python-3.12",
                "scope": "workspace",
            },
            headers=headers,
        )
        assert claim_res.status_code == 201, claim_res.text
        claim_data = claim_res.json()
        claim_id = claim_data["id"]
        assert claim_data["workspace_id"] == str(ws_id)

        # 2. Record an environment snapshot
        dummy_hash = "a" * 64
        snap_res = await client.post(
            "/api/v1/snapshots",
            json={
                "source_ref": "git:main:commit1",
                "source_type": "agent_client",
                "verification_level": "agent_reported",
                "scan_scope": "full_repository",
                "snapshot_data": {
                    "scanned_roots": ["."],
                    "files": {"config.json": dummy_hash},
                    "packages": {"pypi:fastapi": {"version": "0.115.0"}},
                    "packages_scope": "complete",
                    "runtime": {"python": {"version": "3.12.13"}},
                    "runtime_scope": "complete",
                },
            },
            headers=headers,
        )
        assert snap_res.status_code == 201, snap_res.text
        snap_id = snap_res.json()["id"]

        # 3. Establish initial conditions
        cond_res = await client.post(
            f"/api/v1/claims/{claim_id}/conditions",
            json={
                "based_on_snapshot_id": snap_id,
                "rationale": "Initial baseline conditions",
                "conditions": [
                    {
                        "condition_type": "file_hash",
                        "target_path": "config.json",
                        "comparator": "hash_equals",
                        "expected_hash": dummy_hash,
                        "is_critical": True,
                    }
                ],
            },
            headers=headers,
        )
        assert cond_res.status_code == 201, cond_res.text
        assert cond_res.json()["version"] == 1

        # 4. Re-verify existing conditions
        reverify_res = await client.post(
            f"/api/v1/claims/{claim_id}/reverify",
            json={
                "snapshot_id": snap_id,
                "action": "verify_existing",
                "expected_condition_version": 1,
                "attestation_notes": "Routine reverification",
            },
            headers=headers,
        )
        assert reverify_res.status_code == 200, reverify_res.text
        assert reverify_res.json()["outcome"] == "applicable"

    await runtime_engine.dispose()


# ==============================================================================
# 5. Threat Boundary: Limitations of Custom Session Variable RLS
# ==============================================================================

@pytest.mark.asyncio
async def test_threat_boundary_arbitrary_sql_can_alter_custom_setting(runtime_session: AsyncSession):
    """Document and demonstrate the threat boundary:
    If an attacker achieves arbitrary SQL execution under filament_app,
    they can call set_config to change their active workspace.
    This proves that RLS with custom session settings is an application query safety boundary,
    not a cryptographic sandbox against a compromised database connection.
    """
    ws_victim = uuid.uuid4()
    # The runtime role can execute set_config
    await runtime_session.execute(
        text("SELECT set_config('app.current_workspace_id', :ws, true);"),
        {"ws": str(ws_victim)},
    )
    current_val = await runtime_session.scalar(text("SELECT current_setting('app.current_workspace_id', true);"))
    assert current_val == str(ws_victim)
