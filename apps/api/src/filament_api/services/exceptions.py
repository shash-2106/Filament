"""Domain exception hierarchy for Filament service layer."""

import uuid


class FilamentDomainError(Exception):
    """Base exception for all domain and governance errors."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class EntityNotFoundError(FilamentDomainError):
    """Raised when an expected entity does not exist within the tenant workspace."""

    def __init__(self, entity_name: str, entity_id: uuid.UUID) -> None:
        super().__init__(f"{entity_name} with ID '{entity_id}' was not found in the workspace.")
        self.entity_name = entity_name
        self.entity_id = entity_id


class WorkspaceMismatchError(FilamentDomainError):
    """Raised when an operation attempts to link or access records across different workspaces."""

    def __init__(self, message: str = "Entities must belong to the same workspace.") -> None:
        super().__init__(message)


class UnauthorizedActorError(FilamentDomainError):
    """Raised when an actor lacks permission or attempts to impersonate another identity."""

    def __init__(self, message: str = "Actor is not authorized for this operation.") -> None:
        super().__init__(message)


class ValidationDomainError(FilamentDomainError):
    """Raised when domain entity validation fails (e.g. confidence bounds or invalid literals)."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


class DuplicateLinkError(FilamentDomainError):
    """Raised when a claim-evidence link already exists."""

    def __init__(self, claim_id: uuid.UUID, evidence_id: uuid.UUID, message: str | None = None) -> None:
        if message is None:
            message = f"Evidence '{evidence_id}' is already linked to Claim '{claim_id}'."
        super().__init__(message)
        self.claim_id = claim_id
        self.evidence_id = evidence_id


class DuplicateRelationError(DuplicateLinkError):
    """Raised when a claim relation edge already exists."""

    def __init__(self, source_claim_id: uuid.UUID, target_claim_id: uuid.UUID, relation_type: str) -> None:
        message = (
            f"Relation '{relation_type}' from Claim '{source_claim_id}' to "
            f"Claim '{target_claim_id}' already exists."
        )
        super().__init__(source_claim_id, target_claim_id, message=message)
        self.source_claim_id = source_claim_id
        self.target_claim_id = target_claim_id
        self.relation_type = relation_type


class CyclicRelationError(FilamentDomainError):
    """Raised when adding a relation would introduce a directed cycle in the claims graph."""

    def __init__(self, source_claim_id: uuid.UUID, target_claim_id: uuid.UUID, relation_type: str) -> None:
        super().__init__(
            f"Cannot create '{relation_type}' relation from Claim '{source_claim_id}' to "
            f"Claim '{target_claim_id}': it would introduce a cycle in the {relation_type} graph."
        )
        self.source_claim_id = source_claim_id
        self.target_claim_id = target_claim_id
        self.relation_type = relation_type


class InvalidClaimStateError(FilamentDomainError):
    """Raised when an illegal claim lifecycle transition is attempted."""

    def __init__(
        self,
        current_status: str,
        requested_status: str,
        message: str | None = None,
    ) -> None:
        super().__init__(
            message
            or f"Cannot transition claim status from '{current_status}' to '{requested_status}'."
        )
        self.current_status = current_status
        self.requested_status = requested_status


class StaleConditionVersionError(FilamentDomainError):
    """Raised when re-verification specifies a stale or conflicting active condition version."""

    def __init__(self, claim_id: uuid.UUID, expected_version: int, actual_version: int | None) -> None:
        super().__init__(
            f"Stale condition version for claim '{claim_id}': expected active version {expected_version}, "
            f"but current active version is {actual_version}."
        )
        self.claim_id = claim_id
        self.expected_version = expected_version
        self.actual_version = actual_version


from filament_api.core.canonicalization import PathValidationError


class ConditionsAlreadyEstablishedError(FilamentDomainError):
    """Raised when initial condition establishment is attempted on an already conditioned claim."""

    def __init__(self, claim_id: uuid.UUID, active_version: int) -> None:
        super().__init__(
            f"Claim '{claim_id}' already has established condition set version {active_version}. "
            "Use reverification to update conditions."
        )
        self.claim_id = claim_id
        self.active_version = active_version


class ConditionSnapshotMismatchError(ValidationDomainError):
    """Raised when proposed conditions fail evaluation against the establishing snapshot."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


class CriticalConditionRequiredError(ValidationDomainError):
    """Raised when a condition set does not contain at least one critical condition."""

    def __init__(
        self,
        message: str = "Every condition set must contain at least one condition with is_critical=true.",
    ) -> None:
        super().__init__(message)

