"""Pydantic schemas and DTOs for workspace and agent operations."""

from datetime import datetime
from typing import List, Literal, Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field

AgentScope = Literal["private", "team", "workspace"]


class AgentResponse(BaseModel):
    """Public representation of a registered agent."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    default_scope: AgentScope
    is_active: bool
    created_at: datetime
    updated_at: datetime


class WorkspaceDetailResponse(BaseModel):
    """Detailed summary of the authenticated agent's workspace and environment."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    created_at: datetime
    updated_at: datetime
    current_agent: AgentResponse
