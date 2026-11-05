"""Audit API route handlers."""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from filament_api.api.dependencies.auth import get_current_agent_context
from filament_api.core import log_safe_exception
from filament_api.db.session import get_db
from filament_api.models.audit import AuditEvent
from filament_api.schemas.audit import AuditEventResponse
from filament_api.services.context import TrustedContext

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/audit",
    response_model=List[AuditEventResponse],
    status_code=status.HTTP_200_OK,
    summary="List Workspace Audit Events",
    description="Returns the append-only stream of governance transitions and mutations for the authenticated workspace.",
)
async def list_audit_events(
    event_type: Optional[str] = Query(default=None, description="Filter by event type"),
    limit: int = Query(default=50, ge=1, le=200, description="Page limit"),
    offset: int = Query(default=0, ge=0, description="Page offset"),
    context: TrustedContext = Depends(get_current_agent_context),
    session: AsyncSession = Depends(get_db),
) -> List[AuditEventResponse]:
    """Retrieve immutable audit events for the caller's workspace."""
    try:
        stmt = (
            select(AuditEvent)
            .where(AuditEvent.workspace_id == context.workspace_id)
        )
        if event_type:
            stmt = stmt.where(AuditEvent.event_type == event_type)

        stmt = stmt.order_by(AuditEvent.created_at.desc()).limit(limit).offset(offset)

        res = await session.execute(stmt)
        events = res.scalars().all()
        return [AuditEventResponse.model_validate(e) for e in events]
    except Exception as exc:
        log_safe_exception(logger, f"Error listing audit events for workspace {context.workspace_id}", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": {"code": "INTERNAL_SERVER_ERROR", "message": "An internal error occurred."}},
        ) from exc
