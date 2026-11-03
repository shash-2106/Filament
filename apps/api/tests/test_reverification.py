"""Unit and HTTP route integration tests for formal re-verification and condition versioning (POST /api/v1/claims/{id}/reverify)."""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
import uuid

from fastapi import FastAPI
from httpx import AsyncClient
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from filament_api.api.dependencies.auth import get_current_agent_context
from filament_api.core.security import hash_api_key
from filament_api.db.session import get_db
from filament_api.models.agent import Agent
from filament_api.models.claim import Claim
from filament_api.models.condition import ClaimCondition, ClaimConditionSet, ClaimVerification
from filament_api.models.snapshot import EnvironmentSnapshot
from filament_api.schemas.condition import ConditionSpec, ReverifyClaimParams
from filament_api.services.condition import ConditionService
from filament_api.services.context import TrustedContext
from filament_api.services.exceptions import (
    ConditionSnapshotMismatchError,
    EntityNotFoundError,
    InvalidClaimStateError,
    StaleConditionVersionError,
    UnauthorizedActorError,
    WorkspaceMismatchError,
)

HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64
VALID_SECRET = "fil_reverify_test_secret_123"


@pytest.fixture
def reverify_env() -> dict:
    """Fixture providing workspace, agents, claim, active condition set, and snapshots."""
    workspace_id = uuid.uuid4()
    agent_id = uuid.uuid4()
    other_agent_id = uuid.uuid4()

    agent = Agent(
        id=agent_id,
        workspace_id=workspace_id,
        name="reverify-agent",
        api_key_hash=hash_api_key(VALID_SECRET),
        is_active=True,
    )
    other_agent = Agent(
        id=other_agent_id,
        workspace_id=workspace_id,
        name="other-agent",
        api_key_hash=hash_api_key("fil_other_agent_secret_456"),
        is_active=True,
    )

    context = TrustedContext(
        workspace_id=workspace_id,
        actor_type="agent",
        actor_id=agent_id,
        is_active=True,
    )

    claim_id = uuid.uuid4()
    claim = Claim(
        id=claim_id,
        workspace_id=workspace_id,
        agent_id=agent_id,
        claim_type="fact",
        subject="redis",
        predicate="cluster_mode",
        object_value={"enabled": True},
        raw_statement="Redis cluster mode is enabled.",
        scope="workspace",
        status="current",
        confidence=Decimal("1.00"),
        version=1,
        active_condition_version=1,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    snapshot_id = uuid.uuid4()
    snapshot = EnvironmentSnapshot(
        id=snapshot_id,
        workspace_id=workspace_id,
        collected_by_agent=agent_id,
        source_type="agent_client",
        verification_level="agent_reported",
        source_ref="git:commit_v1",
        scan_scope="full_repository",
        snapshot_data={
            "scanned_roots": ["."],
            "files": {"config/redis.conf": HASH_A},
            "unreadable_paths": [],
            "packages": {"pypi:redis": "5.0.1"},
            "packages_scope": "complete",
            "runtime": {"python": "3.12"},
            "runtime_scope": "complete",
        },
        created_at=datetime.now(timezone.utc),
    )

    # Version 1 condition set
    set_v1 = ClaimConditionSet(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        claim_id=claim_id,
        version=1,
        based_on_snapshot_id=snapshot_id,
        established_by_agent=agent_id,
        rationale="Initial redis assertion requirements",
        created_at=datetime.now(timezone.utc),
    )

    cond_file_v1 = ClaimCondition(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        claim_id=claim_id,
        condition_set_version=1,
        condition_type="file_hash",
        target_path="config/redis.conf",
        comparator="hash_equals",
        expected_hash=HASH_A,
        expected_value={},
        is_critical=True,
        created_at=datetime.now(timezone.utc),
    )
    cond_pkg_v1 = ClaimCondition(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        claim_id=claim_id,
        condition_set_version=1,
        condition_type="package_version",
        target_path="pypi:redis",
        comparator="version_equals",
        expected_hash=None,
        expected_value={"version": "5.0.1"},
        is_critical=True,
        created_at=datetime.now(timezone.utc),
    )
    set_v1.conditions = [cond_file_v1, cond_pkg_v1]

    return {
        "workspace_id": workspace_id,
        "agent": agent,
        "other_agent": other_agent,
        "context": context,
        "claim": claim,
        "snapshot": snapshot,
        "condition_set_v1": set_v1,
        "conditions_v1": [cond_file_v1, cond_pkg_v1],
    }


def make_reverify_session(env: dict) -> AsyncMock:
    """Helper creating a mock session wired to reverify_env fixtures."""
    agent = env["agent"]
    claim = env["claim"]
    snapshot = env["snapshot"]
    conditions = env["conditions_v1"]

    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.is_active = True

    def mock_scalar(stmt):
        stmt_str = str(stmt)
        if "FROM agents" in stmt_str:
            return agent
        if "FROM claims" in stmt_str:
            return claim
        if "FROM environment_snapshots" in stmt_str:
            return snapshot
        return None

    def mock_execute(stmt):
        stmt_str = str(stmt)
        res = MagicMock()
        if "FROM claims" in stmt_str:
            res.scalar_one_or_none.return_value = claim
        elif "FROM environment_snapshots" in stmt_str:
            res.scalar_one_or_none.return_value = snapshot
        elif "FROM claim_conditions" in stmt_str:
            res.scalars.return_value.all.return_value = conditions
        return res

    mock_session.scalar.side_effect = mock_scalar
    mock_session.execute.side_effect = mock_execute
    return mock_session


# =============================================================================
# 1. Operation A: Verify Against Existing Conditions Tests
# =============================================================================

@pytest.mark.asyncio
async def test_reverify_existing_conditions_applicable_success(reverify_env: dict) -> None:
    """Verifies that reverifying matching snapshot persists a verification record without mutating condition set."""
    mock_session = make_reverify_session(reverify_env)

    params = ReverifyClaimParams(
        snapshot_id=reverify_env["snapshot"].id,
        action="verify_existing",
        expected_condition_version=1,
        attestation_notes="Routine daily verification passed cleanly.",
    )

    result = await ConditionService.reverify_claim(
        session=mock_session,
        context=reverify_env["context"],
        claim_id=reverify_env["claim"].id,
        params=params,
    )

    assert result["outcome"] == "applicable"
    assert result["is_applicable"] is True
    assert result["action_taken"] == "verify_existing"
    assert result["condition_set_version"] == 1
    assert result["active_condition_version"] == 1
    assert result["claim_id"] == reverify_env["claim"].id
    assert result["snapshot_id"] == reverify_env["snapshot"].id
    assert result["verified_by_agent"] == reverify_env["agent"].id
    assert len(result["condition_results"]) == 2

    # Invariants: active_condition_version unchanged, claim version unchanged
    assert reverify_env["claim"].active_condition_version == 1
    assert reverify_env["claim"].version == 1

    # Database writes: verification added, flush called
    mock_session.add.assert_called()
    mock_session.flush.assert_awaited()


@pytest.mark.asyncio
async def test_reverify_existing_conditions_drifted_persists_mismatch(reverify_env: dict) -> None:
    """Verifies that a drifted file hash persists outcome='environment_mismatch' and is_applicable=False."""
    # Modify snapshot to contain drifted hash
    reverify_env["snapshot"].snapshot_data["files"]["config/redis.conf"] = HASH_B

    mock_session = make_reverify_session(reverify_env)

    params = ReverifyClaimParams(
        snapshot_id=reverify_env["snapshot"].id,
        action="verify_existing",
        expected_condition_version=1,
        attestation_notes="Detected drift in redis configuration.",
    )

    result = await ConditionService.reverify_claim(
        session=mock_session,
        context=reverify_env["context"],
        claim_id=reverify_env["claim"].id,
        params=params,
    )

    assert result["outcome"] == "environment_mismatch"
    assert result["is_applicable"] is False
    assert result["action_taken"] == "verify_existing"
    assert result["condition_set_version"] == 1

    # Verification added to session
    added_entities = [call.args[0] for call in mock_session.add.call_args_list]
    verifications = [e for e in added_entities if isinstance(e, ClaimVerification)]
    assert len(verifications) == 1
    assert verifications[0].outcome == "environment_mismatch"
    assert verifications[0].condition_set_version == 1


# =============================================================================
# 2. Operation B: Adopt New Conditions Tests
# =============================================================================

@pytest.mark.asyncio
async def test_adopt_new_conditions_success(reverify_env: dict) -> None:
    """Verifies that explicit adoption establishes version 2, updates active pointer, and persists verification."""
    # Snapshot contains updated redis.conf (HASH_B) and updated redis pkg 5.0.2
    reverify_env["snapshot"].snapshot_data["files"]["config/redis.conf"] = HASH_B
    reverify_env["snapshot"].snapshot_data["packages"]["pypi:redis"] = "5.0.2"

    mock_session = make_reverify_session(reverify_env)

    params = ReverifyClaimParams(
        snapshot_id=reverify_env["snapshot"].id,
        action="adopt_new_conditions",
        expected_condition_version=1,
        attestation_notes="Adopting upgraded redis config and dependency version.",
        adopt_rationale="Upgraded Redis to 5.0.2 cluster topology.",
        proposed_conditions=[
            ConditionSpec(
                condition_type="file_hash",
                target_path="config/redis.conf",
                comparator="hash_equals",
                expected_hash=HASH_B,
                is_critical=True,
            ),
            ConditionSpec(
                condition_type="package_version",
                target_path="pypi:redis",
                comparator="version_equals",
                expected_value={"version": "5.0.2"},
                is_critical=True,
            ),
        ],
    )

    result = await ConditionService.reverify_claim(
        session=mock_session,
        context=reverify_env["context"],
        claim_id=reverify_env["claim"].id,
        params=params,
    )

    assert result["outcome"] == "applicable"
    assert result["is_applicable"] is True
    assert result["action_taken"] == "adopt_new_conditions"
    assert result["condition_set_version"] == 2
    assert result["active_condition_version"] == 2

    # Invariants: active_condition_version updated to 2, claim version incremented to 2
    assert reverify_env["claim"].active_condition_version == 2
    assert reverify_env["claim"].version == 2

    # Verify entities added to session
    added_entities = [call.args[0] for call in mock_session.add.call_args_list]
    condition_sets = [e for e in added_entities if isinstance(e, ClaimConditionSet)]
    assert len(condition_sets) == 1
    assert condition_sets[0].version == 2
    assert condition_sets[0].rationale == "Upgraded Redis to 5.0.2 cluster topology."

    conditions = [e for e in added_entities if isinstance(e, ClaimCondition)]
    assert len(conditions) == 2
    assert all(c.condition_set_version == 2 for c in conditions)

    verifications = [e for e in added_entities if isinstance(e, ClaimVerification)]
    assert len(verifications) == 1
    assert verifications[0].condition_set_version == 2
    assert verifications[0].outcome == "applicable"


@pytest.mark.asyncio
async def test_adopt_new_conditions_fails_when_proposed_conditions_mismatch_snapshot(reverify_env: dict) -> None:
    """Verifies that proposed conditions must evaluate to SATISFIED against snapshot, or adoption is rejected."""
    mock_session = make_reverify_session(reverify_env)

    params = ReverifyClaimParams(
        snapshot_id=reverify_env["snapshot"].id,
        action="adopt_new_conditions",
        expected_condition_version=1,
        attestation_notes="Attempting adoption with mismatched hash.",
        adopt_rationale="New config",
        proposed_conditions=[
            ConditionSpec(
                condition_type="file_hash",
                target_path="config/redis.conf",
                comparator="hash_equals",
                expected_hash=HASH_C,  # Snapshot contains HASH_A!
                is_critical=True,
            )
        ],
    )

    with pytest.raises(ConditionSnapshotMismatchError, match="not satisfied by snapshot"):
        await ConditionService.reverify_claim(
            session=mock_session,
            context=reverify_env["context"],
            claim_id=reverify_env["claim"].id,
            params=params,
        )

    # Invariants: active_condition_version must remain 1
    assert reverify_env["claim"].active_condition_version == 1
    assert reverify_env["claim"].version == 1


# =============================================================================
# 3. Concurrency, Guards, & Intent Validation Tests
# =============================================================================

@pytest.mark.asyncio
async def test_reverify_rejects_stale_expected_version(reverify_env: dict) -> None:
    """Verifies optimistic concurrency guard: stale expected version raises StaleConditionVersionError."""
    mock_session = make_reverify_session(reverify_env)

    params = ReverifyClaimParams(
        snapshot_id=reverify_env["snapshot"].id,
        action="verify_existing",
        expected_condition_version=99,  # Current is 1
        attestation_notes="Testing stale version guard",
    )

    with pytest.raises(StaleConditionVersionError, match="expected active version 99"):
        await ConditionService.reverify_claim(
            session=mock_session,
            context=reverify_env["context"],
            claim_id=reverify_env["claim"].id,
            params=params,
        )


@pytest.mark.asyncio
async def test_reverify_schema_rejects_silent_adoption_intent() -> None:
    """Verifies that proposed_conditions without explicit action='adopt_new_conditions' is rejected at schema level."""
    from pydantic import ValidationError

    # Passing proposed_conditions with action='verify_existing'
    with pytest.raises(ValidationError, match="must not be provided when action is 'verify_existing'"):
        ReverifyClaimParams(
            snapshot_id=uuid.uuid4(),
            action="verify_existing",
            expected_condition_version=1,
            attestation_notes="Testing rejection",
            proposed_conditions=[
                ConditionSpec(
                    condition_type="file_hash",
                    target_path="config/redis.conf",
                    comparator="hash_equals",
                    expected_hash=HASH_A,
                )
            ],
        )

    # Action='adopt_new_conditions' missing proposed_conditions
    with pytest.raises(ValidationError, match="proposed_conditions cannot be empty"):
        ReverifyClaimParams(
            snapshot_id=uuid.uuid4(),
            action="adopt_new_conditions",
            expected_condition_version=1,
            attestation_notes="Testing missing conditions",
            adopt_rationale="Some rationale",
            proposed_conditions=[],
        )

    # Action='adopt_new_conditions' missing adopt_rationale
    with pytest.raises(ValidationError, match="adopt_rationale is required"):
        ReverifyClaimParams(
            snapshot_id=uuid.uuid4(),
            action="adopt_new_conditions",
            expected_condition_version=1,
            attestation_notes="Testing missing rationale",
            proposed_conditions=[
                ConditionSpec(
                    condition_type="file_hash",
                    target_path="config/redis.conf",
                    comparator="hash_equals",
                    expected_hash=HASH_A,
                )
            ],
        )


# =============================================================================
# 4. Lifecycle & Security Restrictions
# =============================================================================

@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["retracted", "superseded"])
async def test_reverify_rejects_terminal_lifecycle_states(reverify_env: dict, status: str) -> None:
    """Verifies that claims in terminal status ('retracted', 'superseded') cannot be reverified."""
    reverify_env["claim"].status = status
    mock_session = make_reverify_session(reverify_env)

    params = ReverifyClaimParams(
        snapshot_id=reverify_env["snapshot"].id,
        action="verify_existing",
        expected_condition_version=1,
        attestation_notes="Attempting reverification of terminal claim",
    )

    with pytest.raises(InvalidClaimStateError, match="terminal status"):
        await ConditionService.reverify_claim(
            session=mock_session,
            context=reverify_env["context"],
            claim_id=reverify_env["claim"].id,
            params=params,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["needs_review", "disputed"])
async def test_reverify_preserves_claim_status_without_silent_mutation(reverify_env: dict, status: str) -> None:
    """Verifies that reverifying a needs_review or disputed claim does NOT silently alter its status."""
    reverify_env["claim"].status = status
    mock_session = make_reverify_session(reverify_env)

    params = ReverifyClaimParams(
        snapshot_id=reverify_env["snapshot"].id,
        action="verify_existing",
        expected_condition_version=1,
        attestation_notes=f"Reverifying claim in {status} state.",
    )

    result = await ConditionService.reverify_claim(
        session=mock_session,
        context=reverify_env["context"],
        claim_id=reverify_env["claim"].id,
        params=params,
    )

    assert result["outcome"] == "indeterminate"
    assert result["is_applicable"] is False
    # Status is preserved exactly as it was
    assert reverify_env["claim"].status == status


@pytest.mark.asyncio
async def test_reverify_rejects_unconditioned_claim(reverify_env: dict) -> None:
    """Verifies that an unconditioned claim cannot be reverified."""
    reverify_env["claim"].active_condition_version = None
    mock_session = make_reverify_session(reverify_env)

    params = ReverifyClaimParams(
        snapshot_id=reverify_env["snapshot"].id,
        action="verify_existing",
        expected_condition_version=1,
        attestation_notes="Testing unconditioned claim rejection",
    )

    with pytest.raises(InvalidClaimStateError, match="no active conditions established"):
        await ConditionService.reverify_claim(
            session=mock_session,
            context=reverify_env["context"],
            claim_id=reverify_env["claim"].id,
            params=params,
        )


@pytest.mark.asyncio
async def test_reverify_rejects_cross_workspace_snapshot(reverify_env: dict) -> None:
    """Verifies that referencing a snapshot from another workspace raises WorkspaceMismatchError."""
    reverify_env["snapshot"].workspace_id = uuid.uuid4()
    mock_session = make_reverify_session(reverify_env)

    params = ReverifyClaimParams(
        snapshot_id=reverify_env["snapshot"].id,
        action="verify_existing",
        expected_condition_version=1,
        attestation_notes="Testing cross workspace snapshot",
    )

    with pytest.raises(WorkspaceMismatchError, match="another workspace"):
        await ConditionService.reverify_claim(
            session=mock_session,
            context=reverify_env["context"],
            claim_id=reverify_env["claim"].id,
            params=params,
        )


# =============================================================================
# 5. HTTP Route Integration Tests (POST /api/v1/claims/{id}/reverify)
# =============================================================================

@pytest.mark.asyncio
async def test_reverify_route_verify_existing_200(
    app: FastAPI,
    async_client: AsyncClient,
    reverify_env: dict,
) -> None:
    """Verifies that POST /api/v1/claims/{id}/reverify with verify_existing commits transaction and returns 200."""
    mock_session = make_reverify_session(reverify_env)
    app.dependency_overrides[get_db] = lambda: mock_session

    payload = {
        "snapshot_id": str(reverify_env["snapshot"].id),
        "action": "verify_existing",
        "expected_condition_version": 1,
        "attestation_notes": "Route verification test passing.",
    }

    response = await async_client.post(
        f"/api/v1/claims/{reverify_env['claim'].id}/reverify",
        json=payload,
        headers={"Authorization": f"Bearer {VALID_SECRET}"},
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["outcome"] == "applicable"
    assert data["is_applicable"] is True
    assert data["action_taken"] == "verify_existing"
    assert data["condition_set_version"] == 1
    assert data["active_condition_version"] == 1
    assert "verification_id" in data
    assert len(data["condition_results"]) == 2

    # Confirms transaction was committed
    mock_session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_reverify_route_adopt_new_conditions_200(
    app: FastAPI,
    async_client: AsyncClient,
    reverify_env: dict,
) -> None:
    """Verifies that POST /api/v1/claims/{id}/reverify with adopt_new_conditions updates active version to 2."""
    reverify_env["snapshot"].snapshot_data["files"]["config/redis.conf"] = HASH_B
    mock_session = make_reverify_session(reverify_env)
    app.dependency_overrides[get_db] = lambda: mock_session

    payload = {
        "snapshot_id": str(reverify_env["snapshot"].id),
        "action": "adopt_new_conditions",
        "expected_condition_version": 1,
        "attestation_notes": "Adopting v2 config.",
        "adopt_rationale": "Updated cluster configuration",
        "proposed_conditions": [
            {
                "condition_type": "file_hash",
                "target_path": "config/redis.conf",
                "comparator": "hash_equals",
                "expected_hash": HASH_B,
                "is_critical": True,
            }
        ],
    }

    response = await async_client.post(
        f"/api/v1/claims/{reverify_env['claim'].id}/reverify",
        json=payload,
        headers={"Authorization": f"Bearer {VALID_SECRET}"},
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["outcome"] == "applicable"
    assert data["is_applicable"] is True
    assert data["action_taken"] == "adopt_new_conditions"
    assert data["condition_set_version"] == 2
    assert data["active_condition_version"] == 2
    mock_session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_reverify_route_stale_version_409(
    app: FastAPI,
    async_client: AsyncClient,
    reverify_env: dict,
) -> None:
    """Verifies that stale expected version returns HTTP 409 Conflict."""
    mock_session = make_reverify_session(reverify_env)
    app.dependency_overrides[get_db] = lambda: mock_session

    payload = {
        "snapshot_id": str(reverify_env["snapshot"].id),
        "action": "verify_existing",
        "expected_condition_version": 42,  # Stale! Current is 1
        "attestation_notes": "Testing conflict",
    }

    response = await async_client.post(
        f"/api/v1/claims/{reverify_env['claim'].id}/reverify",
        json=payload,
        headers={"Authorization": f"Bearer {VALID_SECRET}"},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "STALE_CONDITION_VERSION"
    mock_session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_reverify_route_scope_visibility_rules(
    app: FastAPI,
    async_client: AsyncClient,
    reverify_env: dict,
) -> None:
    """Verifies scope visibility: private and team claims fail-closed (HTTP 404) for other agents in workspace."""
    other_secret = "fil_other_agent_secret_456"
    other_agent = reverify_env["other_agent"]

    mock_session = make_reverify_session(reverify_env)

    def mock_scalar(stmt):
        if "FROM agents" in str(stmt):
            return other_agent
        if "FROM claims" in str(stmt):
            return reverify_env["claim"]
        if "FROM environment_snapshots" in str(stmt):
            return reverify_env["snapshot"]
        return None

    mock_session.scalar.side_effect = mock_scalar
    app.dependency_overrides[get_db] = lambda: mock_session

    payload = {
        "snapshot_id": str(reverify_env["snapshot"].id),
        "action": "verify_existing",
        "expected_condition_version": 1,
        "attestation_notes": "Testing visibility",
    }

    # Case 1: Workspace scope -> visible to other agent
    reverify_env["claim"].scope = "workspace"
    resp_ws = await async_client.post(
        f"/api/v1/claims/{reverify_env['claim'].id}/reverify",
        json=payload,
        headers={"Authorization": f"Bearer {other_secret}"},
    )
    assert resp_ws.status_code == 200

    # Case 2: Private scope -> fail-closed (HTTP 404)
    reverify_env["claim"].scope = "private"
    resp_priv = await async_client.post(
        f"/api/v1/claims/{reverify_env['claim'].id}/reverify",
        json=payload,
        headers={"Authorization": f"Bearer {other_secret}"},
    )
    assert resp_priv.status_code == 404

    # Case 3: Team scope -> fail-closed under current schema (HTTP 404)
    reverify_env["claim"].scope = "team"
    resp_team = await async_client.post(
        f"/api/v1/claims/{reverify_env['claim'].id}/reverify",
        json=payload,
        headers={"Authorization": f"Bearer {other_secret}"},
    )
    assert resp_team.status_code == 404


@pytest.mark.asyncio
async def test_reverify_route_rollback_on_response_or_commit_failure(
    app: FastAPI,
    async_client: AsyncClient,
    reverify_env: dict,
) -> None:
    """Verifies that an error during commit triggers rollback and returns HTTP 500."""
    mock_session = make_reverify_session(reverify_env)
    mock_session.commit.side_effect = RuntimeError("Database connection severed during commit")
    app.dependency_overrides[get_db] = lambda: mock_session

    payload = {
        "snapshot_id": str(reverify_env["snapshot"].id),
        "action": "verify_existing",
        "expected_condition_version": 1,
        "attestation_notes": "Testing rollback safety.",
    }

    response = await async_client.post(
        f"/api/v1/claims/{reverify_env['claim'].id}/reverify",
        json=payload,
        headers={"Authorization": f"Bearer {VALID_SECRET}"},
    )

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_SERVER_ERROR"
    mock_session.rollback.assert_awaited()

