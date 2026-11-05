"""Database domain model for durable Meta Model API budget reservation and usage tracking."""

from datetime import datetime, timezone
from decimal import Decimal
import uuid

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from filament_api.db.base import Base


class ModelUsageRecord(Base):
    """Persistent audit and spending ledger entry for every Meta Model API request.

    Guarantees atomic budget reservation prior to network calls and records exact
    reconciliation upon provider response or error.
    """

    __tablename__ = "model_usage_records"
    __table_args__ = (
        CheckConstraint(
            "status IN ('RESERVED', 'SUCCEEDED', 'FAILED', 'UNKNOWN')",
            name="ck_model_usage_status",
        ),
        CheckConstraint("reserved_cost_usd >= 0", name="ck_model_usage_reserved_cost_non_negative"),
        CheckConstraint("actual_cost_usd >= 0", name="ck_model_usage_actual_cost_non_negative"),
        CheckConstraint("estimated_input_tokens >= 0", name="ck_model_usage_est_input_non_negative"),
        CheckConstraint("max_reserved_output_tokens >= 0", name="ck_model_usage_max_output_non_negative"),
        Index("ix_model_usage_status", "status"),
        Index("ix_model_usage_created_at", "created_at"),
        Index("ix_model_usage_workspace_created", "workspace_id", "created_at"),
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
    feature: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="Feature or operation requesting inference (e.g. claim_extraction, test_mock)",
    )
    model: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="Allowlisted model identifier (e.g. muse-spark-1.3)",
    )

    # Token Accounting
    estimated_input_tokens: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    max_reserved_output_tokens: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    actual_input_tokens: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    actual_output_tokens: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    # Financial Ledger (USD with 6 decimal places for sub-cent precision)
    reserved_cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(12, 6),
        nullable=False,
        default=Decimal("0.000000"),
    )
    actual_cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(12, 6),
        nullable=False,
        default=Decimal("0.000000"),
    )

    # State Machine: RESERVED -> SUCCEEDED | FAILED | UNKNOWN
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="RESERVED",
    )

    provider_request_id: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        comment="Provider request or tracking ID returned by Meta API headers/body",
    )
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Sanitized, secret-free error diagnostics",
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

