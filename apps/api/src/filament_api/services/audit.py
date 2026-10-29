"""Internal audit service helper for atomic governance event recording."""

from typing import Any, Dict, Optional
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from filament_api.models.audit import AuditEvent
from filament_api.services.context import TrustedContext


async def record_audit_event(
    session: AsyncSession,
    context: TrustedContext,
    *,
    event_type: str,
    target_type: str,
    target_id: uuid.UUID,
    payload: Dict[str, Any],
    idempotency_key: Optional[str] = None,
    event_id: Optional[uuid.UUID] = None,
) -> AuditEvent:
    """Stage an immutable audit event in the active transactional session.

    This operation does NOT commit the session; it stages the event to ensure
    atomic persistence alongside domain entity modifications.
    """
    event = AuditEvent(
        id=event_id or uuid.uuid4(),
        workspace_id=context.workspace_id,
        actor_type=context.actor_type,
        actor_id=context.actor_id,
        event_type=event_type,
        target_type=target_type,
        target_id=target_id,
        idempotency_key=idempotency_key,
        payload=payload,
    )
    session.add(event)
    return event

