"""Claims API route handlers."""

import logging
from typing import List, Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from filament_api.api.dependencies.auth import get_current_agent_context
from filament_api.core import log_safe_exception
from filament_api.db.session import get_db
from filament_api.schemas.claim import (
    ClaimDetailResponse,
    ClaimEvidenceResponse,
    ClaimRelationResponse,
    ClaimResponse,
    CreateClaimParams,
    CreateDependencyRequest,
    CreateRelationParams,
    CreateRelationRequest,
    LinkEvidenceParams,
    LinkEvidenceRequest,
    LinkedEvidenceResponse,
    SupersedeClaimRequest,
)
from filament_api.schemas.condition import (
    ConditionSetResponse,
    EstablishConditionsParams,
    ReverifyClaimParams,
    ReverifyClaimResponse,
)
from filament_api.schemas.evaluation import (
    ClaimEvaluationResponse,
    EvaluateClaimConditionsRequest,
)
from filament_api.services.claim import ClaimService
from filament_api.services.condition import ConditionService
from filament_api.services.evaluation import EvaluationService
from filament_api.services.context import TrustedContext
from filament_api.services.exceptions import (
    ConditionSnapshotMismatchError,
    ConditionsAlreadyEstablishedError,
    CriticalConditionRequiredError,
    CyclicRelationError,
    DuplicateLinkError,
    DuplicateRelationError,
    EntityNotFoundError,
    FilamentDomainError,
    InvalidClaimStateError,
    PathValidationError,
    StaleConditionVersionError,
    UnauthorizedActorError,
    ValidationDomainError,
    WorkspaceMismatchError,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/claims",
    response_model=ClaimResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Memory Claim",
    description=(
        "Asserts an atomic, governed fact or recommendation in memory with "
        "cryptographic actor attribution and atomic audit trail logging."
    ),
    response_description="Newly created memory claim",
)
async def create_claim(
    params: CreateClaimParams,
    context: TrustedContext = Depends(get_current_agent_context),
    session: AsyncSession = Depends(get_db),
) -> ClaimResponse:
    """Create a new governed claim bound to the caller's verified workspace and agent."""
    try:
        claim = await ClaimService.create_claim(
            session=session,
            context=context,
            params=params,
        )
        # Prepare and validate response model representation BEFORE committing
        # This guarantees response serialization errors do not occur after a successful commit.
        response = ClaimResponse.model_validate(claim)

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
            f"Unexpected error while creating claim for workspace {context.workspace_id} (subject={params.subject}, predicate={params.predicate})",
            exc,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": {"code": "INTERNAL_SERVER_ERROR", "message": "An internal server error occurred."}},
        ) from exc


@router.get(
    "/claims",
    response_model=List[ClaimResponse],
    status_code=status.HTTP_200_OK,
    summary="List Claims",
    description="Retrieves a list of claims in the caller's workspace, filtered by scope visibility.",
)
async def list_claims(
    context: TrustedContext = Depends(get_current_agent_context),
    session: AsyncSession = Depends(get_db),
    status_filter: Optional[str] = Query(default=None, alias="status"),
    claim_type: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> List[ClaimResponse]:
    """Retrieve claims in the caller's workspace with optional filtering."""
    try:
        claims = await ClaimService.list_claims(
            session=session,
            context=context,
            status=status_filter,
            claim_type=claim_type,
            limit=limit,
            offset=offset,
        )
        return [ClaimResponse.model_validate(c) for c in claims]
    except Exception as exc:
        log_safe_exception(
            logger=logger,
            message=f"Unexpected error listing claims in workspace {context.workspace_id}",
            exc=exc,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": {"code": "INTERNAL_SERVER_ERROR", "message": "An internal server error occurred."}},
        ) from exc


@router.get(
    "/claims/{claim_id}",
    response_model=ClaimDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve Claim & Provenance",
    description=(
        "Fetches a claim and its linked evidence provenance chain within the "
        "authenticated tenant boundary, enforcing scope visibility."
    ),
    response_description="Claim details and linked evidence provenance records",
)
async def get_claim(
    claim_id: uuid.UUID,
    context: TrustedContext = Depends(get_current_agent_context),
    session: AsyncSession = Depends(get_db),
) -> ClaimDetailResponse:
    """Retrieve an individual claim with linked evidence provenance within tenant scope."""
    try:
        claim, links = await ClaimService.get_claim_with_evidence(
            session=session,
            context=context,
            claim_id=claim_id,
        )

        evidence_items = [
            LinkedEvidenceResponse(
                evidence_id=link.evidence_id,
                support_type=link.support_type,
                confidence_weight=link.confidence_weight,
                extraction_notes=link.extraction_notes,
                source_type=getattr(getattr(link, "evidence", None), "source_type", None),
                source_uri=getattr(getattr(link, "evidence", None), "source_uri", None),
                raw_snippet=getattr(getattr(link, "evidence", None), "raw_snippet", None),
                content_hash=getattr(getattr(link, "evidence", None), "content_hash", None),
                created_at=link.created_at,
            )
            for link in links
        ]

        response = ClaimDetailResponse(
            claim=ClaimResponse.model_validate(claim),
            evidence=evidence_items,
            provenance=evidence_items,
        )
        return response
    except EntityNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "NOT_FOUND", "message": exc.message}},
        ) from exc
    except WorkspaceMismatchError as exc:
        # Defensive isolation: return 404 instead of 403 to prevent cross-tenant enumeration
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "NOT_FOUND", "message": "Resource not found."}},
        ) from exc
    except UnauthorizedActorError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": {"code": "FORBIDDEN", "message": exc.message}},
        ) from exc
    except ValidationDomainError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"error": {"code": "VALIDATION_ERROR", "message": exc.message}},
        ) from exc
    except FilamentDomainError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "BAD_REQUEST", "message": exc.message}},
        ) from exc
    except Exception as exc:
        log_safe_exception(
            logger,
            f"Unexpected error retrieving claim {claim_id} for workspace {context.workspace_id}",
            exc,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": {"code": "INTERNAL_SERVER_ERROR", "message": "An internal server error occurred."}},
        ) from exc


@router.post(
    "/claims/{claim_id}/evidence",
    response_model=ClaimEvidenceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Link Evidence to Claim",
    description=(
        "Associates an existing evidence snapshot with a claim, specifying support "
        "polarity (supports, refutes, mentions) and confidence weighting."
    ),
    response_description="Newly created claim-evidence provenance link",
)
async def link_evidence_to_claim(
    claim_id: uuid.UUID,
    payload: LinkEvidenceRequest,
    context: TrustedContext = Depends(get_current_agent_context),
    session: AsyncSession = Depends(get_db),
) -> ClaimEvidenceResponse:
    """Link an evidence record to a claim within the authenticated workspace."""
    try:
        params = LinkEvidenceParams(
            claim_id=claim_id,
            evidence_id=payload.evidence_id,
            support_type=payload.support_type,
            confidence_weight=payload.confidence_weight,
            extraction_notes=payload.extraction_notes,
        )
        link = await ClaimService.link_evidence(
            session=session,
            context=context,
            params=params,
        )
        # Prepare and validate response model representation BEFORE committing
        response = ClaimEvidenceResponse.model_validate(link)

        # Explicit endpoint-owned commit
        await session.commit()

        return response
    except EntityNotFoundError as exc:
        if session.is_active:
            await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "NOT_FOUND", "message": exc.message}},
        ) from exc
    except WorkspaceMismatchError as exc:
        if session.is_active:
            await session.rollback()
        # Defensive isolation: return 404 instead of 403 to prevent cross-tenant enumeration
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "NOT_FOUND", "message": "Resource not found."}},
        ) from exc
    except DuplicateLinkError as exc:
        if session.is_active:
            await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": {"code": "CONFLICT", "message": exc.message}},
        ) from exc
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
            f"Unexpected error linking evidence {payload.evidence_id} to claim {claim_id} for workspace {context.workspace_id}",
            exc,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": {"code": "INTERNAL_SERVER_ERROR", "message": "An internal server error occurred."}},
        ) from exc


@router.post(
    "/claims/{claim_id}/relations",
    response_model=ClaimRelationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Claim Relationship",
    description=(
        "Creates a directed semantic relationship between claims in the authenticated workspace. "
        "Directions: "
        "- 'supersedes': {claim_id} (newer replacement) supersedes target_claim_id (older claim). "
        "- 'depends_on': {claim_id} (dependent recommendation) depends on target_claim_id (prerequisite). "
        "- 'contradicts': {claim_id} contradicts target_claim_id. "
        "- 'corroborates': {claim_id} corroborates target_claim_id."
    ),
    response_description="Newly created claim relation and affected cascade claim IDs",
)
async def create_claim_relation(
    claim_id: uuid.UUID,
    payload: CreateRelationRequest,
    context: TrustedContext = Depends(get_current_agent_context),
    session: AsyncSession = Depends(get_db),
) -> ClaimRelationResponse:
    """Create a directed relation edge between claims, enforcing DAG acyclicity and invalidation cascade."""
    try:
        params = CreateRelationParams(
            source_claim_id=claim_id,
            target_claim_id=payload.target_claim_id,
            relation_type=payload.relation_type,
            rationale=payload.rationale,
        )
        relation, affected_claims = await ClaimService.create_relation(
            session=session,
            context=context,
            params=params,
        )
        response = ClaimRelationResponse(
            id=relation.id,
            workspace_id=relation.workspace_id,
            source_claim_id=relation.source_claim_id,
            target_claim_id=relation.target_claim_id,
            relation_type=relation.relation_type,
            rationale=relation.rationale,
            created_by_agent=relation.created_by_agent,
            created_at=relation.created_at,
            affected_claim_ids=[c.id for c in affected_claims],
        )

        await session.commit()
        return response
    except EntityNotFoundError as exc:
        if session.is_active:
            await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "NOT_FOUND", "message": exc.message}},
        ) from exc
    except WorkspaceMismatchError as exc:
        if session.is_active:
            await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "NOT_FOUND", "message": "Resource not found."}},
        ) from exc
    except (DuplicateRelationError, DuplicateLinkError) as exc:
        if session.is_active:
            await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": {"code": "CONFLICT", "message": exc.message}},
        ) from exc
    except CyclicRelationError as exc:
        if session.is_active:
            await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"error": {"code": "CYCLIC_RELATION", "message": exc.message}},
        ) from exc
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
            f"Unexpected error creating relation '{payload.relation_type}' from claim {claim_id} to {payload.target_claim_id} for workspace {context.workspace_id}",
            exc,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": {"code": "INTERNAL_SERVER_ERROR", "message": "An internal server error occurred."}},
        ) from exc


@router.post(
    "/claims/{claim_id}/supersede",
    response_model=ClaimRelationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Supersede Older Claim",
    description=(
        "Records that the newer claim {claim_id} supersedes the older claim target_claim_id. "
        "Transitions the older claim to 'superseded', cascades invalidation to any claims "
        "depending on it (marking them 'needs_review'), and emits audit events."
    ),
    response_description="Newly created supersession relation and affected cascade claim IDs",
)
async def supersede_claim(
    claim_id: uuid.UUID,
    payload: SupersedeClaimRequest,
    context: TrustedContext = Depends(get_current_agent_context),
    session: AsyncSession = Depends(get_db),
) -> ClaimRelationResponse:
    """Supersede an older target claim from a newer source claim."""
    rel_req = CreateRelationRequest(
        target_claim_id=payload.target_claim_id,
        relation_type="supersedes",
        rationale=payload.rationale,
    )
    return await create_claim_relation(
        claim_id=claim_id,
        payload=rel_req,
        context=context,
        session=session,
    )


@router.post(
    "/claims/{claim_id}/dependencies",
    response_model=ClaimRelationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Prerequisite Dependency",
    description=(
        "Records that dependent claim {claim_id} depends on prerequisite claim target_claim_id. "
        "Validates cycle freedom and tenant isolation."
    ),
    response_description="Newly created dependency relation",
)
async def create_claim_dependency(
    claim_id: uuid.UUID,
    payload: CreateDependencyRequest,
    context: TrustedContext = Depends(get_current_agent_context),
    session: AsyncSession = Depends(get_db),
) -> ClaimRelationResponse:
    """Record that source claim depends on target prerequisite claim."""
    rel_req = CreateRelationRequest(
        target_claim_id=payload.target_claim_id,
        relation_type="depends_on",
        rationale=payload.rationale,
    )
    return await create_claim_relation(
        claim_id=claim_id,
        payload=rel_req,
        context=context,
        session=session,
    )


@router.post(
    "/claims/{claim_id}/conditions",
    response_model=ConditionSetResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Establish Initial Condition Set",
    description=(
        "Establishes the initial immutable versioned environment prerequisite condition set (v1) "
        "for an unconditioned claim, evaluating and verifying all proposed conditions against an "
        "establishing environment snapshot in the same workspace."
    ),
    response_description="Newly established condition set and initial verification record",
)
async def establish_claim_conditions(
    claim_id: uuid.UUID,
    payload: EstablishConditionsParams,
    context: TrustedContext = Depends(get_current_agent_context),
    session: AsyncSession = Depends(get_db),
) -> ConditionSetResponse:
    """Establish initial environment prerequisite conditions for an unconditioned claim."""
    try:
        condition_set = await ConditionService.establish_initial_conditions(
            session=session,
            context=context,
            claim_id=claim_id,
            params=payload,
        )

        # Prepare and validate response model representation BEFORE committing
        response = ConditionSetResponse.model_validate(condition_set)

        # Explicit endpoint-owned commit
        await session.commit()

        return response
    except EntityNotFoundError as exc:
        if session.is_active:
            await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "NOT_FOUND", "message": exc.message}},
        ) from exc
    except WorkspaceMismatchError as exc:
        if session.is_active:
            await session.rollback()
        # Defensive isolation: return 404 instead of 403 to prevent cross-tenant enumeration
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "NOT_FOUND", "message": "Resource not found."}},
        ) from exc
    except ConditionsAlreadyEstablishedError as exc:
        if session.is_active:
            await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": {"code": "CONDITIONS_ALREADY_ESTABLISHED", "message": exc.message}},
        ) from exc
    except ConditionSnapshotMismatchError as exc:
        if session.is_active:
            await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"error": {"code": "CONDITION_SNAPSHOT_MISMATCH", "message": exc.message}},
        ) from exc
    except (ValidationDomainError, PathValidationError, CriticalConditionRequiredError) as exc:
        if session.is_active:
            await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"error": {"code": "VALIDATION_ERROR", "message": exc.message}},
        ) from exc
    except UnauthorizedActorError as exc:
        if session.is_active:
            await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": {"code": "FORBIDDEN", "message": exc.message}},
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
            f"Unexpected error establishing conditions for claim {claim_id} in workspace {context.workspace_id}",
            exc,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": {"code": "INTERNAL_SERVER_ERROR", "message": "An internal server error occurred."}},
        ) from exc


@router.get(
    "/claims/{claim_id}/conditions",
    response_model=ConditionSetResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve Active Condition Set",
    description="Fetches the active versioned condition set for a claim.",
)
async def get_claim_conditions(
    claim_id: uuid.UUID,
    context: TrustedContext = Depends(get_current_agent_context),
    session: AsyncSession = Depends(get_db),
) -> ConditionSetResponse:
    """Retrieve the currently active condition set for a claim."""
    try:
        from sqlalchemy import select
        from filament_api.models.claim import Claim
        from filament_api.models.condition import ClaimConditionSet, ClaimCondition
        from filament_api.schemas.condition import ConditionResponse

        claim_stmt = select(Claim).where(Claim.id == claim_id, Claim.workspace_id == context.workspace_id)
        claim_res = await session.execute(claim_stmt)
        claim = claim_res.scalar_one_or_none()
        if not claim:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Claim not found")

        if claim.active_condition_version is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Claim has no active condition set")

        cs_stmt = (
            select(ClaimConditionSet)
            .where(
                ClaimConditionSet.workspace_id == context.workspace_id,
                ClaimConditionSet.claim_id == claim_id,
                ClaimConditionSet.version == claim.active_condition_version,
            )
        )
        cs_res = await session.execute(cs_stmt)
        cs = cs_res.scalar_one_or_none()
        if not cs:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Condition set not found")

        conds_stmt = (
            select(ClaimCondition)
            .where(
                ClaimCondition.workspace_id == context.workspace_id,
                ClaimCondition.claim_id == claim_id,
                ClaimCondition.condition_set_version == cs.version,
            )
            .order_by(ClaimCondition.created_at.asc())
        )
        conds_res = await session.execute(conds_stmt)
        conds = conds_res.scalars().all()

        resp = ConditionSetResponse(
            id=cs.id,
            workspace_id=cs.workspace_id,
            claim_id=cs.claim_id,
            version=cs.version,
            based_on_snapshot_id=cs.based_on_snapshot_id,
            established_by_agent=cs.established_by_agent,
            rationale=cs.rationale,
            created_at=cs.created_at,
            conditions=[ConditionResponse.model_validate(c) for c in conds],
        )
        return resp
    except HTTPException:
        raise
    except Exception as exc:
        log_safe_exception(logger, f"Error getting conditions for claim {claim_id}", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": {"code": "INTERNAL_SERVER_ERROR", "message": "An internal server error occurred."}},
        ) from exc


@router.post(
    "/claims/{claim_id}/evaluate",
    response_model=ClaimEvaluationResponse,
    status_code=status.HTTP_200_OK,
    summary="Evaluate Claim Conditions against Snapshot",
    description=(
        "Transiently evaluates whether a claim's active prerequisite conditions "
        "still hold against an environment snapshot. Strictly read-only: does not "
        "mutate claim state, record verifications, or write audit events."
    ),
    response_description="Evaluation outcome and individual condition results",
)
async def evaluate_claim_conditions(
    claim_id: uuid.UUID,
    payload: EvaluateClaimConditionsRequest,
    context: TrustedContext = Depends(get_current_agent_context),
    session: AsyncSession = Depends(get_db),
) -> ClaimEvaluationResponse:
    """Evaluate a claim's conditions against a snapshot in the caller workspace."""
    try:
        response = await EvaluationService.evaluate_claim_conditions(
            session=session,
            context=context,
            claim_id=claim_id,
            snapshot_id=payload.snapshot_id,
        )
        # Strictly read-only: no session.commit() or flush() is invoked.
        return response
    except EntityNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "NOT_FOUND", "message": exc.message}},
        ) from exc
    except WorkspaceMismatchError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "NOT_FOUND", "message": "Resource not found."}},
        ) from exc
    except UnauthorizedActorError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": {"code": "FORBIDDEN", "message": exc.message}},
        ) from exc
    except ValidationDomainError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"error": {"code": "VALIDATION_ERROR", "message": exc.message}},
        ) from exc
    except FilamentDomainError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "BAD_REQUEST", "message": exc.message}},
        ) from exc
    except Exception as exc:
        log_safe_exception(
            logger,
            f"Unexpected error evaluating conditions for claim {claim_id} against snapshot {payload.snapshot_id}",
            exc,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": {"code": "INTERNAL_SERVER_ERROR", "message": "An internal server error occurred."}},
        ) from exc


@router.post(
    "/claims/{claim_id}/reverify",
    response_model=ReverifyClaimResponse,
    status_code=status.HTTP_200_OK,
    summary="Reverify Claim Conditions or Adopt Replacement Condition Set",
    description=(
        "Formally reverifies a claim against a newly recorded environment snapshot. "
        "Supports verifying against active conditions or explicitly adopting a validated replacement condition set. "
        "Atomically persists a formal verification audit record and stages an immutable audit event."
    ),
    response_description="Persisted verification record and condition outcome",
)
async def reverify_claim(
    claim_id: uuid.UUID,
    payload: ReverifyClaimParams,
    context: TrustedContext = Depends(get_current_agent_context),
    session: AsyncSession = Depends(get_db),
) -> ReverifyClaimResponse:
    """Reverify claim conditions or adopt new conditions within the authenticated workspace."""
    try:
        verification_data = await ConditionService.reverify_claim(
            session=session,
            context=context,
            claim_id=claim_id,
            params=payload,
        )
        # Pre-commit DTO validation: guarantees response shape validity before persisting
        response = ReverifyClaimResponse.model_validate(verification_data)

        # Atomic unit-of-work commit
        await session.commit()
        return response

    except EntityNotFoundError as exc:
        if session.is_active:
            await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "NOT_FOUND", "message": exc.message}},
        ) from exc
    except WorkspaceMismatchError as exc:
        if session.is_active:
            await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "NOT_FOUND", "message": "Resource not found."}},
        ) from exc
    except UnauthorizedActorError as exc:
        if session.is_active:
            await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": {"code": "FORBIDDEN", "message": exc.message}},
        ) from exc
    except StaleConditionVersionError as exc:
        if session.is_active:
            await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": {"code": "STALE_CONDITION_VERSION", "message": exc.message}},
        ) from exc
    except ConditionSnapshotMismatchError as exc:
        if session.is_active:
            await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"error": {"code": "CONDITION_SNAPSHOT_MISMATCH", "message": exc.message}},
        ) from exc
    except InvalidClaimStateError as exc:
        if session.is_active:
            await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"error": {"code": "INVALID_CLAIM_STATE", "message": exc.message}},
        ) from exc
    except (ValidationDomainError, PathValidationError, CriticalConditionRequiredError) as exc:
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
            f"Unexpected error reverifying claim {claim_id} against snapshot {payload.snapshot_id}",
            exc,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": {"code": "INTERNAL_SERVER_ERROR", "message": "An internal server error occurred."}},
        ) from exc









@router.get(
    "/claim-relations",
    response_model=List[ClaimRelationResponse],
    status_code=status.HTTP_200_OK,
    summary="List Workspace Claim Relations",
    description="Lists directed relationship edges between claims for dependency and DAG visualization.",
)
async def list_claim_relations(
    relation_type: Optional[str] = None,
    context: TrustedContext = Depends(get_current_agent_context),
    session: AsyncSession = Depends(get_db),
) -> List[ClaimRelationResponse]:
    """Retrieve all claim relations in caller's workspace."""
    try:
        from sqlalchemy import select
        from filament_api.models.relation import ClaimRelation

        stmt = select(ClaimRelation).where(ClaimRelation.workspace_id == context.workspace_id)
        if relation_type:
            stmt = stmt.where(ClaimRelation.relation_type == relation_type)
        stmt = stmt.order_by(ClaimRelation.created_at.desc())

        res = await session.execute(stmt)
        relations = res.scalars().all()
        return [
            ClaimRelationResponse(
                id=rel.id,
                workspace_id=rel.workspace_id,
                source_claim_id=rel.source_claim_id,
                target_claim_id=rel.target_claim_id,
                relation_type=rel.relation_type,
                rationale=rel.rationale,
                created_by_agent=rel.created_by_agent,
                created_at=rel.created_at,
                affected_claim_ids=[],
            )
            for rel in relations
        ]
    except Exception as exc:
        log_safe_exception(logger, f"Error listing relations for workspace {context.workspace_id}", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": {"code": "INTERNAL_SERVER_ERROR", "message": "An internal error occurred."}},
        ) from exc
