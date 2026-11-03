"""Automated HTTP and service tests for snapshot ingestion (POST /api/v1/snapshots)."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock
import uuid

from fastapi import FastAPI
from httpx import AsyncClient
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from filament_api.api.dependencies.auth import get_current_agent_context
from filament_api.core.security import hash_api_key
from filament_api.db.session import get_db
from filament_api.models.agent import Agent
from filament_api.models.snapshot import EnvironmentSnapshot
from filament_api.schemas.snapshot import RecordSnapshotParams, SnapshotData
from filament_api.services.context import TrustedContext
from filament_api.services.exceptions import UnauthorizedActorError, ValidationDomainError
from filament_api.services.snapshot import SnapshotService


@pytest.fixture
def auth_agent() -> tuple[str, Agent]:
    """Fixture providing a valid agent and raw bearer secret."""
    raw_secret = "fil_live_snapshot_test_key_123"
    agent = Agent(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        name="snapshot-collector",
        api_key_hash=hash_api_key(raw_secret),
        is_active=True,
    )
    return raw_secret, agent


VALID_HASH_1 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
VALID_HASH_2 = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


@pytest.mark.asyncio
async def test_record_snapshot_success_route(
    app: FastAPI,
    async_client: AsyncClient,
    auth_agent: tuple[str, Agent],
) -> None:
    """Verifies that authenticated POST /api/v1/snapshots returns 201 with expected response fields."""
    secret, agent = auth_agent

    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.scalar.return_value = agent
    mock_session.is_active = True

    app.dependency_overrides[get_db] = lambda: mock_session

    payload = {
        "source_ref": "git:main:commit_abc123",
        "source_type": "agent_client",
        "scan_scope": "full_repository",
        "snapshot_data": {
            "scanned_roots": ["."],
            "files": {
                "config/redis.conf": VALID_HASH_1,
                "poetry.lock": VALID_HASH_2,
            },
            "unreadable_paths": [],
            "packages": {
                "pypi:redis": "5.0.1",
            },
            "runtime": {
                "python": "3.12",
            },
        },
    }

    response = await async_client.post(
        "/api/v1/snapshots",
        json=payload,
        headers={"Authorization": f"Bearer {secret}"},
    )

    assert response.status_code == 201, response.text
    data = response.json()
    assert "id" in data
    assert data["workspace_id"] == str(agent.workspace_id)
    assert data["collected_by_agent"] == str(agent.id)
    assert data["source_ref"] == "git:main:commit_abc123"
    assert data["source_type"] == "agent_client"
    assert data["verification_level"] == "agent_reported"
    assert data["scan_scope"] == "full_repository"
    assert data["snapshot_data"]["files"]["config/redis.conf"] == VALID_HASH_1
    assert data["snapshot_data"]["packages"]["pypi:redis"] == "5.0.1"

    # Confirms session was committed
    mock_session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_record_snapshot_self_promotion_rejected(
    app: FastAPI,
    async_client: AsyncClient,
    auth_agent: tuple[str, Agent],
) -> None:
    """Verifies that an agent_client cannot declare independently_verified provenance."""
    secret, agent = auth_agent

    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.scalar.return_value = agent
    mock_session.is_active = True

    app.dependency_overrides[get_db] = lambda: mock_session

    payload = {
        "source_ref": "commit_123",
        "source_type": "agent_client",
        "verification_level": "independently_verified",
        "scan_scope": "full_repository",
        "snapshot_data": {
            "scanned_roots": ["."],
            "files": {"src/app.py": VALID_HASH_1},
        },
    }

    response = await async_client.post(
        "/api/v1/snapshots",
        json=payload,
        headers={"Authorization": f"Bearer {secret}"},
    )

    assert response.status_code == 422
    assert "independently_verified" in response.json()["error"]["message"]
    mock_session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_record_snapshot_rejects_file_unreadable_overlap(
    app: FastAPI,
    async_client: AsyncClient,
    auth_agent: tuple[str, Agent],
) -> None:
    """Verifies that a path cannot appear in both files and unreadable_paths."""
    secret, agent = auth_agent

    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.scalar.return_value = agent
    mock_session.is_active = True

    app.dependency_overrides[get_db] = lambda: mock_session

    payload = {
        "source_ref": "commit_123",
        "snapshot_data": {
            "scanned_roots": ["."],
            "files": {"src/app.py": VALID_HASH_1},
            "unreadable_paths": ["src/app.py"],
        },
    }

    response = await async_client.post(
        "/api/v1/snapshots",
        json=payload,
        headers={"Authorization": f"Bearer {secret}"},
    )

    assert response.status_code == 422
    assert "internally inconsistent" in response.json()["error"]["message"]


@pytest.mark.asyncio
async def test_record_snapshot_scope_rules() -> None:
    """Verifies that full_repository requires '.' in scanned_roots and selective requires roots."""
    mock_session = AsyncMock(spec=AsyncSession)
    context = TrustedContext(workspace_id=uuid.uuid4(), actor_type="agent", actor_id=uuid.uuid4())

    # Full repo missing '.'
    with pytest.raises(ValidationDomainError, match="requires repository root marker '.'"):
        params = RecordSnapshotParams(
            source_ref="ref1",
            scan_scope="full_repository",
            snapshot_data=SnapshotData(scanned_roots=["src"], files={}),
        )
        await SnapshotService.record_snapshot(mock_session, context, params)

    # Selective scan with valid relative root
    params_selective = RecordSnapshotParams(
        source_ref="ref2",
        scan_scope="selective",
        snapshot_data=SnapshotData(scanned_roots=["src", "config"], files={"src/app.py": VALID_HASH_1}),
    )
    snap = await SnapshotService.record_snapshot(mock_session, context, params_selective)
    assert snap.scan_scope == "selective"
    assert snap.snapshot_data["scanned_roots"] == ["src", "config"]


@pytest.mark.asyncio
async def test_record_snapshot_rejects_non_agent_actor() -> None:
    """Verifies that non-agent callers (e.g. users) cannot submit environment snapshots."""
    mock_session = AsyncMock(spec=AsyncSession)
    user_context = TrustedContext(workspace_id=uuid.uuid4(), actor_type="user", actor_id=uuid.uuid4())

    params = RecordSnapshotParams(
        source_ref="ref1",
        scan_scope="full_repository",
        snapshot_data=SnapshotData(scanned_roots=["."], files={}),
    )
    with pytest.raises(UnauthorizedActorError, match="authorized agent"):
        await SnapshotService.record_snapshot(mock_session, user_context, params)


@pytest.mark.asyncio
async def test_record_snapshot_rejects_invalid_path_in_files(
    app: FastAPI,
    async_client: AsyncClient,
    auth_agent: tuple[str, Agent],
) -> None:
    """Verifies that absolute paths or traversal paths in snapshot files are rejected with HTTP 422."""
    secret, agent = auth_agent

    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.scalar.return_value = agent
    app.dependency_overrides[get_db] = lambda: mock_session

    payload = {
        "source_ref": "commit_123",
        "snapshot_data": {
            "scanned_roots": ["."],
            "files": {"/etc/passwd": VALID_HASH_1},
        },
    }

    response = await async_client.post(
        "/api/v1/snapshots",
        json=payload,
        headers={"Authorization": f"Bearer {secret}"},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_record_snapshot_requires_auth(
    async_client: AsyncClient,
) -> None:
    """Verifies that missing auth header returns HTTP 401."""
    response = await async_client.post(
        "/api/v1/snapshots",
        json={"source_ref": "commit_123", "snapshot_data": {"scanned_roots": ["."]}},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_record_snapshot_with_inventory_scopes(
    app: FastAPI,
    async_client: AsyncClient,
    auth_agent: tuple[str, Agent],
) -> None:
    """Verifies that packages_scope and runtime_scope are accepted, persisted, and defaulted to partial."""
    secret, agent = auth_agent

    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.scalar.return_value = agent
    app.dependency_overrides[get_db] = lambda: mock_session

    # Case 1: Explicit complete scopes
    payload = {
        "source_ref": "commit_scopes",
        "snapshot_data": {
            "scanned_roots": ["."],
            "packages_scope": "complete",
            "runtime_scope": "complete",
            "packages": {"pypi:flask": "3.0.0"},
            "runtime": {"python": "3.12"},
        },
    }

    response = await async_client.post(
        "/api/v1/snapshots",
        json=payload,
        headers={"Authorization": f"Bearer {secret}"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["snapshot_data"]["packages_scope"] == "complete"
    assert data["snapshot_data"]["runtime_scope"] == "complete"

    # Case 2: Defaults to partial when omitted
    payload_default = {
        "source_ref": "commit_default",
        "snapshot_data": {
            "scanned_roots": ["."],
            "packages": {"pypi:flask": "3.0.0"},
        },
    }
    response2 = await async_client.post(
        "/api/v1/snapshots",
        json=payload_default,
        headers={"Authorization": f"Bearer {secret}"},
    )
    assert response2.status_code == 201
    data2 = response2.json()
    assert data2["snapshot_data"]["packages_scope"] == "partial"
    assert data2["snapshot_data"]["runtime_scope"] == "partial"


@pytest.mark.asyncio
async def test_record_snapshot_rejects_invalid_package_key(
    app: FastAPI,
    async_client: AsyncClient,
    auth_agent: tuple[str, Agent],
) -> None:
    """Verifies that package identifiers without ecosystem prefix are rejected with HTTP 422."""
    secret, agent = auth_agent

    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.scalar.return_value = agent
    app.dependency_overrides[get_db] = lambda: mock_session

    payload = {
        "source_ref": "commit_pkg_err",
        "snapshot_data": {
            "scanned_roots": ["."],
            "packages": {"flask": "3.0.0"},  # Missing ecosystem namespace
        },
    }

    response = await async_client.post(
        "/api/v1/snapshots",
        json=payload,
        headers={"Authorization": f"Bearer {secret}"},
    )
    assert response.status_code == 422

