"""Unit and integration tests for transient condition evaluation (POST /api/v1/claims/{id}/evaluate)."""

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
from filament_api.models.condition import ClaimCondition, ClaimConditionSet
from filament_api.models.snapshot import EnvironmentSnapshot
from filament_api.services.context import TrustedContext
from filament_api.services.evaluation import EvaluationService
from filament_api.services.exceptions import (
    EntityNotFoundError,
    UnauthorizedActorError,
    WorkspaceMismatchError,
)

HASH_A = "a" * 64
HASH_B = "b" * 64
VALID_SECRET = "fil_live_eval_test_key_123"


@pytest.fixture
def test_env() -> dict:
    """Fixture providing workspace, agents, claim, conditions, and snapshot."""
    workspace_id = uuid.uuid4()
    agent_id = uuid.uuid4()
    other_agent_id = uuid.uuid4()

    agent = Agent(
        id=agent_id,
        workspace_id=workspace_id,
        name="eval-agent",
        api_key_hash=hash_api_key(VALID_SECRET),
        is_active=True,
    )
    other_agent = Agent(
        id=other_agent_id,
        workspace_id=workspace_id,
        name="other-agent",
        api_key_hash=hash_api_key("fil_other_key_456"),
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
        source_ref="git:commit_abc",
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

    cond_file = ClaimCondition(
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
    cond_pkg = ClaimCondition(
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

    return {
        "workspace_id": workspace_id,
        "agent": agent,
        "other_agent": other_agent,
        "context": context,
        "claim": claim,
        "snapshot": snapshot,
        "conditions": [cond_file, cond_pkg],
    }


def make_mock_session(test_env: dict) -> AsyncMock:
    """Helper creating an AsyncSession mock wired to test_env fixtures."""
    agent = test_env["agent"]
    claim = test_env["claim"]
    snapshot = test_env["snapshot"]
    conditions = test_env["conditions"]

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
        if "FROM environment_snapshots" in stmt_str:
            res.scalar_one_or_none.return_value = snapshot
        elif "FROM claim_conditions" in stmt_str:
            res.scalars.return_value.all.return_value = conditions
        elif "FROM claims" in stmt_str:
            res.scalar_one_or_none.return_value = claim
        return res

    mock_session.scalar.side_effect = mock_scalar
    mock_session.execute.side_effect = mock_execute
    return mock_session


# =============================================================================
# 1. Domain Service Unit Tests
# =============================================================================

@pytest.mark.asyncio
async def test_evaluate_claim_conditions_applicable_success(test_env: dict) -> None:
    """Verifies that matching conditions produce 'applicable' outcome with is_applicable=True."""
    mock_session = make_mock_session(test_env)
    res = await EvaluationService.evaluate_claim_conditions(
        session=mock_session,
        context=test_env["context"],
        claim_id=test_env["claim"].id,
        snapshot_id=test_env["snapshot"].id,
    )

    assert res.outcome == "applicable"
    assert res.is_applicable is True
    assert res.claim_id == test_env["claim"].id
    assert res.snapshot_id == test_env["snapshot"].id
    assert res.active_condition_version == 1
    assert len(res.condition_results) == 2

    # Check individual item fields
    item1 = res.condition_results[0]
    assert item1.condition_type == "file_hash"
    assert item1.target_path == "config/redis.conf"
    assert item1.target == "config/redis.conf"
    assert item1.is_critical is True
    assert item1.status == "SATISFIED"
    assert item1.reason == "HASH_MATCHES"
    assert item1.expected_value == HASH_A
    assert item1.observed_value == HASH_A

    # Strict read-only assertions
    mock_session.commit.assert_not_awaited()
    mock_session.flush.assert_not_awaited()
    mock_session.add.assert_not_called()
    assert test_env["claim"].version == 1
    assert test_env["claim"].status == "current"
    assert test_env["claim"].active_condition_version == 1


@pytest.mark.asyncio
async def test_evaluate_claim_conditions_environment_mismatch_drifted(test_env: dict) -> None:
    """Verifies that a critical drifted condition results in 'environment_mismatch' and is_applicable=False."""
    # Modify snapshot to have different hash
    test_env["snapshot"].snapshot_data["files"]["config/redis.conf"] = HASH_B

    mock_session = make_mock_session(test_env)
    res = await EvaluationService.evaluate_claim_conditions(
        session=mock_session,
        context=test_env["context"],
        claim_id=test_env["claim"].id,
        snapshot_id=test_env["snapshot"].id,
    )

    assert res.outcome == "environment_mismatch"
    assert res.is_applicable is False
    drifted_item = [i for i in res.condition_results if i.target_path == "config/redis.conf"][0]
    assert drifted_item.status == "DRIFTED"
    assert drifted_item.reason == "CONTENT_HASH_MISMATCH"
    assert drifted_item.observed_value == HASH_B


@pytest.mark.asyncio
async def test_evaluate_claim_conditions_indeterminate_unchecked(test_env: dict) -> None:
    """Verifies that a critical unchecked condition results in 'indeterminate' and is_applicable=False."""
    # Mark target path as unreadable in snapshot
    test_env["snapshot"].snapshot_data["files"] = {}
    test_env["snapshot"].snapshot_data["unreadable_paths"] = ["config/redis.conf"]

    mock_session = make_mock_session(test_env)
    res = await EvaluationService.evaluate_claim_conditions(
        session=mock_session,
        context=test_env["context"],
        claim_id=test_env["claim"].id,
        snapshot_id=test_env["snapshot"].id,
    )

    assert res.outcome == "indeterminate"
    assert res.is_applicable is False
    item = [i for i in res.condition_results if i.target_path == "config/redis.conf"][0]
    assert item.status == "UNCHECKED"
    assert item.reason == "PATH_UNREADABLE"


@pytest.mark.asyncio
async def test_evaluate_claim_conditions_drifted_takes_precedence_over_unchecked(test_env: dict) -> None:
    """Verifies that if both critical DRIFTED and critical UNCHECKED exist, outcome is environment_mismatch."""
    # File drifted (HASH_B), package absent from partial inventory (UNCHECKED)
    test_env["snapshot"].snapshot_data["files"]["config/redis.conf"] = HASH_B
    test_env["snapshot"].snapshot_data["packages"] = {}
    test_env["snapshot"].snapshot_data["packages_scope"] = "partial"

    mock_session = make_mock_session(test_env)
    res = await EvaluationService.evaluate_claim_conditions(
        session=mock_session,
        context=test_env["context"],
        claim_id=test_env["claim"].id,
        snapshot_id=test_env["snapshot"].id,
    )

    assert res.outcome == "environment_mismatch"
    assert res.is_applicable is False


@pytest.mark.asyncio
async def test_evaluate_claim_conditions_noncritical_drifted_still_applicable(test_env: dict) -> None:
    """Verifies that noncritical drifted conditions do not independently change overall outcome."""
    # Add a non-critical condition that drifts
    non_crit = ClaimCondition(
        id=uuid.uuid4(),
        workspace_id=test_env["workspace_id"],
        claim_id=test_env["claim"].id,
        condition_set_version=1,
        condition_type="runtime_fact",
        target_path="os",
        comparator="runtime_equals",
        expected_hash=None,
        expected_value={"value": "darwin"},
        is_critical=False,
        created_at=datetime.now(timezone.utc),
    )
    test_env["conditions"].append(non_crit)
    test_env["snapshot"].snapshot_data["runtime"] = {"python": "3.12", "os": "linux"}

    mock_session = make_mock_session(test_env)
    res = await EvaluationService.evaluate_claim_conditions(
        session=mock_session,
        context=test_env["context"],
        claim_id=test_env["claim"].id,
        snapshot_id=test_env["snapshot"].id,
    )

    # All critical conditions (file and pkg) are satisfied, so overall outcome is applicable!
    assert res.outcome == "applicable"
    assert res.is_applicable is True
    non_crit_item = [i for i in res.condition_results if i.target_path == "os"][0]
    assert non_crit_item.is_critical is False
    assert non_crit_item.status == "DRIFTED"
    assert non_crit_item.reason == "RUNTIME_FACT_MISMATCH"


@pytest.mark.asyncio
async def test_evaluate_claim_conditions_unconditioned_claim(test_env: dict) -> None:
    """Verifies that an unconditioned claim returns outcome='unconditioned' and is_applicable=False."""
    test_env["claim"].active_condition_version = None

    mock_session = make_mock_session(test_env)
    res = await EvaluationService.evaluate_claim_conditions(
        session=mock_session,
        context=test_env["context"],
        claim_id=test_env["claim"].id,
        snapshot_id=test_env["snapshot"].id,
    )

    assert res.outcome == "unconditioned"
    assert res.is_applicable is False
    assert res.active_condition_version is None
    assert res.condition_results == []


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["retracted", "superseded", "disputed", "needs_review"])
async def test_evaluate_claim_conditions_lifecycle_states(test_env: dict, status: str) -> None:
    """Verifies that claims in non-current lifecycle states return 'not_applicable' regardless of condition match."""
    test_env["claim"].status = status

    mock_session = make_mock_session(test_env)
    res = await EvaluationService.evaluate_claim_conditions(
        session=mock_session,
        context=test_env["context"],
        claim_id=test_env["claim"].id,
        snapshot_id=test_env["snapshot"].id,
    )

    assert res.outcome == "not_applicable"
    assert res.is_applicable is False
    # Conditions are still returned for diagnostics
    assert len(res.condition_results) == 2


@pytest.mark.asyncio
async def test_evaluate_claim_conditions_missing_entities(test_env: dict) -> None:
    """Verifies that missing claim or missing snapshot raises EntityNotFoundError."""
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.scalar.return_value = None
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = mock_res

    # Missing claim
    with pytest.raises(EntityNotFoundError, match="Claim"):
        await EvaluationService.evaluate_claim_conditions(
            session=mock_session,
            context=test_env["context"],
            claim_id=uuid.uuid4(),
            snapshot_id=test_env["snapshot"].id,
        )

    # Missing snapshot
    mock_session.scalar.return_value = test_env["claim"]
    with pytest.raises(EntityNotFoundError, match="EnvironmentSnapshot"):
        await EvaluationService.evaluate_claim_conditions(
            session=mock_session,
            context=test_env["context"],
            claim_id=test_env["claim"].id,
            snapshot_id=uuid.uuid4(),
        )


@pytest.mark.asyncio
async def test_evaluate_claim_conditions_cross_workspace_snapshot(test_env: dict) -> None:
    """Verifies that referencing a snapshot from a different workspace raises WorkspaceMismatchError."""
    other_ws = uuid.uuid4()
    test_env["snapshot"].workspace_id = other_ws

    mock_session = make_mock_session(test_env)
    with pytest.raises(WorkspaceMismatchError, match="another workspace"):
        await EvaluationService.evaluate_claim_conditions(
            session=mock_session,
            context=test_env["context"],
            claim_id=test_env["claim"].id,
            snapshot_id=test_env["snapshot"].id,
        )


@pytest.mark.asyncio
async def test_evaluate_claim_conditions_non_agent_rejected(test_env: dict) -> None:
    """Verifies that callers who are not agents are rejected with UnauthorizedActorError."""
    mock_session = make_mock_session(test_env)
    user_context = TrustedContext(
        workspace_id=test_env["workspace_id"],
        actor_type="user",
        actor_id=uuid.uuid4(),
        is_active=True,
    )

    with pytest.raises(UnauthorizedActorError, match="authorized agent"):
        await EvaluationService.evaluate_claim_conditions(
            session=mock_session,
            context=user_context,
            claim_id=test_env["claim"].id,
            snapshot_id=test_env["snapshot"].id,
        )


# =============================================================================
# 2. HTTP Route Integration Tests (POST /api/v1/claims/{id}/evaluate)
# =============================================================================

@pytest.mark.asyncio
async def test_evaluate_route_success(
    app: FastAPI,
    async_client: AsyncClient,
    test_env: dict,
) -> None:
    """Verifies that POST /api/v1/claims/{id}/evaluate returns HTTP 200 with evaluation payload."""
    mock_session = make_mock_session(test_env)
    app.dependency_overrides[get_db] = lambda: mock_session

    response = await async_client.post(
        f"/api/v1/claims/{test_env['claim'].id}/evaluate",
        json={"snapshot_id": str(test_env["snapshot"].id)},
        headers={"Authorization": f"Bearer {VALID_SECRET}"},
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["claim_id"] == str(test_env["claim"].id)
    assert data["snapshot_id"] == str(test_env["snapshot"].id)
    assert data["outcome"] == "applicable"
    assert data["is_applicable"] is True
    assert len(data["condition_results"]) == 2

    # Verify no commit was made
    mock_session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_evaluate_route_404_on_missing_claim_or_snapshot(
    app: FastAPI,
    async_client: AsyncClient,
    test_env: dict,
) -> None:
    """Verifies that missing claim or snapshot returns HTTP 404."""
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.scalar.return_value = test_env["agent"]  # auth succeeds
    app.dependency_overrides[get_db] = lambda: mock_session

    # Claim not found
    def mock_scalar(stmt):
        if "FROM agents" in str(stmt):
            return test_env["agent"]
        return None

    mock_session.scalar.side_effect = mock_scalar

    response = await async_client.post(
        f"/api/v1/claims/{uuid.uuid4()}/evaluate",
        json={"snapshot_id": str(test_env["snapshot"].id)},
        headers={"Authorization": f"Bearer {VALID_SECRET}"},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_evaluate_route_404_on_cross_workspace_snapshot(
    app: FastAPI,
    async_client: AsyncClient,
    test_env: dict,
) -> None:
    """Verifies that referencing a cross-workspace snapshot defensively returns HTTP 404."""
    test_env["snapshot"].workspace_id = uuid.uuid4()
    mock_session = make_mock_session(test_env)
    app.dependency_overrides[get_db] = lambda: mock_session

    response = await async_client.post(
        f"/api/v1/claims/{test_env['claim'].id}/evaluate",
        json={"snapshot_id": str(test_env["snapshot"].id)},
        headers={"Authorization": f"Bearer {VALID_SECRET}"},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_evaluate_route_scope_visibility_rules(
    app: FastAPI,
    async_client: AsyncClient,
    test_env: dict,
) -> None:
    """Verifies scope visibility: private and team claims fail-closed for other agents; workspace claims succeed."""
    other_secret = "fil_other_key_456"
    other_agent = test_env["other_agent"]

    mock_session = make_mock_session(test_env)

    # Wire mock_scalar to return other_agent for auth
    def mock_scalar(stmt):
        if "FROM agents" in str(stmt):
            return other_agent
        if "FROM claims" in str(stmt):
            return test_env["claim"]
        if "FROM environment_snapshots" in str(stmt):
            return test_env["snapshot"]
        return None

    mock_session.scalar.side_effect = mock_scalar
    app.dependency_overrides[get_db] = lambda: mock_session

    # Case 1: Workspace scope -> visible to other_agent
    test_env["claim"].scope = "workspace"
    resp_ws = await async_client.post(
        f"/api/v1/claims/{test_env['claim'].id}/evaluate",
        json={"snapshot_id": str(test_env["snapshot"].id)},
        headers={"Authorization": f"Bearer {other_secret}"},
    )
    assert resp_ws.status_code == 200

    # Case 2: Private scope -> fail-closed (HTTP 404)
    test_env["claim"].scope = "private"
    resp_priv = await async_client.post(
        f"/api/v1/claims/{test_env['claim'].id}/evaluate",
        json={"snapshot_id": str(test_env["snapshot"].id)},
        headers={"Authorization": f"Bearer {other_secret}"},
    )
    assert resp_priv.status_code == 404

    # Case 3: Team scope -> fail-closed under current schema (HTTP 404)
    test_env["claim"].scope = "team"
    resp_team = await async_client.post(
        f"/api/v1/claims/{test_env['claim'].id}/evaluate",
        json={"snapshot_id": str(test_env["snapshot"].id)},
        headers={"Authorization": f"Bearer {other_secret}"},
    )
    assert resp_team.status_code == 404


@pytest.mark.asyncio
async def test_evaluate_route_requires_auth(
    app: FastAPI,
    async_client: AsyncClient,
    test_env: dict,
) -> None:
    """Verifies that missing or invalid auth produces HTTP 401."""
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.scalar.return_value = None  # invalid token lookup returns None
    app.dependency_overrides[get_db] = lambda: mock_session

    # Missing auth
    resp1 = await async_client.post(
        f"/api/v1/claims/{test_env['claim'].id}/evaluate",
        json={"snapshot_id": str(test_env["snapshot"].id)},
    )
    assert resp1.status_code == 401

    # Invalid auth token
    resp2 = await async_client.post(
        f"/api/v1/claims/{test_env['claim'].id}/evaluate",
        json={"snapshot_id": str(test_env["snapshot"].id)},
        headers={"Authorization": "Bearer fil_invalid_key_999"},
    )
    assert resp2.status_code == 401


@pytest.mark.asyncio
async def test_evaluate_route_repeated_evaluation_is_consistent_and_readonly(
    app: FastAPI,
    async_client: AsyncClient,
    test_env: dict,
) -> None:
    """Verifies that repeated evaluations produce identical results and perform zero mutations."""
    mock_session = make_mock_session(test_env)
    app.dependency_overrides[get_db] = lambda: mock_session

    url = f"/api/v1/claims/{test_env['claim'].id}/evaluate"
    payload = {"snapshot_id": str(test_env["snapshot"].id)}
    headers = {"Authorization": f"Bearer {VALID_SECRET}"}

    resp1 = await async_client.post(url, json=payload, headers=headers)
    resp2 = await async_client.post(url, json=payload, headers=headers)

    assert resp1.status_code == 200
    assert resp2.status_code == 200
    assert resp1.json() == resp2.json()

    # Confirms absolute absence of database modifications
    mock_session.commit.assert_not_awaited()
    mock_session.flush.assert_not_awaited()
    mock_session.add.assert_not_called()
