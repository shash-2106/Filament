"""Agent domain model representing autonomous software agents."""

from datetime import datetime
import uuid
from typing import TYPE_CHECKING, List

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from filament_api.db.base import Base

if TYPE_CHECKING:
    from filament_api.models.workspace import Workspace
    from filament_api.models.claim import Claim


class Agent(Base):
    """Registered autonomous agent in a workspace with explicit scoping defaults."""

    __tablename__ = "agents"
    __table_args__ = (
        CheckConstraint(
            "default_scope IN ('private', 'team', 'workspace')",
            name="ck_agents_default_scope",
        ),
        UniqueConstraint("workspace_id", "name", name="uq_agents_workspace_name"),
        UniqueConstraint("workspace_id", "id", name="uq_agents_workspace_id"),
        UniqueConstraint("api_key_hash", name="uq_agents_api_key_hash"),
        Index("idx_agents_workspace", "workspace_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    api_key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    system_prompt_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    default_scope: Mapped[str] = mapped_column(String(32), nullable=False, default="private")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    workspace: Mapped["Workspace"] = relationship("Workspace", back_populates="agents")
    claims: Mapped[List["Claim"]] = relationship(
        "Claim",
        back_populates="agent",
        cascade="all, delete-orphan",
    )

