"""Claim and ClaimEvidence domain models for memory assertions and provenance."""

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Dict, List
import uuid

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from filament_api.db.base import Base

if TYPE_CHECKING:
    from filament_api.models.agent import Agent
    from filament_api.models.evidence import Evidence
    from filament_api.models.relation import ClaimRelation
    from filament_api.models.workspace import Workspace


class Claim(Base):
    """Atomic memory proposition, observation, or derived recommendation."""

    __tablename__ = "claims"
    __table_args__ = (
        CheckConstraint(
            "claim_type IN ('fact', 'recommendation', 'decision', 'preference', 'constraint')",
            name="ck_claims_claim_type",
        ),
        CheckConstraint(
            "scope IN ('private', 'team', 'workspace')",
            name="ck_claims_scope",
        ),
        CheckConstraint(
            "status IN ('current', 'superseded', 'disputed', 'needs_review', 'retracted')",
            name="ck_claims_status",
        ),
        CheckConstraint(
            "confidence >= 0.00 AND confidence <= 1.00",
            name="ck_claims_confidence",
        ),
        UniqueConstraint("workspace_id", "id", name="uq_claims_workspace_id"),
        ForeignKeyConstraint(
            ["workspace_id", "agent_id"],
            ["agents.workspace_id", "agents.id"],
            ondelete="RESTRICT",
            name="fk_claims_agent",
        ),
        Index("idx_claims_query_active", "workspace_id", "scope", "status", "subject"),
        Index("idx_claims_agent_scope", "workspace_id", "agent_id", "scope"),
        Index("idx_claims_status", "status"),
        Index("idx_claims_object_gin", "object_value", postgresql_using="gin"),
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
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )
    claim_type: Mapped[str] = mapped_column(String(32), nullable=False)
    subject: Mapped[str] = mapped_column(String(128), nullable=False)
    predicate: Mapped[str] = mapped_column(String(64), nullable=False)
    object_value: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False)
    raw_statement: Mapped[str] = mapped_column(Text, nullable=False)
    scope: Mapped[str] = mapped_column(String(32), nullable=False, default="private")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="current")
    confidence: Mapped[Decimal] = mapped_column(
        Numeric(3, 2),
        nullable=False,
        default=Decimal("1.00"),
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
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
    workspace: Mapped["Workspace"] = relationship("Workspace", back_populates="claims", overlaps="claims")
    agent: Mapped["Agent"] = relationship("Agent", back_populates="claims", overlaps="workspace,claims")
    evidence_links: Mapped[List["ClaimEvidence"]] = relationship(
        "ClaimEvidence",
        back_populates="claim",
        cascade="all, delete-orphan",
    )
    outgoing_relations: Mapped[List["ClaimRelation"]] = relationship(
        "ClaimRelation",
        primaryjoin="Claim.id == ClaimRelation.source_claim_id",
        back_populates="source_claim",
        cascade="all, delete-orphan",
    )
    incoming_relations: Mapped[List["ClaimRelation"]] = relationship(
        "ClaimRelation",
        primaryjoin="Claim.id == ClaimRelation.target_claim_id",
        back_populates="target_claim",
        cascade="all, delete-orphan",
    )


class ClaimEvidence(Base):
    """Many-to-many junction binding claims to supporting or refuting evidence."""

    __tablename__ = "claim_evidence"
    __table_args__ = (
        CheckConstraint(
            "support_type IN ('supports', 'refutes', 'mentions')",
            name="ck_claim_evidence_support_type",
        ),
        CheckConstraint(
            "confidence_weight >= 0.00 AND confidence_weight <= 1.00",
            name="ck_claim_evidence_confidence_weight",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "claim_id"],
            ["claims.workspace_id", "claims.id"],
            ondelete="CASCADE",
            name="fk_claim_evidence_claim",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "evidence_id"],
            ["evidence.workspace_id", "evidence.id"],
            ondelete="RESTRICT",
            name="fk_claim_evidence_evidence",
        ),
        Index("idx_claim_evidence_reverse", "evidence_id", "claim_id"),
        Index("idx_claim_evidence_workspace", "workspace_id"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    claim_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
    )
    evidence_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
    )
    support_type: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="supports",
    )
    extraction_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence_weight: Mapped[Decimal] = mapped_column(
        Numeric(3, 2),
        nullable=False,
        default=Decimal("1.00"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    claim: Mapped["Claim"] = relationship("Claim", back_populates="evidence_links")
    evidence: Mapped["Evidence"] = relationship(
        "Evidence",
        back_populates="claim_links",
        overlaps="claim,evidence_links",
    )

