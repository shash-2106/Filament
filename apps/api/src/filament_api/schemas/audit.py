"""Pydantic schemas and DTOs for audit event queries."""

from datetime import datetime
from typing import Any, Dict, Literal, Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field

ActorType = Literal["agent", "user", "system"]


class AuditEventResponse(BaseModel):
    """API response schema for an immutable audit trail entry."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    actor_type: ActorType
    actor_id: uuid.UUID
    event_type: str
    target_type: str
    target_id: uuid.UUID
    idempotency_key: Optional[str] = None
    payload: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
