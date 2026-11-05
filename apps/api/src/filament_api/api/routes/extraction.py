"""API routes for AI-assisted candidate memory extraction and approval."""

from typing import Annotated
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from filament_api.api.dependencies.auth import get_current_agent_context
from filament_api.db.session import get_db
from filament_api.schemas.extraction import (
    ApproveCandidateRequest,
    ApproveCandidateResponse,
    ExtractMemoriesRequest,
    ExtractMemoriesResponse,
    ExtractionEstimateRequest,
    ExtractionEstimateResponse,
)
from filament_api.services.context import TrustedContext
from filament_api.services.meta_api.exceptions import (
    BudgetExceededError,
    ConcurrencyLimitExceededError,
    MaxRequestCostExceededError,
    MetaApiDisabledError,
    MetaApiKeyMissingError,
    MetaApiNoUsableOutputError,
    MetaApiProviderError,
    MetaApiTimeoutError,
    TokenLimitExceededError,
    UnresolvedSpendingUncertaintyError,
)
from filament_api.services.meta_api.extraction import MemoryExtractionService

router = APIRouter(prefix="/memory-extraction", tags=["Memory Extraction"])


@router.post(
    "/estimate",
    response_model=ExtractionEstimateResponse,
    summary="Preview token estimation and maximum cost before extraction",
)
async def estimate_extraction(
    request: ExtractionEstimateRequest,
    context: Annotated[TrustedContext, Depends(get_current_agent_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> ExtractionEstimateResponse:
    """Calculates estimated tokens and worst-case ceiling cost for transcript excerpt."""
    service = MemoryExtractionService(session=session)
    return await service.get_estimate(request.transcript)


@router.post(
    "/extract",
    response_model=ExtractMemoriesResponse,
    summary="Extract candidate memories from agent conversation excerpt",
)
async def extract_memories(
    request: ExtractMemoriesRequest,
    context: Annotated[TrustedContext, Depends(get_current_agent_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> ExtractMemoriesResponse:
    """Executes bounded model extraction via MetaModelGateway with human review."""
    service = MemoryExtractionService(session=session)
    try:
        return await service.extract_candidates(
            workspace_id=context.workspace_id,
            request=request,
        )
    except MetaApiDisabledError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
        )
    except MetaApiKeyMissingError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Meta API gateway is not configured with an API key.",
        )
    except (BudgetExceededError, MaxRequestCostExceededError) as e:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Budget limit reached: {str(e)}",
        )
    except ConcurrencyLimitExceededError as e:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(e),
        )
    except UnresolvedSpendingUncertaintyError as e:
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail=str(e),
        )
    except TokenLimitExceededError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except MetaApiNoUsableOutputError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Extraction failed: {str(e)}",
        )
    except (MetaApiProviderError, MetaApiTimeoutError) as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Provider error: {str(e)}",
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )


@router.post(
    "/approve",
    response_model=ApproveCandidateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Approve and persist a candidate memory into governed storage",
)
async def approve_candidate(
    request: ApproveCandidateRequest,
    context: Annotated[TrustedContext, Depends(get_current_agent_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> ApproveCandidateResponse:
    """Persists a human-approved candidate memory with evidence and optional conditions."""
    service = MemoryExtractionService(session=session)
    return await service.approve_candidate(context=context, request=request)
