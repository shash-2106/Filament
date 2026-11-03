"""Pydantic schemas and DTOs for transient condition evaluation."""

from typing import Any, Dict, List, Literal, Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field

EvaluationOutcome = Literal[
    "applicable",
    "environment_mismatch",
    "indeterminate",
    "not_applicable",
    "unconditioned",
]


class EvaluateClaimConditionsRequest(BaseModel):
    """Request payload for transient condition evaluation against a snapshot."""

    model_config = ConfigDict(extra="forbid")

    snapshot_id: uuid.UUID = Field(
        ...,
        description="ID of the environment snapshot to evaluate conditions against.",
    )


class ConditionEvaluationItem(BaseModel):
    """Detailed evaluation result for an individual prerequisite condition."""

    model_config = ConfigDict(extra="forbid")

    condition_id: Optional[uuid.UUID] = Field(
        default=None,
        description="ID of the stored condition entity, if persisted.",
    )
    condition_type: str = Field(
        ...,
        description="Type of environment artifact or attribute (file_hash, lockfile_hash, package_version, runtime_fact).",
    )
    target_path: str = Field(
        ...,
        description="Target file path, package identifier, or runtime attribute name.",
    )
    target: str = Field(
        ...,
        description="Alias for target_path providing direct target reference.",
    )
    is_critical: bool = Field(
        ...,
        description="Whether failure of this condition invalidates overall applicability.",
    )
    comparator: str = Field(
        default="hash_equals",
        description="Comparison operator applied (hash_equals, version_equals, runtime_equals).",
    )
    expected_value: Any = Field(
        ...,
        description="Expected hash, version, or runtime attribute value.",
    )
    observed_value: Optional[Any] = Field(
        default=None,
        description="Observed value from snapshot if present in scan scope.",
    )
    status: str = Field(
        ...,
        description="Evaluation status: SATISFIED, DRIFTED, or UNCHECKED.",
    )
    reason: str = Field(
        ...,
        description="Machine-readable evaluation reason code.",
    )
    details: Dict[str, Any] = Field(
        default_factory=dict,
        description="Diagnostic details from the evaluation comparator.",
    )


class ClaimEvaluationResponse(BaseModel):
    """API response schema for transient claim condition evaluation."""

    model_config = ConfigDict(extra="forbid")

    claim_id: uuid.UUID = Field(
        ...,
        description="ID of the evaluated claim.",
    )
    snapshot_id: uuid.UUID = Field(
        ...,
        description="ID of the environment snapshot evaluated against.",
    )
    active_condition_version: Optional[int] = Field(
        default=None,
        description="Active condition-set version of the claim, or null if unconditioned.",
    )
    outcome: EvaluationOutcome = Field(
        ...,
        description="Overall evaluation outcome: applicable, environment_mismatch, indeterminate, not_applicable, or unconditioned.",
    )
    is_applicable: bool = Field(
        ...,
        description="Whether the claim is applicable in the evaluated environment (true only when outcome is 'applicable').",
    )
    condition_results: List[ConditionEvaluationItem] = Field(
        default_factory=list,
        description="Individual condition evaluation items and diagnostic details.",
    )

