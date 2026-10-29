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

    def __init__(self, claim_id: uuid.UUID, evidence_id: uuid.UUID) -> None:
        super().__init__(
            f"Evidence '{evidence_id}' is already linked to Claim '{claim_id}'."
        )
        self.claim_id = claim_id
        self.evidence_id = evidence_id


class InvalidClaimStateError(FilamentDomainError):
    """Raised when an illegal claim lifecycle transition is attempted."""

    def __init__(self, current_status: str, requested_status: str) -> None:
        super().__init__(
            f"Cannot transition claim status from '{current_status}' to '{requested_status}'."
        )
        self.current_status = current_status
        self.requested_status = requested_status

