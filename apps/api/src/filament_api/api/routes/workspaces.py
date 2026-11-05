"""Workspace and Agent API routes."""

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from filament_api.api.dependencies.auth import get_current_agent_context
from filament_api.core import log_safe_exception
from filament_api.db.session import get_db
from filament_api.models.agent import Agent
from filament_api.models.workspace import Workspace
from filament_api.schemas.workspace import AgentResponse, WorkspaceDetailResponse
from filament_api.services.context import TrustedContext

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/workspaces/current",
    response_model=WorkspaceDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Current Workspace",
    description="Returns workspace identity and authenticated agent profile for the current tenant context.",
)
async def get_current_workspace(
    context: TrustedContext = Depends(get_current_agent_context),
    session: AsyncSession = Depends(get_db),
) -> WorkspaceDetailResponse:
    """Retrieve workspace and agent profile for the authenticated caller."""
    try:
        # Load workspace
        ws_stmt = select(Workspace).where(Workspace.id == context.workspace_id)
        ws = await session.scalar(ws_stmt)
        if ws is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": {"code": "NOT_FOUND", "message": "Workspace not found."}},
            )

        # Load current agent
        agent_stmt = select(Agent).where(
            Agent.workspace_id == context.workspace_id,
            Agent.id == context.actor_id,
        )
        agent = await session.scalar(agent_stmt)
        if agent is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": {"code": "NOT_FOUND", "message": "Agent not found."}},
            )

        return WorkspaceDetailResponse(
            id=ws.id,
            name=ws.name,
            slug=ws.slug,
            created_at=ws.created_at,
            updated_at=ws.updated_at,
            current_agent=AgentResponse.model_validate(agent),
        )
    except HTTPException:
        raise
    except Exception as exc:
        log_safe_exception(logger, f"Error retrieving current workspace for {context.workspace_id}", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": {"code": "INTERNAL_SERVER_ERROR", "message": "An internal error occurred."}},
        ) from exc


@router.get(
    "/agents",
    response_model=List[AgentResponse],
    status_code=status.HTTP_200_OK,
    summary="List Workspace Agents",
    description="Lists registered agents within the caller's workspace.",
)
async def list_agents(
    context: TrustedContext = Depends(get_current_agent_context),
    session: AsyncSession = Depends(get_db),
) -> List[AgentResponse]:
    """List agents in the current workspace."""
    try:
        stmt = (
            select(Agent)
            .where(Agent.workspace_id == context.workspace_id)
            .order_by(Agent.name.asc())
        )
        res = await session.execute(stmt)
        agents = res.scalars().all()
        return [AgentResponse.model_validate(a) for a in agents]
    except Exception as exc:
        log_safe_exception(logger, f"Error listing agents for workspace {context.workspace_id}", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": {"code": "INTERNAL_SERVER_ERROR", "message": "An internal error occurred."}},
        ) from exc
