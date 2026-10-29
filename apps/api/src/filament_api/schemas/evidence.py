"""Pydantic schemas and DTOs for evidence operations."""

from typing import Any, Dict, Literal, Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator

SourceType = Literal["file", "git_commit", "user_turn", "tool_output", "api_response"]


class RecordEvidenceParams(BaseModel):
    """Parameters for recording an immutable evidence snapshot."""

    model_config = ConfigDict(extra="forbid")

    source_type: SourceType
    source_uri: str = Field(..., min_length=1, description="URI or path identifier of the source")
    raw_snippet: str = Field(..., min_length=1, description="Verbatim text snapshot")
    content_hash: Optional[str] = Field(
        default=None,
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-fA-F]{64}$",
        description="Optional SHA-256 hex string. Computed automatically if omitted.",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary structured metadata regarding the observation context.",
    )
    evidence_id: Optional[uuid.UUID] = Field(
        default=None,
        description="Explicit identifier; generated automatically if omitted.",
    )

    @field_validator("source_uri", "raw_snippet")
    @classmethod
    def validate_non_whitespace(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Field cannot be empty or whitespace-only.")
        return v

