"""Claim domain service for managing assertions and provenance linkages."""

from collections import deque
from datetime import datetime, timezone
from typing import List, Optional, Set, Tuple
import uuid

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from filament_api.models.claim import Claim, ClaimEvidence
from filament_api.models.evidence import Evidence
from filament_api.models.relation import ClaimRelation
from filament_api.schemas.claim import (
    CreateClaimParams,
    CreateDependencyParams,
    CreateRelationParams,
    LinkEvidenceParams,
    SupersedeClaimParams,
)
from filament_api.services.audit import record_audit_event
from filament_api.services.context import TrustedContext
from filament_api.services.exceptions import (
    CyclicRelationError,
    DuplicateLinkError,
    DuplicateRelationError,
    EntityNotFoundError,
    ValidationDomainError,
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
            version=1,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
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
            created_at=datetime.now(timezone.utc),
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

    @staticmethod
    async def list_claims(
        session: AsyncSession,
        context: TrustedContext,
        status: Optional[str] = None,
        claim_type: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Claim]:
        """List claims in the caller's workspace visible to the caller's scope."""
        stmt = select(Claim).where(Claim.workspace_id == context.workspace_id)
        if status:
            stmt = stmt.where(Claim.status == status)
        if claim_type:
            stmt = stmt.where(Claim.claim_type == claim_type)

        if context.is_agent:
            scope_filter = or_(
                Claim.scope == "workspace",
                and_(
                    Claim.scope.in_(["private", "team"]),
                    Claim.agent_id == context.actor_id,
                ),
            )
        else:
            scope_filter = Claim.scope == "workspace"

        stmt = stmt.where(scope_filter).order_by(Claim.created_at.desc()).limit(limit).offset(offset)
        res = await session.execute(stmt)
        return list(res.scalars().all())

    @staticmethod
    async def get_claim(
        session: AsyncSession,
        context: TrustedContext,
        claim_id: uuid.UUID,
    ) -> Claim:
        """Retrieve an individual claim within the caller workspace, enforcing scope visibility.

        Scope visibility rules:
        - workspace: visible to all authenticated agents in the workspace.
        - team: fails closed (accessible only to the authoring agent, because the schema lacks
                team models or team membership representations).
        - private: accessible only to the authoring agent.

        Nonexistent, cross-workspace, and out-of-scope claims raise EntityNotFoundError
        or WorkspaceMismatchError to prevent tenant resource enumeration.
        """
        claim_stmt = select(Claim).where(Claim.id == claim_id)
        claim = await session.scalar(claim_stmt)
        if claim is None:
            raise EntityNotFoundError("Claim", claim_id)

        if claim.workspace_id != context.workspace_id:
            raise WorkspaceMismatchError(
                f"Claim '{claim_id}' belongs to workspace '{claim.workspace_id}', "
                f"which does not match caller workspace '{context.workspace_id}'."
            )

        # Enforce scope visibility rules
        ClaimService._check_claim_visibility(claim, context)

        return claim

    @staticmethod
    def _check_claim_visibility(claim: Claim, context: TrustedContext) -> None:
        """Enforces scope visibility rules for claims within the workspace."""
        if claim.scope in ("private", "team"):
            # Fail-closed for private and team scopes: accessible only to authoring agent
            if not context.is_agent or claim.agent_id != context.actor_id:
                raise EntityNotFoundError("Claim", claim.id)
        elif claim.scope == "workspace":
            # Visible to all authenticated agents within the matching workspace
            pass
        else:
            # Defensive fail-closed on any unrecognized scope
            raise EntityNotFoundError("Claim", claim.id)

    @staticmethod
    async def get_claim_with_evidence(
        session: AsyncSession,
        context: TrustedContext,
        claim_id: uuid.UUID,
    ) -> tuple[Claim, list[ClaimEvidence]]:
        """Retrieve a claim and its associated evidence provenance within caller scope.

        Enforces workspace boundary isolation and scope visibility.
        Read-only: does NOT stage audit events or mutate database transactions.
        """
        claim = await ClaimService.get_claim(
            session=session,
            context=context,
            claim_id=claim_id,
        )

        links_stmt = (
            select(ClaimEvidence)
            .options(selectinload(ClaimEvidence.evidence))
            .where(
                ClaimEvidence.claim_id == claim_id,
                ClaimEvidence.workspace_id == context.workspace_id,
            )
            .order_by(ClaimEvidence.created_at.asc())
        )
        result = await session.scalars(links_stmt)
        links = list(result.all())

        return claim, links

    @staticmethod
    async def _has_relation_path(
        session: AsyncSession,
        workspace_id: uuid.UUID,
        start_id: uuid.UUID,
        end_id: uuid.UUID,
        relation_type: str,
    ) -> bool:
        """Check if a directed path exists from start_id to end_id along edges of relation_type."""
        if start_id == end_id:
            return True

        stmt = select(ClaimRelation).where(
            ClaimRelation.workspace_id == workspace_id,
            ClaimRelation.relation_type == relation_type,
        )
        result = await session.scalars(stmt)
        relations = result.all()

        adj: dict[uuid.UUID, list[uuid.UUID]] = {}
        for rel in relations:
            adj.setdefault(rel.source_claim_id, []).append(rel.target_claim_id)

        visited = {start_id}
        queue = deque([start_id])

        while queue:
            curr = queue.popleft()
            if curr == end_id:
                return True
            for neighbor in adj.get(curr, []):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)

        return False

    @staticmethod
    async def _cascade_supersession_to_dependents(
        session: AsyncSession,
        context: TrustedContext,
        superseded_claim_id: uuid.UUID,
    ) -> list[Claim]:
        """Find all claims that directly or transitively depend on the superseded claim and transition them to needs_review."""
        stmt = select(ClaimRelation).where(
            ClaimRelation.workspace_id == context.workspace_id,
            ClaimRelation.relation_type == "depends_on",
        )
        result = await session.scalars(stmt)
        relations = result.all()

        # In depends_on relations: source_claim_id depends on target_claim_id (prerequisite).
        # When target_claim_id is superseded, we traverse backwards: from prerequisite to dependent (target -> source).
        reverse_adj: dict[uuid.UUID, list[uuid.UUID]] = {}
        for rel in relations:
            reverse_adj.setdefault(rel.target_claim_id, []).append(rel.source_claim_id)

        visited = {superseded_claim_id}
        queue = deque([superseded_claim_id])
        affected_ids: list[uuid.UUID] = []

        while queue:
            curr = queue.popleft()
            for dep_id in reverse_adj.get(curr, []):
                if dep_id not in visited:
                    visited.add(dep_id)
                    queue.append(dep_id)
                    affected_ids.append(dep_id)

        transitioned_claims: list[Claim] = []
        for dep_id in affected_ids:
            claim_stmt = select(Claim).where(
                Claim.id == dep_id,
                Claim.workspace_id == context.workspace_id,
            )
            dep_claim = await session.scalar(claim_stmt)
            if dep_claim is not None and dep_claim.status == "current":
                old_status = dep_claim.status
                dep_claim.status = "needs_review"
                dep_claim.version += 1
                dep_claim.updated_at = datetime.now(timezone.utc)

                await record_audit_event(
                    session=session,
                    context=context,
                    event_type="DEPENDENCY_INVALIDATED",
                    target_type="claim",
                    target_id=dep_claim.id,
                    payload={
                        "claim_id": str(dep_claim.id),
                        "invalidating_upstream_claim_id": str(superseded_claim_id),
                        "old_status": old_status,
                        "new_status": "needs_review",
                    },
                )
                transitioned_claims.append(dep_claim)

        return transitioned_claims

    @staticmethod
    async def create_relation(
        session: AsyncSession,
        context: TrustedContext,
        params: CreateRelationParams,
    ) -> tuple[ClaimRelation, list[Claim]]:
        """Create a directed relation between two claims in the caller workspace.

        Supports supersedes, depends_on, contradicts, and corroborates.
        Enforces self-relation rejection, tenant isolation, scope visibility,
        duplicate rejection, and directed cycle prevention.
        """
        if params.source_claim_id == params.target_claim_id:
            raise ValidationDomainError("A claim cannot establish a relationship to itself.")

        # Validate source claim exists and belongs to context workspace
        source_stmt = select(Claim).where(Claim.id == params.source_claim_id)
        source_claim = await session.scalar(source_stmt)
        if source_claim is None:
            raise EntityNotFoundError("Claim", params.source_claim_id)
        if source_claim.workspace_id != context.workspace_id:
            raise WorkspaceMismatchError(
                f"Claim '{params.source_claim_id}' belongs to workspace '{source_claim.workspace_id}', "
                f"which does not match caller workspace '{context.workspace_id}'."
            )
        ClaimService._check_claim_visibility(source_claim, context)

        # Validate target claim exists and belongs to context workspace
        target_stmt = select(Claim).where(Claim.id == params.target_claim_id)
        target_claim = await session.scalar(target_stmt)
        if target_claim is None:
            raise EntityNotFoundError("Claim", params.target_claim_id)
        if target_claim.workspace_id != context.workspace_id:
            raise WorkspaceMismatchError(
                f"Claim '{params.target_claim_id}' belongs to workspace '{target_claim.workspace_id}', "
                f"which does not match caller workspace '{context.workspace_id}'."
            )
        ClaimService._check_claim_visibility(target_claim, context)

        # Check for duplicate relation
        dup_stmt = select(ClaimRelation).where(
            ClaimRelation.workspace_id == context.workspace_id,
            ClaimRelation.source_claim_id == params.source_claim_id,
            ClaimRelation.target_claim_id == params.target_claim_id,
            ClaimRelation.relation_type == params.relation_type,
        )
        existing = await session.scalar(dup_stmt)
        if existing is not None:
            raise DuplicateRelationError(
                params.source_claim_id,
                params.target_claim_id,
                params.relation_type,
            )

        # Check cycles for DAG relation types
        if params.relation_type in ("supersedes", "depends_on"):
            has_cycle = await ClaimService._has_relation_path(
                session=session,
                workspace_id=context.workspace_id,
                start_id=params.target_claim_id,
                end_id=params.source_claim_id,
                relation_type=params.relation_type,
            )
            if has_cycle:
                raise CyclicRelationError(
                    params.source_claim_id,
                    params.target_claim_id,
                    params.relation_type,
                )

        transitioned_dependents: list[Claim] = []

        # If superseding: update target claim status and cascade invalidation
        if params.relation_type == "supersedes":
            if target_claim.status != "superseded":
                target_claim.status = "superseded"
                target_claim.version += 1
                target_claim.updated_at = datetime.now(timezone.utc)

            transitioned_dependents = await ClaimService._cascade_supersession_to_dependents(
                session=session,
                context=context,
                superseded_claim_id=target_claim.id,
            )

            await record_audit_event(
                session=session,
                context=context,
                event_type="CLAIM_SUPERSEDED",
                target_type="claim",
                target_id=target_claim.id,
                payload={
                    "old_claim_id": str(params.target_claim_id),
                    "new_claim_id": str(params.source_claim_id),
                    "rationale": params.rationale,
                },
            )

        # Create the relation
        agent_id = context.actor_id if context.is_agent else None
        relation = ClaimRelation(
            id=uuid.uuid4(),
            workspace_id=context.workspace_id,
            source_claim_id=params.source_claim_id,
            target_claim_id=params.target_claim_id,
            relation_type=params.relation_type,
            rationale=params.rationale,
            created_by_agent=agent_id,
            created_at=datetime.now(timezone.utc),
        )
        session.add(relation)

        # Audit event for relation creation
        await record_audit_event(
            session=session,
            context=context,
            event_type="CLAIM_RELATION_CREATED",
            target_type="claim_relation",
            target_id=relation.id,
            payload={
                "source_claim_id": str(params.source_claim_id),
                "target_claim_id": str(params.target_claim_id),
                "relation_type": params.relation_type,
                "rationale": params.rationale,
            },
        )

        await session.flush()
        return relation, transitioned_dependents

    @staticmethod
    async def supersede_claim(
        session: AsyncSession,
        context: TrustedContext,
        params: SupersedeClaimParams,
    ) -> tuple[ClaimRelation, list[Claim]]:
        """Supersede an existing target claim with a new source claim."""
        rel_params = CreateRelationParams(
            source_claim_id=params.source_claim_id,
            target_claim_id=params.target_claim_id,
            relation_type="supersedes",
            rationale=params.rationale,
        )
        return await ClaimService.create_relation(session, context, rel_params)

    @staticmethod
    async def create_dependency(
        session: AsyncSession,
        context: TrustedContext,
        params: CreateDependencyParams,
    ) -> ClaimRelation:
        """Create a dependency where source_claim depends on prerequisite target_claim."""
        rel_params = CreateRelationParams(
            source_claim_id=params.source_claim_id,
            target_claim_id=params.target_claim_id,
            relation_type="depends_on",
            rationale=params.rationale,
        )
        relation, _ = await ClaimService.create_relation(session, context, rel_params)
        return relation

