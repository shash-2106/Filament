"""Snapshot domain service for ingesting immutable environment captures."""

from datetime import datetime, timezone
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from filament_api.models.snapshot import EnvironmentSnapshot
from filament_api.schemas.snapshot import RecordSnapshotParams, SnapshotData
from filament_api.services.audit import record_audit_event
from filament_api.services.context import TrustedContext
from filament_api.services.exceptions import UnauthorizedActorError, ValidationDomainError


class SnapshotService:
    """Domain service managing the ingestion of immutable environment snapshots."""

    @staticmethod
    async def record_snapshot(
        session: AsyncSession,
        context: TrustedContext,
        params: RecordSnapshotParams,
    ) -> EnvironmentSnapshot:
        """Ingest an immutable environment snapshot with strict validation and atomic audit logging.

        Stages both the EnvironmentSnapshot entity and its corresponding AuditEvent atomically
        within the provided AsyncSession. Does not commit.
        """
        # Enforce agent authentication
        if not context.is_agent:
            raise UnauthorizedActorError("Environment snapshots must be collected and submitted by an authorized agent.")

        # Enforce trust boundary: an agent client cannot self-promote to independently_verified
        if params.verification_level == "independently_verified" and params.source_type == "agent_client":
            raise ValidationDomainError(
                "Agent-reported snapshots cannot declare 'independently_verified' provenance."
            )

        data: SnapshotData = (
            params.snapshot_data
            if isinstance(params.snapshot_data, SnapshotData)
            else SnapshotData.model_validate(params.snapshot_data)
        )

        # Invariant: A path cannot be both present and unreadable
        overlap = set(data.files.keys()) & set(data.unreadable_paths)
        if overlap:
            raise ValidationDomainError(
                f"Snapshot data is internally inconsistent: path(s) {sorted(overlap)} appear in both files and unreadable_paths."
            )

        # Invariant: Scope consistency
        if params.scan_scope == "full_repository":
            if "." not in data.scanned_roots:
                raise ValidationDomainError(
                    "Full repository scan scope requires repository root marker '.' in scanned_roots."
                )
        elif params.scan_scope == "selective":
            if not data.scanned_roots:
                raise ValidationDomainError(
                    "Selective scan scope requires at least one declared scanned root path."
                )

        snapshot_id = params.snapshot_id or uuid.uuid4()
        dumped_data = data.model_dump()

        snapshot = EnvironmentSnapshot(
            id=snapshot_id,
            workspace_id=context.workspace_id,
            collected_by_agent=context.actor_id,
            source_type=params.source_type,
            verification_level=params.verification_level,
            source_ref=params.source_ref,
            scan_scope=params.scan_scope,
            snapshot_data=dumped_data,
            created_at=datetime.now(timezone.utc),
        )
        session.add(snapshot)

        # Atomic Audit Trail recording
        await record_audit_event(
            session=session,
            context=context,
            event_type="SNAPSHOT_RECORDED",
            target_type="environment_snapshot",
            target_id=snapshot.id,
            payload={
                "source_ref": params.source_ref,
                "source_type": params.source_type,
                "verification_level": params.verification_level,
                "scan_scope": params.scan_scope,
                "packages_scope": data.packages_scope,
                "runtime_scope": data.runtime_scope,
                "file_count": len(data.files),
                "unreadable_count": len(data.unreadable_paths),
                "package_count": len(data.packages),
                "runtime_fact_count": len(data.runtime),
                "scanned_roots": data.scanned_roots,
            },
        )

        await session.flush()
        return snapshot

