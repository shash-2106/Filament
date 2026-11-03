"""Pydantic schemas and DTOs for claim and provenance operations."""

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Literal, Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator

from filament_api.schemas.evidence import SourceType

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


class ClaimResponse(BaseModel):
    """API response schema for a recorded memory claim."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    agent_id: uuid.UUID
    claim_type: ClaimType
    subject: str
    predicate: str
    object_value: Dict[str, Any]
    raw_statement: str
    scope: ClaimScope
    status: ClaimStatus
    confidence: Decimal
    version: int
    active_condition_version: Optional[int] = None
    created_at: datetime
    updated_at: datetime


class LinkEvidenceRequest(BaseModel):
    """Request payload for linking an evidence snapshot to a claim via HTTP."""

    model_config = ConfigDict(extra="forbid")

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


class ClaimEvidenceResponse(BaseModel):
    """API response schema for a claim-evidence provenance link."""

    model_config = ConfigDict(from_attributes=True)

    workspace_id: uuid.UUID
    claim_id: uuid.UUID
    evidence_id: uuid.UUID
    support_type: SupportType
    confidence_weight: Decimal
    extraction_notes: Optional[str] = None
    created_at: datetime


class LinkedEvidenceResponse(BaseModel):
    """Minimal representation of linked evidence with relationship metadata."""

    model_config = ConfigDict(from_attributes=True)

    evidence_id: uuid.UUID
    support_type: SupportType
    confidence_weight: Decimal
    extraction_notes: Optional[str] = None
    source_type: Optional[SourceType] = None
    created_at: datetime


class ClaimDetailResponse(BaseModel):
    """API response schema for claim retrieval with linked evidence provenance."""

    model_config = ConfigDict(from_attributes=True)

    claim: ClaimResponse
    evidence: List[LinkedEvidenceResponse] = Field(default_factory=list)
    provenance: List[LinkedEvidenceResponse] = Field(default_factory=list)



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


RelationType = Literal["supersedes", "depends_on", "contradicts", "corroborates"]


class CreateRelationParams(BaseModel):
    """Parameters for creating a directed edge between claims in the service layer."""

    model_config = ConfigDict(extra="forbid")

    source_claim_id: uuid.UUID = Field(..., description="Source / origin claim ID")
    target_claim_id: uuid.UUID = Field(..., description="Target / destination claim ID")
    relation_type: RelationType = Field(..., description="Semantic edge type")
    rationale: str = Field(..., min_length=1, description="Causal or architectural justification")

    @field_validator("rationale")
    @classmethod
    def validate_rationale(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("rationale cannot be empty whitespace.")
        return v


class SupersedeClaimParams(BaseModel):
    """Parameters for superseding an existing claim with a new claim."""

    model_config = ConfigDict(extra="forbid")

    source_claim_id: uuid.UUID = Field(..., description="New / replacement claim ID")
    target_claim_id: uuid.UUID = Field(..., description="Old / superseded claim ID")
    rationale: str = Field(..., min_length=1, description="Justification explaining why the old claim is superseded")

    @field_validator("rationale")
    @classmethod
    def validate_rationale(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("rationale cannot be empty whitespace.")
        return v


class CreateDependencyParams(BaseModel):
    """Parameters for recording a dependency relationship between claims."""

    model_config = ConfigDict(extra="forbid")

    source_claim_id: uuid.UUID = Field(..., description="Dependent recommendation / claim ID")
    target_claim_id: uuid.UUID = Field(..., description="Prerequisite claim ID")
    rationale: str = Field(..., min_length=1, description="Rationale explaining the dependency")

    @field_validator("rationale")
    @classmethod
    def validate_rationale(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("rationale cannot be empty whitespace.")
        return v


class CreateRelationRequest(BaseModel):
    """HTTP request payload for creating a relationship edge from a source claim."""

    model_config = ConfigDict(extra="forbid")

    target_claim_id: uuid.UUID = Field(..., description="Destination claim ID")
    relation_type: RelationType = Field(..., description="Edge relation type: supersedes or depends_on")
    rationale: str = Field(..., min_length=1, description="Semantic justification")

    @field_validator("rationale")
    @classmethod
    def validate_rationale(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("rationale cannot be empty whitespace.")
        return v


class SupersedeClaimRequest(BaseModel):
    """HTTP request payload for superseding an old claim from a new claim."""

    model_config = ConfigDict(extra="forbid")

    target_claim_id: uuid.UUID = Field(..., description="Old / superseded claim ID")
    rationale: str = Field(..., min_length=1, description="Justification for supersession")

    @field_validator("rationale")
    @classmethod
    def validate_rationale(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("rationale cannot be empty whitespace.")
        return v


class CreateDependencyRequest(BaseModel):
    """HTTP request payload for creating a dependency on a prerequisite claim."""

    model_config = ConfigDict(extra="forbid")

    target_claim_id: uuid.UUID = Field(..., description="Prerequisite claim ID")
    rationale: str = Field(..., min_length=1, description="Rationale for dependency")

    @field_validator("rationale")
    @classmethod
    def validate_rationale(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("rationale cannot be empty whitespace.")
        return v


class ClaimRelationResponse(BaseModel):
    """API response schema for a created claim relation."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    source_claim_id: uuid.UUID
    target_claim_id: uuid.UUID
    relation_type: str
    rationale: str
    created_by_agent: Optional[uuid.UUID] = None
    created_at: datetime
    affected_claim_ids: List[uuid.UUID] = Field(
        default_factory=list,
        description="IDs of claims transitioned to needs_review as a cascade effect",
    )

