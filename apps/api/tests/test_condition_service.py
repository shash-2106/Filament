"""Automated tests for condition comparison logic and initial condition establishment."""

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
from filament_api.models.snapshot import EnvironmentSnapshot
from filament_api.schemas.condition import ConditionSpec, EstablishConditionsParams
from filament_api.services.condition import (
    ConditionService,
    ConditionStatus,
    evaluate_condition_against_snapshot,
)
from filament_api.services.context import TrustedContext
from filament_api.services.exceptions import (
    ConditionSnapshotMismatchError,
    ConditionsAlreadyEstablishedError,
    CriticalConditionRequiredError,
    EntityNotFoundError,
    UnauthorizedActorError,
    WorkspaceMismatchError,
)

HASH_A = "1111111111111111111111111111111111111111111111111111111111111111"
HASH_B = "2222222222222222222222222222222222222222222222222222222222222222"


# =============================================================================
# 1. Deterministic Condition Evaluation Logic Tests
# =============================================================================

def test_evaluate_file_hash_satisfied() -> None:
    """Verifies that an exact file hash match returns SATISFIED."""
    cond = ConditionSpec(
        condition_type="file_hash",
        target_path="config/app.conf",
        comparator="hash_equals",
        expected_hash=HASH_A,
    )
    snapshot_data = {
        "scanned_roots": ["."],
        "files": {"config/app.conf": HASH_A},
        "unreadable_paths": [],
    }
    res = evaluate_condition_against_snapshot(cond, "full_repository", snapshot_data)
    assert res.status == ConditionStatus.SATISFIED
    assert res.reason == "HASH_MATCHES"


def test_evaluate_file_hash_drifted() -> None:
    """Verifies that a hash mismatch returns DRIFTED."""
    cond = ConditionSpec(
        condition_type="file_hash",
        target_path="config/app.conf",
        comparator="hash_equals",
        expected_hash=HASH_A,
    )
    snapshot_data = {
        "scanned_roots": ["."],
        "files": {"config/app.conf": HASH_B},
        "unreadable_paths": [],
    }
    res = evaluate_condition_against_snapshot(cond, "full_repository", snapshot_data)
    assert res.status == ConditionStatus.DRIFTED
    assert res.reason == "CONTENT_HASH_MISMATCH"


def test_evaluate_file_hash_unreadable() -> None:
    """Verifies that an unreadable path returns UNCHECKED."""
    cond = ConditionSpec(
        condition_type="file_hash",
        target_path="secret/key.pem",
        comparator="hash_equals",
        expected_hash=HASH_A,
    )
    snapshot_data = {
        "scanned_roots": ["."],
        "files": {},
        "unreadable_paths": ["secret/key.pem"],
    }
    res = evaluate_condition_against_snapshot(cond, "full_repository", snapshot_data)
    assert res.status == ConditionStatus.UNCHECKED
    assert res.reason == "PATH_UNREADABLE"


def test_evaluate_file_hash_full_repo_deleted() -> None:
    """Verifies that an absent file in full_repository scan returns DRIFTED (FILE_DELETED)."""
    cond = ConditionSpec(
        condition_type="file_hash",
        target_path="old/file.txt",
        comparator="hash_equals",
        expected_hash=HASH_A,
    )
    snapshot_data = {
        "scanned_roots": ["."],
        "files": {},
        "unreadable_paths": [],
    }
    res = evaluate_condition_against_snapshot(cond, "full_repository", snapshot_data)
    assert res.status == ConditionStatus.DRIFTED
    assert res.reason == "FILE_DELETED"


def test_evaluate_file_hash_selective_scan_boundaries() -> None:
    """Verifies selective scan distinguishes between covered deletion and out-of-scope omission."""
    cond_in_scope = ConditionSpec(
        condition_type="file_hash",
        target_path="src/missing.py",
        comparator="hash_equals",
        expected_hash=HASH_A,
    )
    cond_out_of_scope = ConditionSpec(
        condition_type="file_hash",
        target_path="docs/readme.md",
        comparator="hash_equals",
        expected_hash=HASH_A,
    )
    snapshot_data = {
        "scanned_roots": ["src"],
        "files": {"src/other.py": HASH_A},
        "unreadable_paths": [],
    }

    # Within scan root -> DRIFTED (FILE_DELETED)
    res_in = evaluate_condition_against_snapshot(cond_in_scope, "selective", snapshot_data)
    assert res_in.status == ConditionStatus.DRIFTED
    assert res_in.reason == "FILE_DELETED"

    # Outside scan roots -> UNCHECKED (PATH_NOT_IN_SCAN_SCOPE)
    res_out = evaluate_condition_against_snapshot(cond_out_of_scope, "selective", snapshot_data)
    assert res_out.status == ConditionStatus.UNCHECKED
    assert res_out.reason == "PATH_NOT_IN_SCAN_SCOPE"


def test_evaluate_package_version_satisfied_and_mismatch() -> None:
    """Verifies package_version comparison for exact matches, mismatches, and scope completeness."""
    cond = ConditionSpec(
        condition_type="package_version",
        target_path="pypi:redis",
        comparator="version_equals",
        expected_value={"version": "5.0.1"},
    )

    # Match in partial inventory
    res_ok = evaluate_condition_against_snapshot(
        cond, "full_repository", {"packages": {"pypi:redis": "5.0.1"}, "packages_scope": "partial"}
    )
    assert res_ok.status == ConditionStatus.SATISFIED
    assert res_ok.reason == "VERSION_MATCHES"

    # Match in complete inventory
    res_ok_complete = evaluate_condition_against_snapshot(
        cond, "full_repository", {"packages": {"pypi:redis": "5.0.1"}, "packages_scope": "complete"}
    )
    assert res_ok_complete.status == ConditionStatus.SATISFIED

    # Mismatch in partial inventory
    res_diff = evaluate_condition_against_snapshot(
        cond, "full_repository", {"packages": {"pypi:redis": "4.9.0"}, "packages_scope": "partial"}
    )
    assert res_diff.status == ConditionStatus.DRIFTED
    assert res_diff.reason == "VERSION_MISMATCH"

    # Not found in complete inventory -> DRIFTED (PACKAGE_NOT_FOUND)
    res_missing_complete = evaluate_condition_against_snapshot(
        cond, "full_repository", {"packages": {}, "packages_scope": "complete"}
    )
    assert res_missing_complete.status == ConditionStatus.DRIFTED
    assert res_missing_complete.reason == "PACKAGE_NOT_FOUND"

    # Not found in partial inventory -> UNCHECKED (PACKAGE_NOT_IN_SCAN_SCOPE)
    res_missing_partial = evaluate_condition_against_snapshot(
        cond, "full_repository", {"packages": {}, "packages_scope": "partial"}
    )
    assert res_missing_partial.status == ConditionStatus.UNCHECKED
    assert res_missing_partial.reason == "PACKAGE_NOT_IN_SCAN_SCOPE"

    # Not found with undeclared / missing packages_scope metadata -> fails closed to partial -> UNCHECKED
    res_missing_undeclared = evaluate_condition_against_snapshot(
        cond, "full_repository", {"packages": {}}
    )
    assert res_missing_undeclared.status == ConditionStatus.UNCHECKED
    assert res_missing_undeclared.reason == "PACKAGE_NOT_IN_SCAN_SCOPE"


def test_evaluate_runtime_fact_satisfied_and_mismatch() -> None:
    """Verifies runtime_fact comparison for exact matches, mismatches, and scope completeness."""
    cond = ConditionSpec(
        condition_type="runtime_fact",
        target_path="python",
        comparator="runtime_equals",
        expected_value={"value": "3.12"},
    )

    # Match in partial inventory
    res_ok = evaluate_condition_against_snapshot(
        cond, "full_repository", {"runtime": {"python": "3.12"}, "runtime_scope": "partial"}
    )
    assert res_ok.status == ConditionStatus.SATISFIED
    assert res_ok.reason == "RUNTIME_FACT_MATCHES"

    # Match in complete inventory
    res_ok_complete = evaluate_condition_against_snapshot(
        cond, "full_repository", {"runtime": {"python": "3.12"}, "runtime_scope": "complete"}
    )
    assert res_ok_complete.status == ConditionStatus.SATISFIED

    # Mismatch in partial inventory
    res_diff = evaluate_condition_against_snapshot(
        cond, "full_repository", {"runtime": {"python": "3.11"}, "runtime_scope": "partial"}
    )
    assert res_diff.status == ConditionStatus.DRIFTED
    assert res_diff.reason == "RUNTIME_FACT_MISMATCH"

    # Not found in complete inventory -> DRIFTED (RUNTIME_FACT_NOT_FOUND)
    res_missing_complete = evaluate_condition_against_snapshot(
        cond, "full_repository", {"runtime": {}, "runtime_scope": "complete"}
    )
    assert res_missing_complete.status == ConditionStatus.DRIFTED
    assert res_missing_complete.reason == "RUNTIME_FACT_NOT_FOUND"

    # Not found in partial inventory -> UNCHECKED (RUNTIME_FACT_NOT_IN_SCAN_SCOPE)
    res_missing_partial = evaluate_condition_against_snapshot(
        cond, "full_repository", {"runtime": {}, "runtime_scope": "partial"}
    )
    assert res_missing_partial.status == ConditionStatus.UNCHECKED
    assert res_missing_partial.reason == "RUNTIME_FACT_NOT_IN_SCAN_SCOPE"

    # Not found with undeclared / missing runtime_scope metadata -> fails closed to partial -> UNCHECKED
    res_missing_undeclared = evaluate_condition_against_snapshot(
        cond, "full_repository", {"runtime": {}}
    )
    assert res_missing_undeclared.status == ConditionStatus.UNCHECKED
    assert res_missing_undeclared.reason == "RUNTIME_FACT_NOT_IN_SCAN_SCOPE"


def test_condition_spec_hash_validation() -> None:
    """Verifies schema-level validation of SHA-256 hashes for file_hash and lockfile_hash conditions."""
    from pydantic import ValidationError

    valid_hash = "a" * 64

    # Valid with expected_hash
    spec1 = ConditionSpec(
        condition_type="file_hash",
        target_path="src/main.py",
        comparator="hash_equals",
        expected_hash=valid_hash,
    )
    assert spec1.expected_hash == valid_hash

    # Valid with expected_value['hash']
    spec2 = ConditionSpec(
        condition_type="lockfile_hash",
        target_path="poetry.lock",
        comparator="hash_equals",
        expected_value={"hash": valid_hash},
    )
    assert spec2.expected_value["hash"] == valid_hash

    # Missing both expected_hash and expected_value['hash'] -> rejected
    with pytest.raises(ValidationError, match="requires a valid 64-character SHA-256 hash"):
        ConditionSpec(
            condition_type="file_hash",
            target_path="src/main.py",
            comparator="hash_equals",
        )

    # Empty hash in expected_value -> rejected
    with pytest.raises(ValidationError, match="requires a valid 64-character SHA-256 hash"):
        ConditionSpec(
            condition_type="file_hash",
            target_path="src/main.py",
            comparator="hash_equals",
            expected_value={"hash": ""},
        )

    # Invalid length in expected_value -> rejected
    with pytest.raises(ValidationError, match="Invalid SHA-256 hash"):
        ConditionSpec(
            condition_type="file_hash",
            target_path="src/main.py",
            comparator="hash_equals",
            expected_value={"hash": "abc123"},
        )

    # Non-hex characters in expected_value -> rejected
    with pytest.raises(ValidationError, match="Invalid SHA-256 hash"):
        ConditionSpec(
            condition_type="file_hash",
            target_path="src/main.py",
            comparator="hash_equals",
            expected_value={"hash": "z" * 64},
        )


def test_condition_spec_package_target_path_validation() -> None:
    """Verifies that ConditionSpec enforces <ecosystem>:<package-name> format on package_version."""
    from pydantic import ValidationError

    # Valid package target_path
    spec = ConditionSpec(
        condition_type="package_version",
        target_path="pypi:requests",
        comparator="version_equals",
        expected_value={"version": "2.31.0"},
    )
    assert spec.target_path == "pypi:requests"

    # Missing ecosystem prefix -> rejected
    with pytest.raises(ValidationError, match="must include an ecosystem namespace prefix"):
        ConditionSpec(
            condition_type="package_version",
            target_path="requests",
            comparator="version_equals",
            expected_value={"version": "2.31.0"},
        )

    # Leading/trailing whitespace -> rejected
    with pytest.raises(ValidationError, match="leading or trailing whitespace"):
        ConditionSpec(
            condition_type="package_version",
            target_path=" pypi:requests",
            comparator="version_equals",
            expected_value={"version": "2.31.0"},
        )


def test_snapshot_data_package_keys_validation() -> None:
    """Verifies that SnapshotData enforces <ecosystem>:<package-name> format on package inventory keys."""
    from pydantic import ValidationError
    from filament_api.schemas.snapshot import SnapshotData

    # Valid packages
    snap = SnapshotData(
        scanned_roots=["."],
        packages={"pypi:flask": "3.0.0", "npm:react": "18.2.0"},
        packages_scope="complete",
        runtime_scope="partial",
    )
    assert snap.packages["pypi:flask"] == "3.0.0"
    assert snap.packages_scope == "complete"
    assert snap.runtime_scope == "partial"

    # Invalid package key without ecosystem -> rejected
    with pytest.raises(ValidationError, match="must include an ecosystem namespace prefix"):
        SnapshotData(
            scanned_roots=["."],
            packages={"flask": "3.0.0"},
        )


# =============================================================================
# 2. ConditionService Domain Service Tests
# =============================================================================

@pytest.fixture
def test_setup() -> dict:
    """Fixture providing workspace, agent context, unconditioned claim, and matching snapshot."""
    workspace_id = uuid.uuid4()
    agent_id = uuid.uuid4()
    context = TrustedContext(workspace_id=workspace_id, actor_type="agent", actor_id=agent_id)

    claim = Claim(
        id=uuid.uuid4(),
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
        active_condition_version=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    snapshot = EnvironmentSnapshot(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        collected_by_agent=agent_id,
        source_type="agent_client",
        verification_level="agent_reported",
        source_ref="git:main:commit_1",
        scan_scope="full_repository",
        snapshot_data={
            "scanned_roots": ["."],
            "files": {"config/redis.conf": HASH_A},
            "unreadable_paths": [],
            "packages": {"pypi:redis": "5.0.1"},
            "runtime": {"python": "3.12"},
        },
        created_at=datetime.now(timezone.utc),
    )

    return {"context": context, "claim": claim, "snapshot": snapshot}


@pytest.mark.asyncio
async def test_establish_initial_conditions_success(test_setup: dict) -> None:
    """Verifies atomic establishment: condition set v1, condition rows, verification record, and claim pointer."""
    context = test_setup["context"]
    claim = test_setup["claim"]
    snapshot = test_setup["snapshot"]

    mock_session = AsyncMock(spec=AsyncSession)

    def mock_execute(stmt):
        mock_result = MagicMock()
        # Handle select(Claim)
        if "FROM claims" in str(stmt):
            mock_result.scalar_one_or_none.return_value = claim
        # Handle select(EnvironmentSnapshot)
        elif "FROM environment_snapshots" in str(stmt):
            mock_result.scalar_one_or_none.return_value = snapshot
        else:
            mock_result.scalar_one_or_none.return_value = None
        return mock_result

    mock_session.execute.side_effect = mock_execute

    params = EstablishConditionsParams(
        based_on_snapshot_id=snapshot.id,
        rationale="Binds redis cluster fact to config file and client library version.",
        conditions=[
            ConditionSpec(
                condition_type="file_hash",
                target_path="config/redis.conf",
                comparator="hash_equals",
                expected_hash=HASH_A,
                is_critical=True,
            ),
            ConditionSpec(
                condition_type="package_version",
                target_path="pypi:redis",
                comparator="version_equals",
                expected_value={"version": "5.0.1"},
                is_critical=False,
            ),
        ],
    )

    cond_set = await ConditionService.establish_initial_conditions(
        session=mock_session,
        context=context,
        claim_id=claim.id,
        params=params,
    )

    assert cond_set.version == 1
    assert cond_set.claim_id == claim.id
    assert cond_set.workspace_id == context.workspace_id
    assert len(cond_set.conditions) == 2

    # Verifies claim pointer and version were updated atomically
    assert claim.active_condition_version == 1
    assert claim.version == 2
    # Status remains current
    assert claim.status == "current"


@pytest.mark.asyncio
async def test_establish_conditions_rejects_already_conditioned_claim(test_setup: dict) -> None:
    """Verifies that attempting initial establishment on claim with non-NULL active_condition_version raises 409."""
    context = test_setup["context"]
    claim = test_setup["claim"]
    snapshot = test_setup["snapshot"]

    # Pre-condition claim to version 1
    claim.active_condition_version = 1

    mock_session = AsyncMock(spec=AsyncSession)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = claim
    mock_session.execute.return_value = mock_result

    params = EstablishConditionsParams(
        based_on_snapshot_id=snapshot.id,
        rationale="Re-establishment attempt",
        conditions=[
            ConditionSpec(
                condition_type="file_hash",
                target_path="config/redis.conf",
                comparator="hash_equals",
                expected_hash=HASH_A,
                is_critical=True,
            )
        ],
    )

    with pytest.raises(ConditionsAlreadyEstablishedError) as exc_info:
        await ConditionService.establish_initial_conditions(
            session=mock_session,
            context=context,
            claim_id=claim.id,
            params=params,
        )
    assert exc_info.value.active_version == 1


@pytest.mark.asyncio
async def test_establish_conditions_rejects_missing_critical(test_setup: dict) -> None:
    """Verifies that establishment without at least one critical condition is rejected."""
    context = test_setup["context"]
    claim = test_setup["claim"]
    snapshot = test_setup["snapshot"]

    mock_session = AsyncMock(spec=AsyncSession)

    def mock_execute(stmt):
        mock_result = MagicMock()
        if "FROM claims" in str(stmt):
            mock_result.scalar_one_or_none.return_value = claim
        elif "FROM environment_snapshots" in str(stmt):
            mock_result.scalar_one_or_none.return_value = snapshot
        return mock_result

    mock_session.execute.side_effect = mock_execute

    with pytest.raises(ValueError, match="at least one condition with is_critical=true"):
        EstablishConditionsParams(
            based_on_snapshot_id=snapshot.id,
            rationale="Rationale",
            conditions=[
                ConditionSpec(
                    condition_type="file_hash",
                    target_path="config/redis.conf",
                    comparator="hash_equals",
                    expected_hash=HASH_A,
                    is_critical=False,
                )
            ],
        )


@pytest.mark.asyncio
async def test_establish_conditions_rejects_snapshot_mismatch(test_setup: dict) -> None:
    """Verifies that establishment fails if any proposed condition is DRIFTED or UNCHECKED."""
    context = test_setup["context"]
    claim = test_setup["claim"]
    snapshot = test_setup["snapshot"]

    mock_session = AsyncMock(spec=AsyncSession)

    def mock_execute(stmt):
        mock_result = MagicMock()
        if "FROM claims" in str(stmt):
            mock_result.scalar_one_or_none.return_value = claim
        elif "FROM environment_snapshots" in str(stmt):
            mock_result.scalar_one_or_none.return_value = snapshot
        return mock_result

    mock_session.execute.side_effect = mock_execute

    # Propose condition with wrong expected hash (mismatch)
    params = EstablishConditionsParams(
        based_on_snapshot_id=snapshot.id,
        rationale="Testing mismatch detection",
        conditions=[
            ConditionSpec(
                condition_type="file_hash",
                target_path="config/redis.conf",
                comparator="hash_equals",
                expected_hash=HASH_B,  # Snapshot contains HASH_A
                is_critical=True,
            )
        ],
    )

    with pytest.raises(ConditionSnapshotMismatchError, match="CONTENT_HASH_MISMATCH"):
        await ConditionService.establish_initial_conditions(
            session=mock_session,
            context=context,
            claim_id=claim.id,
            params=params,
        )


@pytest.mark.asyncio
async def test_establish_conditions_rejects_cross_workspace_snapshot(test_setup: dict) -> None:
    """Verifies that an establishing snapshot from another workspace is rejected with WorkspaceMismatchError."""
    context = test_setup["context"]
    claim = test_setup["claim"]
    snapshot = test_setup["snapshot"]

    # Place snapshot in another workspace
    snapshot.workspace_id = uuid.uuid4()

    mock_session = AsyncMock(spec=AsyncSession)

    def mock_execute(stmt):
        mock_result = MagicMock()
        if "FROM claims" in str(stmt):
            mock_result.scalar_one_or_none.return_value = claim
        elif "FROM environment_snapshots" in str(stmt):
            mock_result.scalar_one_or_none.return_value = snapshot
        return mock_result

    mock_session.execute.side_effect = mock_execute

    params = EstablishConditionsParams(
        based_on_snapshot_id=snapshot.id,
        rationale="Cross-workspace snapshot test",
        conditions=[
            ConditionSpec(
                condition_type="file_hash",
                target_path="config/redis.conf",
                comparator="hash_equals",
                expected_hash=HASH_A,
                is_critical=True,
            )
        ],
    )

    with pytest.raises(WorkspaceMismatchError, match="another workspace"):
        await ConditionService.establish_initial_conditions(
            session=mock_session,
            context=context,
            claim_id=claim.id,
            params=params,
        )


# =============================================================================
# 3. HTTP Integration Route Tests (POST /api/v1/claims/{id}/conditions)
# =============================================================================

@pytest.fixture
def auth_agent() -> tuple[str, Agent]:
    """Fixture providing a valid agent and raw bearer secret."""
    raw_secret = "fil_live_condition_route_key_123"
    agent = Agent(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        name="condition-agent",
        api_key_hash=hash_api_key(raw_secret),
        is_active=True,
    )
    return raw_secret, agent


@pytest.mark.asyncio
async def test_establish_conditions_route_success(
    app: FastAPI,
    async_client: AsyncClient,
    auth_agent: tuple[str, Agent],
) -> None:
    """Verifies that POST /api/v1/claims/{id}/conditions returns HTTP 201 with condition set."""
    secret, agent = auth_agent
    claim_id = uuid.uuid4()
    snapshot_id = uuid.uuid4()

    claim = Claim(
        id=claim_id,
        workspace_id=agent.workspace_id,
        agent_id=agent.id,
        claim_type="fact",
        subject="redis",
        predicate="cluster_mode",
        object_value={"enabled": True},
        raw_statement="Redis cluster mode is enabled.",
        scope="workspace",
        status="current",
        confidence=Decimal("1.00"),
        version=1,
        active_condition_version=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    snapshot = EnvironmentSnapshot(
        id=snapshot_id,
        workspace_id=agent.workspace_id,
        collected_by_agent=agent.id,
        source_type="agent_client",
        verification_level="agent_reported",
        source_ref="git:commit_1",
        scan_scope="full_repository",
        snapshot_data={
            "scanned_roots": ["."],
            "files": {"config/redis.conf": HASH_A},
            "unreadable_paths": [],
            "packages": {"pypi:redis": "5.0.1"},
            "runtime": {"python": "3.12"},
        },
        created_at=datetime.now(timezone.utc),
    )

    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.is_active = True
    mock_session.scalar.return_value = agent

    def mock_execute(stmt):
        mock_result = MagicMock()
        if "FROM claims" in str(stmt):
            mock_result.scalar_one_or_none.return_value = claim
        elif "FROM environment_snapshots" in str(stmt):
            mock_result.scalar_one_or_none.return_value = snapshot
        return mock_result

    mock_session.execute.side_effect = mock_execute
    app.dependency_overrides[get_db] = lambda: mock_session

    payload = {
        "based_on_snapshot_id": str(snapshot_id),
        "rationale": "Validating redis configuration",
        "conditions": [
            {
                "condition_type": "file_hash",
                "target_path": "config/redis.conf",
                "comparator": "hash_equals",
                "expected_hash": HASH_A,
                "is_critical": True,
            }
        ],
    }

    response = await async_client.post(
        f"/api/v1/claims/{claim_id}/conditions",
        json=payload,
        headers={"Authorization": f"Bearer {secret}"},
    )

    assert response.status_code == 201, response.text
    data = response.json()
    assert data["claim_id"] == str(claim_id)
    assert data["version"] == 1
    assert data["based_on_snapshot_id"] == str(snapshot_id)
    assert len(data["conditions"]) == 1
    assert data["conditions"][0]["target_path"] == "config/redis.conf"
    mock_session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_establish_conditions_route_409_conflict_when_conditioned(
    app: FastAPI,
    async_client: AsyncClient,
    auth_agent: tuple[str, Agent],
) -> None:
    """Verifies that establishing conditions on an already conditioned claim returns HTTP 409."""
    secret, agent = auth_agent
    claim_id = uuid.uuid4()
    snapshot_id = uuid.uuid4()

    claim = Claim(
        id=claim_id,
        workspace_id=agent.workspace_id,
        agent_id=agent.id,
        claim_type="fact",
        subject="redis",
        predicate="cluster_mode",
        object_value={"enabled": True},
        raw_statement="Redis cluster mode is enabled.",
        scope="workspace",
        status="current",
        confidence=Decimal("1.00"),
        version=1,
        active_condition_version=1,  # Already conditioned!
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.is_active = True
    mock_session.scalar.return_value = agent

    def mock_execute(stmt):
        mock_result = MagicMock()
        if "FROM claims" in str(stmt):
            mock_result.scalar_one_or_none.return_value = claim
        return mock_result

    mock_session.execute.side_effect = mock_execute
    app.dependency_overrides[get_db] = lambda: mock_session

    payload = {
        "based_on_snapshot_id": str(snapshot_id),
        "rationale": "Attempting second establishment",
        "conditions": [
            {
                "condition_type": "file_hash",
                "target_path": "config/redis.conf",
                "comparator": "hash_equals",
                "expected_hash": HASH_A,
                "is_critical": True,
            }
        ],
    }

    response = await async_client.post(
        f"/api/v1/claims/{claim_id}/conditions",
        json=payload,
        headers={"Authorization": f"Bearer {secret}"},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CONDITIONS_ALREADY_ESTABLISHED"
    mock_session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_establish_conditions_route_422_snapshot_mismatch(
    app: FastAPI,
    async_client: AsyncClient,
    auth_agent: tuple[str, Agent],
) -> None:
    """Verifies that an unsatisfied condition returns HTTP 422 with CONDITION_SNAPSHOT_MISMATCH."""
    secret, agent = auth_agent
    claim_id = uuid.uuid4()
    snapshot_id = uuid.uuid4()

    claim = Claim(
        id=claim_id,
        workspace_id=agent.workspace_id,
        agent_id=agent.id,
        claim_type="fact",
        subject="redis",
        predicate="cluster_mode",
        object_value={"enabled": True},
        raw_statement="Redis cluster mode is enabled.",
        scope="workspace",
        status="current",
        confidence=Decimal("1.00"),
        version=1,
        active_condition_version=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    snapshot = EnvironmentSnapshot(
        id=snapshot_id,
        workspace_id=agent.workspace_id,
        collected_by_agent=agent.id,
        source_type="agent_client",
        verification_level="agent_reported",
        source_ref="git:commit_1",
        scan_scope="full_repository",
        snapshot_data={
            "scanned_roots": ["."],
            "files": {"config/redis.conf": HASH_A},
            "unreadable_paths": [],
            "packages": {},
            "runtime": {},
        },
        created_at=datetime.now(timezone.utc),
    )

    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.is_active = True
    mock_session.scalar.return_value = agent

    def mock_execute(stmt):
        mock_result = MagicMock()
        if "FROM claims" in str(stmt):
            mock_result.scalar_one_or_none.return_value = claim
        elif "FROM environment_snapshots" in str(stmt):
            mock_result.scalar_one_or_none.return_value = snapshot
        return mock_result

    mock_session.execute.side_effect = mock_execute
    app.dependency_overrides[get_db] = lambda: mock_session

    payload = {
        "based_on_snapshot_id": str(snapshot_id),
        "rationale": "Condition mismatch test",
        "conditions": [
            {
                "condition_type": "file_hash",
                "target_path": "config/redis.conf",
                "comparator": "hash_equals",
                "expected_hash": HASH_B,  # Doesn't match snapshot's HASH_A
                "is_critical": True,
            }
        ],
    }

    response = await async_client.post(
        f"/api/v1/claims/{claim_id}/conditions",
        json=payload,
        headers={"Authorization": f"Bearer {secret}"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "CONDITION_SNAPSHOT_MISMATCH"
    mock_session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_establish_conditions_route_422_on_invalid_hash_or_package(
    app: FastAPI,
    async_client: AsyncClient,
    auth_agent: tuple[str, Agent],
) -> None:
    """Verifies that route validation rejects missing hash and unnamespaced package identifiers with HTTP 422."""
    secret, agent = auth_agent
    claim_id = uuid.uuid4()
    snapshot_id = uuid.uuid4()

    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.is_active = True
    mock_session.scalar.return_value = agent
    app.dependency_overrides[get_db] = lambda: mock_session

    # Case 1: file_hash missing hash in payload
    payload_missing_hash = {
        "based_on_snapshot_id": str(snapshot_id),
        "rationale": "Testing missing hash",
        "conditions": [
            {
                "condition_type": "file_hash",
                "target_path": "src/main.py",
                "comparator": "hash_equals",
            }
        ],
    }
    resp1 = await async_client.post(
        f"/api/v1/claims/{claim_id}/conditions",
        json=payload_missing_hash,
        headers={"Authorization": f"Bearer {secret}"},
    )
    assert resp1.status_code == 422

    # Case 2: package_version missing ecosystem namespace
    payload_bad_pkg = {
        "based_on_snapshot_id": str(snapshot_id),
        "rationale": "Testing bad package identifier",
        "conditions": [
            {
                "condition_type": "package_version",
                "target_path": "redis",  # Missing pypi: prefix
                "comparator": "version_equals",
                "expected_value": {"version": "5.0.1"},
            }
        ],
    }
    resp2 = await async_client.post(
        f"/api/v1/claims/{claim_id}/conditions",
        json=payload_bad_pkg,
        headers={"Authorization": f"Bearer {secret}"},
    )
    assert resp2.status_code == 422

