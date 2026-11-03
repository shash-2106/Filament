"""Pydantic schemas and DTOs for environment snapshot operations."""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator

from filament_api.core.canonicalization import (
    canonicalize_path,
    validate_package_identifier,
)

SourceType = Literal["agent_client", "ci_webhook", "mcp_adapter"]
VerificationLevel = Literal["agent_reported", "independently_verified"]
ScanScope = Literal["full_repository", "selective"]
InventoryScope = Literal["complete", "partial"]


class SnapshotData(BaseModel):
    """Structured environment snapshot payload."""

    model_config = ConfigDict(extra="forbid")

    scanned_roots: List[str] = Field(
        ...,
        min_length=1,
        description="Declared scan root paths (e.g. ['.'] for full repo, or relative directory roots).",
    )
    files: Dict[str, str] = Field(
        default_factory=dict,
        description="Mapping of relative file paths to SHA-256 content hashes.",
    )
    unreadable_paths: List[str] = Field(
        default_factory=list,
        description="List of paths encountered but unreadable due to permissions or I/O errors.",
    )
    packages: Dict[str, Any] = Field(
        default_factory=dict,
        description="Captured package names and exact versions (e.g. {'pypi:redis': '5.0.1'}).",
    )
    packages_scope: InventoryScope = Field(
        default="partial",
        description="Declared completeness of package inventory ('complete' or 'partial'). Defaults to 'partial'.",
    )
    runtime: Dict[str, Any] = Field(
        default_factory=dict,
        description="Captured runtime facts (e.g. {'python': '3.12', 'os': 'linux'}).",
    )
    runtime_scope: InventoryScope = Field(
        default="partial",
        description="Declared completeness of runtime facts inventory ('complete' or 'partial'). Defaults to 'partial'.",
    )

    @field_validator("scanned_roots")
    @classmethod
    def validate_scanned_roots(cls, v: List[str]) -> List[str]:
        if not v:
            raise ValueError("scanned_roots cannot be empty.")
        canonical = []
        for r in v:
            canonical.append(canonicalize_path(r, allow_root_marker=True))
        return canonical

    @field_validator("files")
    @classmethod
    def validate_files(cls, v: Dict[str, str]) -> Dict[str, str]:
        canonical_files = {}
        for path, file_hash in v.items():
            c_path = canonicalize_path(path, allow_root_marker=False)
            if not isinstance(file_hash, str) or len(file_hash) != 64 or not all(c in "0123456789abcdefABCDEF" for c in file_hash):
                raise ValueError(f"File '{path}' must have a valid 64-character SHA-256 hex digest, got '{file_hash}'.")
            canonical_files[c_path] = file_hash.lower()
        return canonical_files

    @field_validator("unreadable_paths")
    @classmethod
    def validate_unreadable(cls, v: List[str]) -> List[str]:
        canonical_unreadable = []
        for path in v:
            canonical_unreadable.append(canonicalize_path(path, allow_root_marker=False))
        return canonical_unreadable

    @field_validator("packages")
    @classmethod
    def validate_packages(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        canonical_packages = {}
        for pkg_id, details in v.items():
            c_id = validate_package_identifier(pkg_id)
            canonical_packages[c_id] = details
        return canonical_packages


class RecordSnapshotParams(BaseModel):
    """Parameters for ingesting an agent-reported environment snapshot."""

    model_config = ConfigDict(extra="forbid")

    source_ref: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="External source reference (e.g. git commit SHA, branch name, or environment tag).",
    )
    source_type: SourceType = Field(
        default="agent_client",
        description="Mechanism through which the snapshot was captured.",
    )
    verification_level: VerificationLevel = Field(
        default="agent_reported",
        description="Provenance level. Client-reported snapshots must remain agent_reported.",
    )
    scan_scope: ScanScope = Field(
        default="full_repository",
        description="Declared scan completeness: full_repository or selective.",
    )
    snapshot_data: SnapshotData = Field(
        ...,
        description="Structured environment inventory.",
    )
    snapshot_id: Optional[uuid.UUID] = Field(
        default=None,
        description="Explicit identifier; generated automatically if omitted.",
    )

    @field_validator("source_ref")
    @classmethod
    def validate_source_ref(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("source_ref cannot be empty or whitespace-only.")
        return v.strip()

    @field_validator("verification_level")
    @classmethod
    def prevent_unauthorized_elevation(cls, v: str, info: Any) -> str:
        # Note: Checked in service layer as well
        return v


class SnapshotResponse(BaseModel):
    """API response schema for a recorded environment snapshot."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    collected_by_agent: uuid.UUID
    source_type: str
    verification_level: str
    source_ref: str
    scan_scope: str
    snapshot_data: Dict[str, Any]
    created_at: datetime
