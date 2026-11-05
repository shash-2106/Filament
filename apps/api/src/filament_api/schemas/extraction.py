"""Pydantic schemas for LLM-assisted candidate memory extraction and approval workflow."""

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Literal, Optional
import uuid
from pydantic import BaseModel, ConfigDict, Field, field_validator

from filament_api.schemas.claim import ClaimScope, ClaimType


class ExtractionEstimateRequest(BaseModel):
    """Request to preview estimated tokens and maximum cost for a transcript."""

    model_config = ConfigDict(extra="forbid")
    transcript: str = Field(..., min_length=10, max_length=100000, description="Agent transcript or excerpt")


class ExtractionEstimateResponse(BaseModel):
    """Estimated token counts and maximum worst-case cost."""

    estimated_input_tokens: int
    max_output_tokens: int
    estimated_cost_usd: float
    model: str
    remaining_lifetime_budget_usd: float
    remaining_test_budget_usd: float
    gateway_enabled: bool


class CandidateMemory(BaseModel):
    """A structured candidate memory proposed by Muse Spark 1.3 from conversation excerpts."""

    model_config = ConfigDict(extra="forbid")

    temp_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Temporary identifier for review UI")
    subject: str = Field(default="system", min_length=1, max_length=128, description="Target entity, component or subject")
    predicate: str = Field(default="rule", min_length=1, max_length=64, description="Relationship or property attribute")
    statement: str = Field(..., min_length=1, description="Concise human-readable memory statement")
    claim_type: ClaimType = Field(default="fact", description="Assertion category: fact, recommendation, decision, preference, constraint")
    scope: ClaimScope = Field(default="team", description="Visibility scope: private, team, workspace")
    confidence: Decimal = Field(default=Decimal("0.85"), ge=Decimal("0.00"), le=Decimal("1.00"), description="Confidence score")
    
    # Provenance and evidence
    evidence_quote: str = Field(..., min_length=1, description="Direct verbatim excerpt from the transcript supporting this memory")
    source_reference: Optional[str] = Field(default=None, description="Speaker or location in transcript")
    
    # Condition guidance (suggested requirements, not active conditions)
    suggested_validity_requirements: List[str] = Field(default_factory=list, description="Suggested conditions under which this memory is valid")
    relevant_files: List[str] = Field(default_factory=list, description="Relevant files, dependencies or configuration paths")
    uncertainty_notes: Optional[str] = Field(default=None, description="Ambiguities or caveats identified by the model")
    suggested_relationships: List[str] = Field(default_factory=list, description="Possible links to existing knowledge")

    @field_validator("subject", "predicate", "statement", "evidence_quote")
    @classmethod
    def validate_non_whitespace(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Field cannot be empty or whitespace-only.")
        return v.strip()


class ExtractMemoriesRequest(BaseModel):
    """User request to perform model-assisted candidate memory extraction."""

    model_config = ConfigDict(extra="forbid")
    transcript: str = Field(..., min_length=10, max_length=100000, description="Raw agent transcript or tool output")
    user_confirmed_cost: bool = Field(..., description="User explicit acknowledgement of cost before execution")


class ExtractMemoriesResponse(BaseModel):
    """Extracted candidate memories ready for human review."""

    candidates: List[CandidateMemory]
    usage: Dict[str, Any]
    provider_request_id: Optional[str]
    record_id: str
    model: str
    explanation: str = Field(
        default="Candidate memories extracted by Muse Spark. Review, edit, and approve each memory before persistence.",
        description="User-facing guidance",
    )


class ApproveCandidateRequest(BaseModel):
    """Parameters for approving and persisting a single reviewed candidate memory."""

    model_config = ConfigDict(extra="forbid")

    subject: str = Field(..., min_length=1, max_length=128)
    predicate: str = Field(..., min_length=1, max_length=64)
    statement: str = Field(..., min_length=1)
    claim_type: ClaimType = Field(default="fact")
    scope: ClaimScope = Field(default="team")
    confidence: Decimal = Field(default=Decimal("0.85"), ge=Decimal("0.00"), le=Decimal("1.00"))
    
    # Evidence linkage
    evidence_quote: str = Field(..., min_length=1, description="Verbatim quote stored as immutable evidence")
    source_uri: str = Field(default="agent_conversation_transcript", description="Provenance source reference")
    
    # Optional snapshot link for condition baseline
    snapshot_id: Optional[uuid.UUID] = Field(default=None, description="Optional environment snapshot ID if conditions should be governed")
    condition_rules: List[str] = Field(default_factory=list, description="Optional condition rule keys to activate against snapshot")


class ApproveCandidateResponse(BaseModel):
    """Result of persisting an approved candidate memory into governed storage."""

    claim_id: uuid.UUID
    evidence_id: uuid.UUID
    condition_set_id: Optional[uuid.UUID] = None
    status: str = "current"
    message: str = "Candidate memory approved and successfully stored with provenance."

