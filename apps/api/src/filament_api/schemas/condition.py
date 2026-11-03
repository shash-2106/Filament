"""Pydantic schemas and DTOs for condition establishment and verification."""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from filament_api.core.canonicalization import (
    canonicalize_path,
    validate_package_identifier,
)
from filament_api.schemas.evaluation import ConditionEvaluationItem

ConditionType = Literal["file_hash", "lockfile_hash", "package_version", "runtime_fact"]
Comparator = Literal["hash_equals", "version_equals", "runtime_equals"]


class ConditionSpec(BaseModel):
    """Specification of an individual environment prerequisite condition."""

    model_config = ConfigDict(extra="forbid")

    condition_type: ConditionType = Field(
        ...,
        description="Type of environment artifact or attribute to bound.",
    )
    target_path: str = Field(
        ...,
        min_length=1,
        description="POSIX relative file path, package identifier (e.g. pypi:redis), or runtime attribute name.",
    )
    comparator: Comparator = Field(
        default="hash_equals",
        description="Exact deterministic comparison operator.",
    )
    expected_hash: Optional[str] = Field(
        default=None,
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-fA-F]{64}$",
        description="Expected 64-character SHA-256 digest for hash_equals comparator.",
    )
    expected_value: Dict[str, Any] = Field(
        default_factory=dict,
        description="Structured expected value representation (e.g. {'version': '5.0.1'}).",
    )
    is_critical: bool = Field(
        default=True,
        description="Whether failure of this condition invalidates the claim's applicability.",
    )

    @field_validator("target_path")
    @classmethod
    def validate_target_path(cls, v: str, info: Any) -> str:
        # File paths must be canonicalized under Step 21C rules
        cond_type = info.data.get("condition_type")
        if cond_type in ("file_hash", "lockfile_hash"):
            return canonicalize_path(v, allow_root_marker=False)
        if cond_type == "package_version":
            return validate_package_identifier(v)
        # Runtime identifiers must not contain leading/trailing whitespace
        if v != v.strip():
            raise ValueError("target_path must not contain leading or trailing whitespace.")
        if not v.strip():
            raise ValueError("target_path cannot be empty.")
        return v.strip()

    @field_validator("comparator")
    @classmethod
    def validate_comparator_type_match(cls, v: str, info: Any) -> str:
        cond_type = info.data.get("condition_type")
        if cond_type in ("file_hash", "lockfile_hash") and v != "hash_equals":
            raise ValueError(f"Condition type '{cond_type}' requires comparator 'hash_equals'.")
        if cond_type == "package_version" and v != "version_equals":
            raise ValueError("Condition type 'package_version' requires comparator 'version_equals'.")
        if cond_type == "runtime_fact" and v != "runtime_equals":
            raise ValueError("Condition type 'runtime_fact' requires comparator 'runtime_equals'.")
        return v

    @model_validator(mode="after")
    def validate_condition_payload(self) -> "ConditionSpec":
        if self.condition_type in ("file_hash", "lockfile_hash"):
            hash_val = self.expected_hash or self.expected_value.get("hash")
            if not hash_val:
                raise ValueError(
                    f"Condition type '{self.condition_type}' requires a valid 64-character SHA-256 hash "
                    f"in expected_hash or expected_value['hash']."
                )
            if not isinstance(hash_val, str) or len(hash_val) != 64 or not all(c in "0123456789abcdefABCDEF" for c in hash_val):
                raise ValueError(
                    f"Invalid SHA-256 hash for '{self.condition_type}': expected 64 hex characters, got '{hash_val}'."
                )
        return self


class EstablishConditionsParams(BaseModel):
    """Parameters for establishing the initial versioned condition set for an unconditioned claim."""

    model_config = ConfigDict(extra="forbid")

    based_on_snapshot_id: uuid.UUID = Field(
        ...,
        description="ID of the environment snapshot against which conditions were established.",
    )
    rationale: str = Field(
        ...,
        min_length=1,
        description="Justification explaining why these conditions are necessary for the claim.",
    )
    conditions: List[ConditionSpec] = Field(
        ...,
        min_length=1,
        description="List of prerequisite conditions establishing the environment boundary.",
    )

    @field_validator("rationale")
    @classmethod
    def validate_rationale(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("rationale cannot be empty or whitespace-only.")
        return v.strip()

    @field_validator("conditions")
    @classmethod
    def validate_conditions(cls, v: List[ConditionSpec]) -> List[ConditionSpec]:
        if not v:
            raise ValueError("At least one condition must be specified.")

        has_critical = any(c.is_critical for c in v)
        if not has_critical:
            raise ValueError("Every condition set must contain at least one condition with is_critical=true.")

        seen_targets = set()
        for c in v:
            key = (c.condition_type, c.target_path)
            if key in seen_targets:
                raise ValueError(f"Duplicate condition for ({c.condition_type}, '{c.target_path}') in the same condition set.")
            seen_targets.add(key)
        return v


class ConditionResponse(BaseModel):
    """API response schema for an individual established condition."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    claim_id: uuid.UUID
    condition_set_version: int
    condition_type: str
    target_path: str
    comparator: str
    expected_hash: Optional[str] = None
    expected_value: Dict[str, Any]
    is_critical: bool
    created_at: datetime


class ConditionSetResponse(BaseModel):
    """API response schema for a committed condition set."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    claim_id: uuid.UUID
    version: int
    based_on_snapshot_id: uuid.UUID
    established_by_agent: uuid.UUID
    rationale: str
    created_at: datetime
    conditions: List[ConditionResponse] = Field(default_factory=list)


ReverificationAction = Literal["verify_existing", "adopt_new_conditions"]


class ReverifyClaimParams(BaseModel):
    """Parameters for reverifying a claim or adopting a replacement condition set."""

    model_config = ConfigDict(extra="forbid")

    snapshot_id: uuid.UUID = Field(
        ...,
        description="ID of the environment snapshot to reverify against.",
    )
    action: ReverificationAction = Field(
        default="verify_existing",
        description="Explicit re-verification action: 'verify_existing' or 'adopt_new_conditions'.",
    )
    expected_condition_version: int = Field(
        ...,
        ge=1,
        description="Expected active condition-set version for optimistic concurrency protection.",
    )
    attestation_notes: str = Field(
        ...,
        min_length=1,
        description="Notes attesting the verification or condition adoption rationale.",
    )
    adopt_rationale: Optional[str] = Field(
        default=None,
        description="Required when action is 'adopt_new_conditions': justification for adopting the new condition set.",
    )
    proposed_conditions: Optional[List[ConditionSpec]] = Field(
        default=None,
        description="Required when action is 'adopt_new_conditions': list of proposed replacement conditions.",
    )

    @field_validator("attestation_notes")
    @classmethod
    def validate_attestation(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("attestation_notes cannot be empty or whitespace-only.")
        return v.strip()

    @model_validator(mode="after")
    def validate_reverification_action(self) -> "ReverifyClaimParams":
        if self.action == "adopt_new_conditions":
            if not self.proposed_conditions:
                raise ValueError("proposed_conditions cannot be empty when action is 'adopt_new_conditions'.")
            if not self.adopt_rationale or not self.adopt_rationale.strip():
                raise ValueError("adopt_rationale is required when action is 'adopt_new_conditions'.")
            if not any(c.is_critical for c in self.proposed_conditions):
                raise ValueError("Every adopted condition set must contain at least one condition with is_critical=true.")

            seen_targets = set()
            for c in self.proposed_conditions:
                key = (c.condition_type, c.target_path)
                if key in seen_targets:
                    raise ValueError(
                        f"Duplicate condition for ({c.condition_type}, '{c.target_path}') in proposed conditions."
                    )
                seen_targets.add(key)
        elif self.action == "verify_existing":
            if self.proposed_conditions is not None:
                raise ValueError(
                    "proposed_conditions must not be provided when action is 'verify_existing'. "
                    "Explicit adoption intent ('adopt_new_conditions') is required."
                )
        return self


class ReverifyClaimResponse(BaseModel):
    """API response schema for formal claim re-verification or condition adoption."""

    model_config = ConfigDict(extra="forbid")

    verification_id: uuid.UUID
    claim_id: uuid.UUID
    snapshot_id: uuid.UUID
    condition_set_version: int
    active_condition_version: int
    verification_type: str
    outcome: str
    is_applicable: bool
    action_taken: str
    verified_by_agent: uuid.UUID
    attestation_notes: str
    condition_results: List[ConditionEvaluationItem] = Field(default_factory=list)
    created_at: datetime
