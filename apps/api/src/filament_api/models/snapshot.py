"""EnvironmentSnapshot domain model representing immutable environment state captures."""

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List
import uuid

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from filament_api.db.base import Base

if TYPE_CHECKING:
    from filament_api.models.agent import Agent
    from filament_api.models.condition import ClaimConditionSet, ClaimVerification
    from filament_api.models.workspace import Workspace


class EnvironmentSnapshot(Base):
    """Immutable environment snapshot capturing file digests, package versions, and runtime facts."""

    __tablename__ = "environment_snapshots"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_env_snapshots_workspace_id"),
        CheckConstraint(
            "source_type IN ('agent_client', 'ci_webhook', 'mcp_adapter')",
            name="ck_env_snapshots_source_type",
        ),
        CheckConstraint(
            "verification_level IN ('agent_reported', 'independently_verified')",
            name="ck_env_snapshots_verification_level",
        ),
        CheckConstraint(
            "scan_scope IN ('full_repository', 'selective')",
            name="ck_env_snapshots_scan_scope",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "collected_by_agent"],
            ["agents.workspace_id", "agents.id"],
            ondelete="RESTRICT",
            name="fk_env_snapshots_agent",
        ),
        Index("idx_env_snapshots_lookup", "workspace_id", "source_ref", "created_at"),
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
    collected_by_agent: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )
    source_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="agent_client",
    )
    verification_level: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="agent_reported",
    )
    source_ref: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )
    scan_scope: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="full_repository",
    )
    snapshot_data: Mapped[Dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    workspace: Mapped["Workspace"] = relationship("Workspace", overlaps="collector")
    collector: Mapped["Agent"] = relationship(
        "Agent",
        primaryjoin="and_(EnvironmentSnapshot.workspace_id == Agent.workspace_id, EnvironmentSnapshot.collected_by_agent == Agent.id)",
        foreign_keys="[EnvironmentSnapshot.workspace_id, EnvironmentSnapshot.collected_by_agent]",
        overlaps="workspace",
    )
    condition_sets: Mapped[List["ClaimConditionSet"]] = relationship(
        "ClaimConditionSet",
        primaryjoin="and_(EnvironmentSnapshot.workspace_id == ClaimConditionSet.workspace_id, EnvironmentSnapshot.id == ClaimConditionSet.based_on_snapshot_id)",
        foreign_keys="[ClaimConditionSet.workspace_id, ClaimConditionSet.based_on_snapshot_id]",
        back_populates="based_on_snapshot",
        overlaps="based_on_snapshot,claim,condition_sets,established_by,workspace",
    )
    verifications: Mapped[List["ClaimVerification"]] = relationship(
        "ClaimVerification",
        primaryjoin="and_(EnvironmentSnapshot.workspace_id == ClaimVerification.workspace_id, EnvironmentSnapshot.id == ClaimVerification.snapshot_id)",
        foreign_keys="[ClaimVerification.workspace_id, ClaimVerification.snapshot_id]",
        back_populates="snapshot",
        overlaps="condition_set,snapshot,verifications,verifier",
    )
