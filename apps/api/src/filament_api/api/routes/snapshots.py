"""Snapshots API route handlers."""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from filament_api.api.dependencies.auth import get_current_agent_context
from filament_api.core import log_safe_exception
from filament_api.db.session import get_db
from filament_api.schemas.snapshot import RecordSnapshotParams, SnapshotResponse
from filament_api.services.context import TrustedContext
from filament_api.services.exceptions import (
    FilamentDomainError,
    UnauthorizedActorError,
    ValidationDomainError,
)
from filament_api.services.snapshot import SnapshotService

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/snapshots",
    response_model=SnapshotResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record Environment Snapshot",
    description=(
        "Records an immutable environment snapshot capturing file digests, package versions, "
        "and runtime facts with cryptographic actor attribution and atomic audit logging."
    ),
    response_description="Newly recorded environment snapshot",
)
async def record_snapshot(
    params: RecordSnapshotParams,
    context: TrustedContext = Depends(get_current_agent_context),
    session: AsyncSession = Depends(get_db),
) -> SnapshotResponse:
    """Ingest an immutable environment snapshot bound to the caller's verified workspace."""
    try:
        snapshot = await SnapshotService.record_snapshot(
            session=session,
            context=context,
            params=params,
        )

        # Prepare and validate response model representation BEFORE committing
        response = SnapshotResponse.model_validate(snapshot)

        # Explicit endpoint-owned commit
        await session.commit()

        return response
    except UnauthorizedActorError as exc:
        if session.is_active:
            await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": {"code": "FORBIDDEN", "message": exc.message}},
        ) from exc
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
            f"Unexpected error while recording snapshot for workspace {context.workspace_id} (source_ref={params.source_ref})",
            exc,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": {"code": "INTERNAL_SERVER_ERROR", "message": "An internal server error occurred."}},
        ) from exc

