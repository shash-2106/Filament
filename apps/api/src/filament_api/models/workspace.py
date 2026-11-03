"""Workspace domain model representing tenant boundaries."""

from datetime import datetime
import uuid
from typing import TYPE_CHECKING, List

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from filament_api.db.base import Base

if TYPE_CHECKING:
    from filament_api.models.user import User
    from filament_api.models.agent import Agent
    from filament_api.models.claim import Claim
    from filament_api.models.evidence import Evidence
    from filament_api.models.relation import ClaimRelation
    from filament_api.models.audit import AuditEvent


class Workspace(Base):
    """Tenant boundary workspace container."""

    __tablename__ = "workspaces"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    slug: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
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
    users: Mapped[List["User"]] = relationship(
        "User",
        back_populates="workspace",
        cascade="all, delete-orphan",
    )
    agents: Mapped[List["Agent"]] = relationship(
        "Agent",
        back_populates="workspace",
        cascade="all, delete-orphan",
    )
    claims: Mapped[List["Claim"]] = relationship(
        "Claim",
        back_populates="workspace",
        cascade="all, delete-orphan",
        overlaps="active_condition_set,agent,claims",
    )
    evidence: Mapped[List["Evidence"]] = relationship(
        "Evidence",
        back_populates="workspace",
        cascade="all, delete-orphan",
        overlaps="agent_collector,user_collector",
    )
    claim_relations: Mapped[List["ClaimRelation"]] = relationship(
        "ClaimRelation",
        back_populates="workspace",
        cascade="all, delete-orphan",
    )
    audit_events: Mapped[List["AuditEvent"]] = relationship(
        "AuditEvent",
        back_populates="workspace",
        cascade="all, delete-orphan",
    )

