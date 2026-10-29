"""Claim domain service for managing assertions and provenance linkages."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from filament_api.models.claim import Claim, ClaimEvidence
from filament_api.models.evidence import Evidence
from filament_api.schemas.claim import CreateClaimParams, LinkEvidenceParams
from filament_api.services.audit import record_audit_event
from filament_api.services.context import TrustedContext
from filament_api.services.exceptions import (
    DuplicateLinkError,
    EntityNotFoundError,
    WorkspaceMismatchError,
)


class ClaimService:
    """Domain service managing governed memory claims and provenance links."""

    @staticmethod
    async def create_claim(
        session: AsyncSession,
        context: TrustedContext,
        params: CreateClaimParams,
    ) -> Claim:
        """Create a new governed claim with actor attribution and atomic audit event.

        Validates caller attribution against the trusted context and stages
        the Claim and AuditEvent within the active transaction.
        """
        agent_id = context.resolve_agent_id_for_claim(params.agent_id)
        claim_id = params.claim_id or uuid.uuid4()

        claim = Claim(
            id=claim_id,
            workspace_id=context.workspace_id,
            agent_id=agent_id,
            claim_type=params.claim_type,
            subject=params.subject,
            predicate=params.predicate,
            object_value=params.object_value,
            raw_statement=params.raw_statement,
            scope=params.scope,
            status=params.status,
            confidence=params.confidence,
        )
        session.add(claim)

        # Atomic Audit Trail recording
        await record_audit_event(
            session=session,
            context=context,
            event_type="CLAIM_CREATED",
            target_type="claim",
            target_id=claim.id,
            payload={
                "claim_type": params.claim_type,
                "scope": params.scope,
                "status": params.status,
                "subject": params.subject,
                "predicate": params.predicate,
                "confidence": str(params.confidence),
                "agent_id": str(agent_id),
            },
        )

        await session.flush()
        return claim

    @staticmethod
    async def link_evidence(
        session: AsyncSession,
        context: TrustedContext,
        params: LinkEvidenceParams,
    ) -> ClaimEvidence:
        """Link an evidence record to a claim with support polarity and confidence weighting.

        Enforces strict workspace isolation across both entities and prevents duplicate links.
        Stages the ClaimEvidence junction and an AuditEvent atomically.
        """
        # Validate Claim exists and belongs to context workspace
        claim_stmt = select(Claim).where(Claim.id == params.claim_id)
        claim = await session.scalar(claim_stmt)
        if claim is None:
            raise EntityNotFoundError("Claim", params.claim_id)
        if claim.workspace_id != context.workspace_id:
            raise WorkspaceMismatchError(
                f"Claim '{params.claim_id}' belongs to workspace '{claim.workspace_id}', "
                f"which does not match caller workspace '{context.workspace_id}'."
            )

        # Validate Evidence exists and belongs to context workspace
        evidence_stmt = select(Evidence).where(Evidence.id == params.evidence_id)
        evidence = await session.scalar(evidence_stmt)
        if evidence is None:
            raise EntityNotFoundError("Evidence", params.evidence_id)
        if evidence.workspace_id != context.workspace_id:
            raise WorkspaceMismatchError(
                f"Evidence '{params.evidence_id}' belongs to workspace '{evidence.workspace_id}', "
                f"which does not match caller workspace '{context.workspace_id}'."
            )

        # Check for existing link
        link_stmt = select(ClaimEvidence).where(
            ClaimEvidence.claim_id == params.claim_id,
            ClaimEvidence.evidence_id == params.evidence_id,
        )
        existing_link = await session.scalar(link_stmt)
        if existing_link is not None:
            raise DuplicateLinkError(params.claim_id, params.evidence_id)

        # Create link
        link = ClaimEvidence(
            workspace_id=context.workspace_id,
            claim_id=params.claim_id,
            evidence_id=params.evidence_id,
            support_type=params.support_type,
            confidence_weight=params.confidence_weight,
            extraction_notes=params.extraction_notes,
        )
        session.add(link)

        # Atomic Audit Trail recording
        await record_audit_event(
            session=session,
            context=context,
            event_type="EVIDENCE_LINKED",
            target_type="claim_evidence",
            target_id=params.claim_id,
            payload={
                "claim_id": str(params.claim_id),
                "evidence_id": str(params.evidence_id),
                "support_type": params.support_type,
                "confidence_weight": str(params.confidence_weight),
            },
        )

        await session.flush()
        return link

