"""Evidence domain model representing immutable source observation snapshots."""

from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List
import uuid

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from filament_api.db.base import Base

if TYPE_CHECKING:
    from filament_api.models.agent import Agent
    from filament_api.models.claim import ClaimEvidence
    from filament_api.models.user import User
    from filament_api.models.workspace import Workspace


class Evidence(Base):
    """Immutable evidence snapshot supporting or refuting claims."""

    __tablename__ = "evidence"
    __table_args__ = (
        CheckConstraint(
            "source_type IN ('file', 'git_commit', 'user_turn', 'tool_output', 'api_response')",
            name="ck_evidence_source_type",
        ),
        UniqueConstraint("workspace_id", "id", name="uq_evidence_workspace_id"),
        ForeignKeyConstraint(
            ["workspace_id", "collected_by_agent"],
            ["agents.workspace_id", "agents.id"],
            ondelete="SET NULL (collected_by_agent)",
            name="fk_evidence_agent",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "collected_by_user"],
            ["users.workspace_id", "users.id"],
            ondelete="SET NULL (collected_by_user)",
            name="fk_evidence_user",
        ),
        Index("idx_evidence_workspace", "workspace_id"),
        Index("idx_evidence_source_lookup", "workspace_id", "source_type", "content_hash"),
        Index("idx_evidence_metadata_gin", "metadata", postgresql_using="gin"),
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
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_uri: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_snippet: Mapped[str] = mapped_column(Text, nullable=False)
    collected_by_agent: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )
    collected_by_user: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )
    metadata_: Mapped[Dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    workspace: Mapped["Workspace"] = relationship("Workspace", back_populates="evidence")
    agent_collector: Mapped["Agent | None"] = relationship("Agent", overlaps="workspace")
    user_collector: Mapped["User | None"] = relationship("User", overlaps="agent_collector,workspace")
    claim_links: Mapped[List["ClaimEvidence"]] = relationship(
        "ClaimEvidence",
        back_populates="evidence",
        cascade="all, delete-orphan",
        overlaps="claim,evidence_links",
    )

