"""Condition governance domain models for versioned environment prerequisite bindings."""

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List
import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
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
    from filament_api.models.claim import Claim
    from filament_api.models.snapshot import EnvironmentSnapshot
    from filament_api.models.workspace import Workspace


class ClaimConditionSet(Base):
    """Immutable versioned set of environment prerequisite conditions established for a claim."""

    __tablename__ = "claim_condition_sets"
    __table_args__ = (
        UniqueConstraint("workspace_id", "claim_id", "version", name="uq_claim_condition_sets_version"),
        ForeignKeyConstraint(
            ["workspace_id", "claim_id"],
            ["claims.workspace_id", "claims.id"],
            ondelete="RESTRICT",
            name="fk_claim_condition_sets_claim",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "based_on_snapshot_id"],
            ["environment_snapshots.workspace_id", "environment_snapshots.id"],
            ondelete="RESTRICT",
            name="fk_claim_condition_sets_snapshot",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "established_by_agent"],
            ["agents.workspace_id", "agents.id"],
            ondelete="RESTRICT",
            name="fk_claim_condition_sets_agent",
        ),
        Index("idx_claim_condition_sets_claim", "workspace_id", "claim_id", "version"),
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
    claim_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
    )
    based_on_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )
    established_by_agent: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )
    rationale: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    workspace: Mapped["Workspace"] = relationship("Workspace", overlaps="based_on_snapshot,claim,condition_sets,established_by")
    claim: Mapped["Claim"] = relationship(
        "Claim",
        primaryjoin="and_(ClaimConditionSet.workspace_id == Claim.workspace_id, ClaimConditionSet.claim_id == Claim.id)",
        foreign_keys="[ClaimConditionSet.workspace_id, ClaimConditionSet.claim_id]",
        back_populates="condition_sets",
        overlaps="based_on_snapshot,claim,condition_sets,established_by,workspace",
    )
    based_on_snapshot: Mapped["EnvironmentSnapshot"] = relationship(
        "EnvironmentSnapshot",
        primaryjoin="and_(ClaimConditionSet.workspace_id == EnvironmentSnapshot.workspace_id, ClaimConditionSet.based_on_snapshot_id == EnvironmentSnapshot.id)",
        foreign_keys="[ClaimConditionSet.workspace_id, ClaimConditionSet.based_on_snapshot_id]",
        back_populates="condition_sets",
        overlaps="based_on_snapshot,claim,condition_sets,established_by,workspace",
    )
    established_by: Mapped["Agent"] = relationship(
        "Agent",
        primaryjoin="and_(ClaimConditionSet.workspace_id == Agent.workspace_id, ClaimConditionSet.established_by_agent == Agent.id)",
        foreign_keys="[ClaimConditionSet.workspace_id, ClaimConditionSet.established_by_agent]",
        overlaps="based_on_snapshot,claim,condition_sets,established_by,workspace",
    )
    conditions: Mapped[List["ClaimCondition"]] = relationship(
        "ClaimCondition",
        primaryjoin="and_(ClaimConditionSet.workspace_id == ClaimCondition.workspace_id, ClaimConditionSet.claim_id == ClaimCondition.claim_id, ClaimConditionSet.version == ClaimCondition.condition_set_version)",
        foreign_keys="[ClaimCondition.workspace_id, ClaimCondition.claim_id, ClaimCondition.condition_set_version]",
        back_populates="condition_set",
        cascade="all, delete-orphan",
    )
    verifications: Mapped[List["ClaimVerification"]] = relationship(
        "ClaimVerification",
        primaryjoin="and_(ClaimConditionSet.workspace_id == ClaimVerification.workspace_id, ClaimConditionSet.claim_id == ClaimVerification.claim_id, ClaimConditionSet.version == ClaimVerification.condition_set_version)",
        foreign_keys="[ClaimVerification.workspace_id, ClaimVerification.claim_id, ClaimVerification.condition_set_version]",
        back_populates="condition_set",
        cascade="all, delete-orphan",
    )


class ClaimCondition(Base):
    """Immutable individual prerequisite condition attached to a specific claim condition set."""

    __tablename__ = "claim_conditions"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "claim_id",
            "condition_set_version",
            "condition_type",
            "target_path",
            name="uq_claim_conditions_entry",
        ),
        CheckConstraint(
            "condition_type IN ('file_hash', 'lockfile_hash', 'package_version', 'runtime_fact')",
            name="ck_claim_conditions_type",
        ),
        CheckConstraint(
            "comparator IN ('hash_equals', 'version_equals', 'runtime_equals')",
            name="ck_claim_conditions_comparator",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "claim_id", "condition_set_version"],
            ["claim_condition_sets.workspace_id", "claim_condition_sets.claim_id", "claim_condition_sets.version"],
            ondelete="CASCADE",
            name="fk_claim_conditions_set",
        ),
        Index("idx_claim_conditions_query", "workspace_id", "claim_id", "condition_set_version"),
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
    claim_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )
    condition_set_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
    )
    condition_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    target_path: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    comparator: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="hash_equals",
    )
    expected_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    expected_value: Mapped[Dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )
    is_critical: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    condition_set: Mapped["ClaimConditionSet"] = relationship(
        "ClaimConditionSet",
        primaryjoin="and_(ClaimCondition.workspace_id == ClaimConditionSet.workspace_id, ClaimCondition.claim_id == ClaimConditionSet.claim_id, ClaimCondition.condition_set_version == ClaimConditionSet.version)",
        foreign_keys="[ClaimCondition.workspace_id, ClaimCondition.claim_id, ClaimCondition.condition_set_version]",
        back_populates="conditions",
    )


class ClaimVerification(Base):
    """Immutable audit record attesting formal evaluation or re-verification against an environment snapshot."""

    __tablename__ = "claim_verifications"
    __table_args__ = (
        CheckConstraint(
            "verification_type IN ('initial', 'reverification')",
            name="ck_claim_verifications_type",
        ),
        CheckConstraint(
            "outcome IN ('applicable', 'environment_mismatch', 'indeterminate')",
            name="ck_claim_verifications_outcome",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "claim_id", "condition_set_version"],
            ["claim_condition_sets.workspace_id", "claim_condition_sets.claim_id", "claim_condition_sets.version"],
            ondelete="CASCADE",
            name="fk_claim_verifications_set",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "snapshot_id"],
            ["environment_snapshots.workspace_id", "environment_snapshots.id"],
            ondelete="RESTRICT",
            name="fk_claim_verifications_snapshot",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "verified_by_agent"],
            ["agents.workspace_id", "agents.id"],
            ondelete="RESTRICT",
            name="fk_claim_verifications_agent",
        ),
        Index("idx_claim_verifications_timeline", "workspace_id", "claim_id", "created_at"),
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
    claim_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )
    condition_set_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )
    verification_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="reverification",
    )
    outcome: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    evaluation_details: Mapped[Dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )
    verified_by_agent: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )
    attestation_notes: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    condition_set: Mapped["ClaimConditionSet"] = relationship(
        "ClaimConditionSet",
        primaryjoin="and_(ClaimVerification.workspace_id == ClaimConditionSet.workspace_id, ClaimVerification.claim_id == ClaimConditionSet.claim_id, ClaimVerification.condition_set_version == ClaimConditionSet.version)",
        foreign_keys="[ClaimVerification.workspace_id, ClaimVerification.claim_id, ClaimVerification.condition_set_version]",
        back_populates="verifications",
        overlaps="condition_set,snapshot,verifications,verifier",
    )
    snapshot: Mapped["EnvironmentSnapshot"] = relationship(
        "EnvironmentSnapshot",
        primaryjoin="and_(ClaimVerification.workspace_id == EnvironmentSnapshot.workspace_id, ClaimVerification.snapshot_id == EnvironmentSnapshot.id)",
        foreign_keys="[ClaimVerification.workspace_id, ClaimVerification.snapshot_id]",
        back_populates="verifications",
        overlaps="condition_set,snapshot,verifications,verifier",
    )
    verifier: Mapped["Agent"] = relationship(
        "Agent",
        primaryjoin="and_(ClaimVerification.workspace_id == Agent.workspace_id, ClaimVerification.verified_by_agent == Agent.id)",
        foreign_keys="[ClaimVerification.workspace_id, ClaimVerification.verified_by_agent]",
        overlaps="condition_set,snapshot,verifications,verifier",
    )
