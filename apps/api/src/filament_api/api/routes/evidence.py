"""Evidence API route handlers."""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from filament_api.api.dependencies.auth import get_current_agent_context
from filament_api.core import log_safe_exception
from filament_api.db.session import get_db
from filament_api.schemas.evidence import EvidenceResponse, RecordEvidenceParams
from filament_api.services.context import TrustedContext
from filament_api.services.evidence import EvidenceService
from filament_api.services.exceptions import FilamentDomainError, ValidationDomainError

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/evidence",
    response_model=EvidenceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record Evidence Snapshot",
    description=(
        "Records an immutable source observation snapshot (e.g. file excerpt, git commit, "
        "user turn, or tool output) with cryptographic integrity hashing and atomic audit logging."
    ),
    response_description="Newly recorded evidence snapshot",
)
async def record_evidence(
    params: RecordEvidenceParams,
    context: TrustedContext = Depends(get_current_agent_context),
    session: AsyncSession = Depends(get_db),
) -> EvidenceResponse:
    """Record an immutable evidence snapshot bound to the caller's verified workspace."""
    try:
        evidence = await EvidenceService.record_evidence(
            session=session,
            context=context,
            params=params,
        )
        # Prepare and validate response model representation BEFORE committing
        # This guarantees response serialization errors do not occur after a successful commit.
        response = EvidenceResponse.model_validate(evidence)

        # Explicit endpoint-owned commit
        await session.commit()

        return response
    except ValidationDomainError as exc:
        if session.is_active:
            await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"error": {"code": "VALIDATION_ERROR", "message": exc.message}},
        ) from exc
    except FilamentDomainError as exc:
        if session.is_active:
            await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "BAD_REQUEST", "message": exc.message}},
        ) from exc
    except Exception as exc:
        if session.is_active:
            await session.rollback()
        log_safe_exception(
            logger,
            f"Unexpected error while recording evidence for workspace {context.workspace_id} (source_type={params.source_type})",
            exc,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": {"code": "INTERNAL_SERVER_ERROR", "message": "An internal server error occurred."}},
        ) from exc
