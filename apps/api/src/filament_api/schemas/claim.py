"""Pydantic schemas and DTOs for claim and provenance operations."""

from decimal import Decimal
from typing import Any, Dict, Literal, Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator

ClaimType = Literal["fact", "recommendation", "decision", "preference", "constraint"]
ClaimScope = Literal["private", "team", "workspace"]
ClaimStatus = Literal["current", "superseded", "disputed", "needs_review", "retracted"]
SupportType = Literal["supports", "refutes", "mentions"]


class CreateClaimParams(BaseModel):
    """Parameters for creating a governed claim in memory."""

    model_config = ConfigDict(extra="forbid")

    subject: str = Field(..., min_length=1, max_length=128, description="Target entity or topic")
    predicate: str = Field(..., min_length=1, max_length=64, description="Semantic attribute")
    object_value: Dict[str, Any] = Field(..., description="Structured payload")
    raw_statement: str = Field(..., min_length=1, description="Human-readable statement")
    claim_type: ClaimType = Field(default="fact", description="Assertion classification")
    scope: ClaimScope = Field(default="private", description="Memory visibility scope")
    status: ClaimStatus = Field(default="current", description="Lifecycle validity status")
    confidence: Decimal = Field(
        default=Decimal("1.00"),
        ge=Decimal("0.00"),
        le=Decimal("1.00"),
        description="Confidence score between 0.00 and 1.00",
    )
    agent_id: Optional[uuid.UUID] = Field(
        default=None,
        description="Originating agent ID. Inferred from TrustedContext if caller is an agent.",
    )
    claim_id: Optional[uuid.UUID] = Field(
        default=None,
        description="Explicit identifier; generated automatically if omitted.",
    )

    @field_validator("subject", "predicate", "raw_statement")
    @classmethod
    def validate_non_whitespace(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Field cannot be empty or whitespace-only.")
        return v


class LinkEvidenceParams(BaseModel):
    """Parameters for linking an evidence snapshot to a claim."""

    model_config = ConfigDict(extra="forbid")

    claim_id: uuid.UUID = Field(..., description="Target claim ID")
    evidence_id: uuid.UUID = Field(..., description="Target evidence ID")
    support_type: SupportType = Field(default="supports", description="Polarity of evidence")
    confidence_weight: Decimal = Field(
        default=Decimal("1.00"),
        ge=Decimal("0.00"),
        le=Decimal("1.00"),
        description="Confidence weight between 0.00 and 1.00",
    )
    extraction_notes: Optional[str] = Field(
        default=None,
        description="Optional human/agent notes describing the derivation or contradiction rationale.",
    )

    @field_validator("extraction_notes")
    @classmethod
    def validate_notes(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not v.strip():
            raise ValueError("extraction_notes cannot be empty whitespace.")
        return v

