"""Evidence domain service for ingesting immutable source snapshots."""

from datetime import datetime, timezone
import hashlib
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from filament_api.models.evidence import Evidence
from filament_api.schemas.evidence import RecordEvidenceParams
from filament_api.services.audit import record_audit_event
from filament_api.services.context import TrustedContext
from filament_api.services.exceptions import ValidationDomainError


class EvidenceService:
    """Domain service managing the ingestion of immutable evidence."""

    @staticmethod
    async def record_evidence(
        session: AsyncSession,
        context: TrustedContext,
        params: RecordEvidenceParams,
    ) -> Evidence:
        """Record an immutable evidence record with provenance attribution and audit logging.

        Stages both the Evidence entity and its corresponding AuditEvent atomically
        within the provided AsyncSession. Does not commit.
        """
        # Validate or calculate SHA-256 hash
        computed_hash = hashlib.sha256(params.raw_snippet.encode("utf-8")).hexdigest()
        if params.content_hash is not None and params.content_hash.lower() != computed_hash.lower():
            raise ValidationDomainError(
                f"Supplied content_hash '{params.content_hash}' does not match "
                f"computed hash '{computed_hash}' for raw snippet."
            )

        # Attribution mapping based on trusted context
        collected_by_agent = context.actor_id if context.is_agent else None
        collected_by_user = context.actor_id if context.is_user else None

        evidence_id = params.evidence_id or uuid.uuid4()
        evidence = Evidence(
            id=evidence_id,
            workspace_id=context.workspace_id,
            source_type=params.source_type,
            source_uri=params.source_uri,
            content_hash=computed_hash,
            raw_snippet=params.raw_snippet,
            collected_by_agent=collected_by_agent,
            collected_by_user=collected_by_user,
            metadata_=params.metadata,
            created_at=datetime.now(timezone.utc),
        )
        session.add(evidence)

        # Atomic Audit Trail recording
        await record_audit_event(
            session=session,
            context=context,
            event_type="EVIDENCE_RECORDED",
            target_type="evidence",
            target_id=evidence.id,
            payload={
                "source_type": params.source_type,
                "source_uri": params.source_uri,
                "content_hash": computed_hash,
                "collected_by_agent": str(collected_by_agent) if collected_by_agent else None,
                "collected_by_user": str(collected_by_user) if collected_by_user else None,
            },
        )

        await session.flush()
        return evidence

