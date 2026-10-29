"""ClaimRelation domain model capturing directed causal and lineage edges."""

from datetime import datetime
from typing import TYPE_CHECKING
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
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from filament_api.db.base import Base

if TYPE_CHECKING:
    from filament_api.models.agent import Agent
    from filament_api.models.claim import Claim
    from filament_api.models.workspace import Workspace


class ClaimRelation(Base):
    """Directed edge representing supersession, dependency, or contradiction between claims."""

    __tablename__ = "claim_relations"
    __table_args__ = (
        CheckConstraint(
            "source_claim_id <> target_claim_id",
            name="ck_claim_relations_no_self_loops",
        ),
        CheckConstraint(
            "relation_type IN ('supersedes', 'depends_on', 'contradicts', 'corroborates')",
            name="ck_claim_relations_relation_type",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "source_claim_id"],
            ["claims.workspace_id", "claims.id"],
            ondelete="RESTRICT",
            name="fk_claim_relations_source_claim",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "target_claim_id"],
            ["claims.workspace_id", "claims.id"],
            ondelete="RESTRICT",
            name="fk_claim_relations_target_claim",
        ),
        UniqueConstraint(
            "source_claim_id",
            "target_claim_id",
            "relation_type",
            name="uq_claim_relation_edge",
        ),
        Index("idx_claim_relations_target", "target_claim_id", "relation_type"),
        Index("idx_claim_relations_workspace", "workspace_id"),
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
    source_claim_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )
    target_claim_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )
    relation_type: Mapped[str] = mapped_column(String(32), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    created_by_agent: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agents.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    workspace: Mapped["Workspace"] = relationship("Workspace", back_populates="claim_relations")
    source_claim: Mapped["Claim"] = relationship(
        "Claim",
        foreign_keys=[source_claim_id],
        back_populates="outgoing_relations",
    )
    target_claim: Mapped["Claim"] = relationship(
        "Claim",
        foreign_keys=[target_claim_id],
        back_populates="incoming_relations",
    )
    creator_agent: Mapped["Agent | None"] = relationship("Agent")

