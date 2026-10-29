"""Trusted security and tenant context for service operations.

CRITICAL SECURITY INVARIANT:
`TrustedContext` represents the verified caller identity and tenant isolation boundary.
Because Filament never trusts client-supplied identity claims, `TrustedContext` MUST NEVER
be bound directly to FastAPI request bodies, query parameters, or unverified headers.
It must ONLY be constructed by authenticated middleware or verified security dependencies
(e.g., `get_current_trusted_context`) after validating cryptographic credentials
(API key SHA-256 hash or signed session token).
"""

from dataclasses import dataclass
from enum import Enum
from typing import Literal, Optional
import uuid

from filament_api.services.exceptions import (
    UnauthorizedActorError,
    ValidationDomainError,
    WorkspaceMismatchError,
)


class ActorType(str, Enum):
    """Permitted actor classifications for domain operations."""

    AGENT = "agent"
    USER = "user"
    SYSTEM = "system"


@dataclass(frozen=True)
class TrustedContext:
    """Immutable verified tenant boundary and actor identity.

    Never construct this directly from raw unverified client input.
    Must be instantiated only by trusted authentication dependencies.
    """

    workspace_id: uuid.UUID
    actor_type: Literal["agent", "user", "system"]
    actor_id: uuid.UUID
    is_active: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.workspace_id, uuid.UUID):
            raise ValidationDomainError(
                f"workspace_id must be a UUID instance, got {type(self.workspace_id).__name__}."
            )
        if not isinstance(self.actor_id, uuid.UUID):
            raise ValidationDomainError(
                f"actor_id must be a UUID instance, got {type(self.actor_id).__name__}."
            )
        if not isinstance(self.is_active, bool):
            raise ValidationDomainError(
                f"is_active must be a boolean, got {type(self.is_active).__name__}."
            )
        if self.actor_type not in ("agent", "user", "system"):
            raise ValidationDomainError(f"Invalid actor_type: {self.actor_type}")
        if not self.is_active:
            raise UnauthorizedActorError("Actor account is inactive or disabled.")

    @property
    def is_agent(self) -> bool:
        return self.actor_type == "agent"

    @property
    def is_user(self) -> bool:
        return self.actor_type == "user"

    @property
    def is_system(self) -> bool:
        return self.actor_type == "system"

    def ensure_workspace(self, target_workspace_id: uuid.UUID) -> None:
        """Enforce strict workspace boundary matching."""
        if self.workspace_id != target_workspace_id:
            raise WorkspaceMismatchError(
                f"Context workspace '{self.workspace_id}' does not match target workspace '{target_workspace_id}'."
            )

    def resolve_agent_id_for_claim(self, claimed_agent_id: Optional[uuid.UUID]) -> uuid.UUID:
        """Resolve and validate the agent identifier responsible for creating a claim.

        Claims can only be created by an authorized agent in the same workspace.
        Non-agent actors (e.g. human users) are rejected with UnauthorizedActorError.
        """
        if not self.is_agent:
            raise UnauthorizedActorError(
                f"Actor of type '{self.actor_type}' is not authorized to create claims. "
                "Claims can only be created by an authorized agent in the same workspace."
            )

        if claimed_agent_id is not None and claimed_agent_id != self.actor_id:
            raise UnauthorizedActorError(
                f"Agent '{self.actor_id}' cannot create claims for another agent '{claimed_agent_id}'."
            )
        return self.actor_id

