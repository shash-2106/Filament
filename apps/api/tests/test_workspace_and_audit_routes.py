"""Tests for workspace, agent, and audit HTTP API routes."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
import uuid
from fastapi import FastAPI
import pytest
from httpx import AsyncClient

from filament_api.models.agent import Agent
from filament_api.models.audit import AuditEvent
from filament_api.models.workspace import Workspace
from filament_api.core.security import hash_api_key
from filament_api.db.session import get_db


@pytest.fixture
def auth_agent() -> tuple[str, Agent]:
    raw_key = "fil_live_test_workspace_key_abc123"
    agent = Agent(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        name="Workspace Auditor Agent",
        default_scope="team",
        is_active=True,
        api_key_hash=hash_api_key(raw_key),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    return raw_key, agent


@pytest.mark.asyncio
async def test_get_current_workspace_and_agents(
    app: FastAPI,
    async_client: AsyncClient,
    auth_agent: tuple[str, Agent],
):
    raw_key, agent = auth_agent
    mock_ws = Workspace(
        id=agent.workspace_id,
        name="Test Governance Lab",
        slug="test-gov-lab",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    mock_session = AsyncMock()
    mock_session.scalar.side_effect = [agent, mock_ws, agent]
    mock_session.is_active = True

    app.dependency_overrides[get_db] = lambda: mock_session

    try:
        # 1. Unauthenticated -> 401
        res = await async_client.get("/api/v1/workspaces/current")
        assert res.status_code == 401

        # 2. Authenticated -> 200
        headers = {"Authorization": f"Bearer {raw_key}"}
        res = await async_client.get("/api/v1/workspaces/current", headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert data["id"] == str(agent.workspace_id)
        assert data["name"] == "Test Governance Lab"
        assert data["current_agent"]["id"] == str(agent.id)

    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_list_agents_and_audit(
    app: FastAPI,
    async_client: AsyncClient,
    auth_agent: tuple[str, Agent],
):
    raw_key, agent = auth_agent

    mock_audit = AuditEvent(
        id=uuid.uuid4(),
        workspace_id=agent.workspace_id,
        actor_type="agent",
        actor_id=agent.id,
        event_type="TEST_ACTION",
        target_type="claim",
        target_id=uuid.uuid4(),
        payload={"action": "reverify"},
        created_at=datetime.now(timezone.utc),
    )

    # We mock execute by inspecting statement or returning custom mock
    class MockSession(AsyncMock):
        async def scalar(self, stmt):
            return agent

        async def execute(self, stmt):
            m = MagicMock()
            sql_str = str(stmt).upper()
            if "AGENTS" in sql_str:
                m.scalars.return_value.all.return_value = [agent]
            elif "AUDIT_EVENTS" in sql_str:
                m.scalars.return_value.all.return_value = [mock_audit]
            else:
                m.scalars.return_value.all.return_value = []
                m.first.return_value = None
            return m

    mock_sess = MockSession()
    mock_sess.is_active = True
    app.dependency_overrides[get_db] = lambda: mock_sess

    try:
        headers = {"Authorization": f"Bearer {raw_key}"}

        # List agents
        res = await async_client.get("/api/v1/agents", headers=headers)
        assert res.status_code == 200
        agents_list = res.json()
        assert len(agents_list) == 1
        assert agents_list[0]["name"] == agent.name

        # List audit events
        res = await async_client.get("/api/v1/audit", headers=headers)
        assert res.status_code == 200
        audit_list = res.json()
        assert len(audit_list) == 1
        assert audit_list[0]["event_type"] == "TEST_ACTION"

    finally:
        app.dependency_overrides.clear()
