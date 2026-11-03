"""Condition domain service for establishing versioned environment prerequisite bindings."""

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Union
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from filament_api.models.claim import Claim
from filament_api.models.condition import ClaimCondition, ClaimConditionSet, ClaimVerification
from filament_api.models.snapshot import EnvironmentSnapshot
from filament_api.schemas.condition import (
    ConditionSpec,
    EstablishConditionsParams,
    ReverifyClaimParams,
)
from filament_api.schemas.evaluation import ConditionEvaluationItem
from filament_api.services.audit import record_audit_event
from filament_api.services.canonicalization import canonicalize_path
from filament_api.services.context import TrustedContext
from filament_api.services.exceptions import (
    ConditionSnapshotMismatchError,
    ConditionsAlreadyEstablishedError,
    CriticalConditionRequiredError,
    EntityNotFoundError,
    InvalidClaimStateError,
    StaleConditionVersionError,
    UnauthorizedActorError,
    ValidationDomainError,
    WorkspaceMismatchError,
)


class ConditionStatus(str, Enum):
    """Deterministic outcome states for condition evaluation against a snapshot."""

    SATISFIED = "SATISFIED"
    DRIFTED = "DRIFTED"
    UNCHECKED = "UNCHECKED"


@dataclass(frozen=True)
class ConditionEvaluationResult:
    """Deterministic evaluation outcome for an individual prerequisite condition."""

    status: ConditionStatus
    reason: str
    details: Dict[str, Any]


def evaluate_condition_against_snapshot(
    condition: Union[ConditionSpec, ClaimCondition],
    scan_scope: str,
    snapshot_data: Dict[str, Any],
) -> ConditionEvaluationResult:
    """Deterministically evaluate an individual condition against an environment snapshot.

    Rules strictly follow Step 21C / Step 23 specification:
    - hash_equals:
        - If target_path is in unreadable_paths -> UNCHECKED (PATH_UNREADABLE)
        - If target_path is in files -> compare exact hashes:
            - matches -> SATISFIED (HASH_MATCHES)
            - mismatch -> DRIFTED (CONTENT_HASH_MISMATCH)
        - If target_path is missing:
            - If scan_scope == 'full_repository' -> DRIFTED (FILE_DELETED)
            - If scan_scope == 'selective':
                - If target_path falls under any scanned_roots -> DRIFTED (FILE_DELETED)
                - Else -> UNCHECKED (PATH_NOT_IN_SCAN_SCOPE)
    - version_equals:
        - If target_path not in packages -> DRIFTED (PACKAGE_NOT_FOUND)
        - Else -> exact equality check:
            - matches -> SATISFIED (VERSION_MATCHES)
            - mismatch -> DRIFTED (VERSION_MISMATCH)
    - runtime_equals:
        - If target_path not in runtime -> DRIFTED (RUNTIME_FACT_NOT_FOUND)
        - Else -> exact equality check:
            - matches -> SATISFIED (RUNTIME_FACT_MATCHES)
            - mismatch -> DRIFTED (RUNTIME_FACT_MISMATCH)
    """
    cond_type = condition.condition_type

    if cond_type in ("file_hash", "lockfile_hash"):
        target_path = canonicalize_path(condition.target_path, allow_root_marker=False)
        expected_hash = condition.expected_hash or condition.expected_value.get("hash")
        if not expected_hash:
            raise ValidationDomainError(
                f"Condition for '{target_path}' requires expected_hash or expected_value['hash']."
            )

        files = snapshot_data.get("files", {})
        unreadable = snapshot_data.get("unreadable_paths", [])
        scanned_roots = snapshot_data.get("scanned_roots", [])

        # Case 1: Path is explicitly unreadable
        if target_path in unreadable:
            return ConditionEvaluationResult(
                status=ConditionStatus.UNCHECKED,
                reason="PATH_UNREADABLE",
                details={"target_path": target_path},
            )

        # Case 2: Path is present in snapshot files
        if target_path in files:
            actual_hash = str(files[target_path]).lower()
            if actual_hash == expected_hash.lower():
                return ConditionEvaluationResult(
                    status=ConditionStatus.SATISFIED,
                    reason="HASH_MATCHES",
                    details={"target_path": target_path, "hash": actual_hash},
                )
            return ConditionEvaluationResult(
                status=ConditionStatus.DRIFTED,
                reason="CONTENT_HASH_MISMATCH",
                details={
                    "target_path": target_path,
                    "expected_hash": expected_hash.lower(),
                    "actual_hash": actual_hash,
                },
            )

        # Case 3: Path is absent from files and unreadable
        if scan_scope == "full_repository":
            return ConditionEvaluationResult(
                status=ConditionStatus.DRIFTED,
                reason="FILE_DELETED",
                details={"target_path": target_path, "scan_scope": scan_scope},
            )

        # Selective scan: check if target_path falls under any declared scanned_roots
        is_covered = any(
            root == "." or target_path == root or target_path.startswith(root.rstrip("/") + "/")
            for root in scanned_roots
        )
        if is_covered:
            return ConditionEvaluationResult(
                status=ConditionStatus.DRIFTED,
                reason="FILE_DELETED",
                details={"target_path": target_path, "scanned_roots": scanned_roots},
            )
        return ConditionEvaluationResult(
            status=ConditionStatus.UNCHECKED,
            reason="PATH_NOT_IN_SCAN_SCOPE",
            details={"target_path": target_path, "scanned_roots": scanned_roots},
        )

    elif cond_type == "package_version":
        packages = snapshot_data.get("packages", {})
        packages_scope = snapshot_data.get("packages_scope") or "partial"
        pkg_key = condition.target_path.strip()

        if pkg_key not in packages:
            if packages_scope == "complete":
                return ConditionEvaluationResult(
                    status=ConditionStatus.DRIFTED,
                    reason="PACKAGE_NOT_FOUND",
                    details={"package": pkg_key, "packages_scope": packages_scope},
                )
            return ConditionEvaluationResult(
                status=ConditionStatus.UNCHECKED,
                reason="PACKAGE_NOT_IN_SCAN_SCOPE",
                details={"package": pkg_key, "packages_scope": packages_scope},
            )

        actual = packages[pkg_key]
        actual_ver = actual.get("version", actual) if isinstance(actual, dict) else actual
        expected_ver = (
            condition.expected_value.get("version")
            if "version" in condition.expected_value
            else condition.expected_value.get("value", condition.expected_hash)
        )
        if expected_ver is None:
            raise ValidationDomainError(
                f"Package condition for '{pkg_key}' requires expected_value['version']."
            )

        if str(actual_ver).strip() == str(expected_ver).strip():
            return ConditionEvaluationResult(
                status=ConditionStatus.SATISFIED,
                reason="VERSION_MATCHES",
                details={"package": pkg_key, "version": str(actual_ver)},
            )
        return ConditionEvaluationResult(
            status=ConditionStatus.DRIFTED,
            reason="VERSION_MISMATCH",
            details={
                "package": pkg_key,
                "expected": str(expected_ver).strip(),
                "actual": str(actual_ver).strip(),
            },
        )

    elif cond_type == "runtime_fact":
        runtime = snapshot_data.get("runtime", {})
        runtime_scope = snapshot_data.get("runtime_scope") or "partial"
        fact_key = condition.target_path.strip()

        if fact_key not in runtime:
            if runtime_scope == "complete":
                return ConditionEvaluationResult(
                    status=ConditionStatus.DRIFTED,
                    reason="RUNTIME_FACT_NOT_FOUND",
                    details={"runtime_fact": fact_key, "runtime_scope": runtime_scope},
                )
            return ConditionEvaluationResult(
                status=ConditionStatus.UNCHECKED,
                reason="RUNTIME_FACT_NOT_IN_SCAN_SCOPE",
                details={"runtime_fact": fact_key, "runtime_scope": runtime_scope},
            )

        actual = runtime[fact_key]
        actual_val = actual.get("value", actual) if isinstance(actual, dict) else actual
        expected_val = (
            condition.expected_value.get("value")
            if "value" in condition.expected_value
            else condition.expected_value.get(fact_key, condition.expected_value)
        )

        if actual_val == expected_val or str(actual_val).strip() == str(expected_val).strip():
            return ConditionEvaluationResult(
                status=ConditionStatus.SATISFIED,
                reason="RUNTIME_FACT_MATCHES",
                details={"runtime_fact": fact_key, "value": actual_val},
            )
        return ConditionEvaluationResult(
            status=ConditionStatus.DRIFTED,
            reason="RUNTIME_FACT_MISMATCH",
            details={
                "runtime_fact": fact_key,
                "expected": expected_val,
                "actual": actual_val,
            },
        )

    raise ValidationDomainError(f"Unsupported condition type '{cond_type}'.")


class ConditionService:
    """Domain service managing versioned environment prerequisite condition sets and verifications."""

    @staticmethod
    async def establish_initial_conditions(
        session: AsyncSession,
        context: TrustedContext,
        claim_id: uuid.UUID,
        params: EstablishConditionsParams,
    ) -> ClaimConditionSet:
        """Establish the initial condition set (version 1) for an unconditioned claim.

        Performs:
        1. Caller authentication and authorization check.
        2. Row-level lock on the Claim using SELECT ... FOR UPDATE.
        3. Rejects already conditioned claims with ConditionsAlreadyEstablishedError (HTTP 409).
        4. Validates that establishing snapshot exists in the same workspace.
        5. Requires at least one critical condition.
        6. Evaluates all proposed conditions against the establishing snapshot.
           Rejects establishment if any condition is DRIFTED or UNCHECKED (HTTP 422).
        7. Atomically creates ClaimConditionSet (version 1), ClaimCondition rows, and
           initial ClaimVerification (verification_type='initial', outcome='applicable').
        8. Atomically updates claims.active_condition_version=1 and increments claims.version.
        9. Stages CLAIM_CONDITIONS_ESTABLISHED audit event.

        Does not commit; the route owns transaction commit/rollback.
        """
        if not context.is_agent:
            raise UnauthorizedActorError("Conditions can only be established by an authorized agent.")

        # 1. Lock and retrieve Claim row
        claim_stmt = (
            select(Claim)
            .where(Claim.id == claim_id, Claim.workspace_id == context.workspace_id)
            .with_for_update()
        )
        claim_res = await session.execute(claim_stmt)
        claim = claim_res.scalar_one_or_none()

        if claim is None:
            # Check for cross-workspace existence to protect tenant boundary
            other_claim = await session.execute(select(Claim.id).where(Claim.id == claim_id))
            if other_claim.scalar_one_or_none() is not None:
                raise WorkspaceMismatchError("Claim belongs to another workspace.")
            raise EntityNotFoundError("Claim", claim_id)

        # 2. Invariant: Claim must be unconditioned
        if claim.active_condition_version is not None:
            raise ConditionsAlreadyEstablishedError(claim.id, claim.active_condition_version)

        # 3. Retrieve establishing EnvironmentSnapshot in same workspace
        snap_stmt = select(EnvironmentSnapshot).where(EnvironmentSnapshot.id == params.based_on_snapshot_id)
        snap_res = await session.execute(snap_stmt)
        snapshot = snap_res.scalar_one_or_none()

        if snapshot is None:
            raise EntityNotFoundError("EnvironmentSnapshot", params.based_on_snapshot_id)
        if snapshot.workspace_id != context.workspace_id:
            raise WorkspaceMismatchError("Establishing snapshot belongs to another workspace.")

        # 4. Critical condition requirement
        if not any(c.is_critical for c in params.conditions):
            raise CriticalConditionRequiredError()

        # 5. Evaluate all conditions against establishing snapshot
        evaluation_details = []
        for cond_spec in params.conditions:
            eval_result = evaluate_condition_against_snapshot(
                condition=cond_spec,
                scan_scope=snapshot.scan_scope,
                snapshot_data=snapshot.snapshot_data,
            )
            evaluation_details.append({
                "condition_type": cond_spec.condition_type,
                "target_path": cond_spec.target_path,
                "status": eval_result.status.value,
                "reason": eval_result.reason,
                "details": eval_result.details,
            })
            if eval_result.status != ConditionStatus.SATISFIED:
                raise ConditionSnapshotMismatchError(
                    f"Initial condition '{cond_spec.condition_type}:{cond_spec.target_path}' "
                    f"is not satisfied by establishing snapshot: status={eval_result.status.value}, "
                    f"reason={eval_result.reason}."
                )

        # 6. Create ClaimConditionSet (version 1)
        condition_set_id = uuid.uuid4()
        now = datetime.now(timezone.utc)
        condition_set = ClaimConditionSet(
            id=condition_set_id,
            workspace_id=context.workspace_id,
            claim_id=claim.id,
            version=1,
            based_on_snapshot_id=snapshot.id,
            established_by_agent=context.actor_id,
            rationale=params.rationale,
            created_at=now,
        )
        session.add(condition_set)

        # 7. Create ClaimCondition rows
        created_conditions: List[ClaimCondition] = []
        for cond_spec in params.conditions:
            expected_hash = (
                cond_spec.expected_hash
                if cond_spec.expected_hash
                else cond_spec.expected_value.get("hash")
            )
            cond_row = ClaimCondition(
                id=uuid.uuid4(),
                workspace_id=context.workspace_id,
                claim_id=claim.id,
                condition_set_version=1,
                condition_type=cond_spec.condition_type,
                target_path=cond_spec.target_path,
                comparator=cond_spec.comparator,
                expected_hash=expected_hash.lower() if expected_hash else None,
                expected_value=cond_spec.expected_value,
                is_critical=cond_spec.is_critical,
                created_at=now,
            )
            session.add(cond_row)
            created_conditions.append(cond_row)

        condition_set.conditions = created_conditions

        # 8. Create initial ClaimVerification record
        verification = ClaimVerification(
            id=uuid.uuid4(),
            workspace_id=context.workspace_id,
            claim_id=claim.id,
            condition_set_version=1,
            snapshot_id=snapshot.id,
            verification_type="initial",
            outcome="applicable",
            evaluation_details={
                "evaluated_conditions": evaluation_details,
                "total_conditions": len(params.conditions),
                "critical_conditions": sum(1 for c in params.conditions if c.is_critical),
            },
            verified_by_agent=context.actor_id,
            attestation_notes=f"Initial condition set v1 established and verified against snapshot '{snapshot.id}'.",
            created_at=now,
        )
        session.add(verification)
        await session.flush()

        # 9. Atomically update Claim pointer and version (preserving claim status!)
        claim.active_condition_version = 1
        claim.version += 1
        claim.updated_at = now

        # 10. Stage Audit Event
        await record_audit_event(
            session=session,
            context=context,
            event_type="CLAIM_CONDITIONS_ESTABLISHED",
            target_type="claim",
            target_id=claim.id,
            payload={
                "condition_set_id": str(condition_set.id),
                "version": 1,
                "based_on_snapshot_id": str(snapshot.id),
                "condition_count": len(params.conditions),
                "critical_count": sum(1 for c in params.conditions if c.is_critical),
                "verification_id": str(verification.id),
            },
        )

        await session.flush()
        return condition_set

    @staticmethod
    async def reverify_claim(
        session: AsyncSession,
        context: TrustedContext,
        claim_id: uuid.UUID,
        params: ReverifyClaimParams,
    ) -> Dict[str, Any]:
        """Reverify a claim's active conditions against an environment snapshot or adopt new conditions.

        Enforces:
        1. Caller must be an authorized agent.
        2. Pessimistic row-level lock on the Claim using SELECT ... FOR UPDATE.
        3. Strict workspace boundary and claim scope visibility.
        4. Rejects claims in terminal lifecycle status ('retracted', 'superseded') with InvalidClaimStateError.
        5. Rejects unconditioned claims with InvalidClaimStateError.
        6. Optimistic concurrency guard: expected_condition_version must match active_condition_version,
           rejecting stale concurrent updates with StaleConditionVersionError (HTTP 409).
        7. Referenced snapshot must exist within the caller workspace.
        8. Action 'verify_existing':
           - Evaluates active conditions against the snapshot.
           - Persists an immutable ClaimVerification record.
           - Stages CLAIM_REVERIFIED audit event.
           - Preserves active conditions and claim status.
        9. Action 'adopt_new_conditions':
           - Validates all proposed conditions against the snapshot (rejects if any is DRIFTED or UNCHECKED).
           - Requires at least one critical condition.
           - Creates a new immutable ClaimConditionSet (version = active_version + 1).
           - Creates new ClaimCondition rows for the new version.
           - Persists ClaimVerification for the new version.
           - Atomically updates claims.active_condition_version and increments claims.version.
           - Stages CLAIM_CONDITIONS_ADOPTED audit event.
           - Preserves claim lifecycle status as-is.

        Does not commit; the route owns transaction commit/rollback.
        """
        if not context.is_agent:
            raise UnauthorizedActorError("Claims can only be reverified by an authorized agent.")

        # 1. Lock and retrieve Claim row
        claim_stmt = (
            select(Claim)
            .where(Claim.id == claim_id, Claim.workspace_id == context.workspace_id)
            .with_for_update()
        )
        claim_res = await session.execute(claim_stmt)
        claim = claim_res.scalar_one_or_none()

        if claim is None:
            other_claim = await session.execute(select(Claim.id).where(Claim.id == claim_id))
            if other_claim.scalar_one_or_none() is not None:
                raise WorkspaceMismatchError("Claim belongs to another workspace.")
            raise EntityNotFoundError("Claim", claim_id)

        # 2. Scope visibility check
        from filament_api.services.claim import ClaimService
        ClaimService._check_claim_visibility(claim, context)

        # 3. Terminal lifecycle check
        if claim.status in ("retracted", "superseded"):
            raise InvalidClaimStateError(
                current_status=claim.status,
                requested_status="reverified",
                message=f"Cannot reverify claim in terminal status '{claim.status}'."
            )

        # 4. Conditioned claim invariant
        if claim.active_condition_version is None:
            raise InvalidClaimStateError(
                current_status=claim.status,
                requested_status="reverified",
                message=f"Claim '{claim.id}' has no active conditions established. Establish initial conditions first."
            )

        # 5. Concurrency guard: expected active condition version
        if claim.active_condition_version != params.expected_condition_version:
            raise StaleConditionVersionError(
                claim_id=claim.id,
                expected_version=params.expected_condition_version,
                actual_version=claim.active_condition_version,
            )

        # 6. Retrieve referenced snapshot
        snap_stmt = select(EnvironmentSnapshot).where(EnvironmentSnapshot.id == params.snapshot_id)
        snap_res = await session.execute(snap_stmt)
        snapshot = snap_res.scalar_one_or_none()

        if snapshot is None:
            raise EntityNotFoundError("EnvironmentSnapshot", params.snapshot_id)
        if snapshot.workspace_id != context.workspace_id:
            raise WorkspaceMismatchError("Referenced snapshot belongs to another workspace.")

        now = datetime.now(timezone.utc)

        # 7. Execute according to explicit action
        if params.action == "verify_existing":
            # Retrieve active conditions
            conds_stmt = (
                select(ClaimCondition)
                .where(
                    ClaimCondition.workspace_id == context.workspace_id,
                    ClaimCondition.claim_id == claim.id,
                    ClaimCondition.condition_set_version == claim.active_condition_version,
                )
                .order_by(ClaimCondition.created_at, ClaimCondition.target_path)
            )
            conds_res = await session.execute(conds_stmt)
            conditions = list(conds_res.scalars().all())

            if not conditions:
                raise EntityNotFoundError("ClaimConditionSet", claim.active_condition_version)

            # Evaluate each active condition
            condition_results: List[ConditionEvaluationItem] = []
            for cond in conditions:
                eval_res = evaluate_condition_against_snapshot(
                    condition=cond,
                    scan_scope=snapshot.scan_scope,
                    snapshot_data=snapshot.snapshot_data,
                )
                if cond.condition_type in ("file_hash", "lockfile_hash"):
                    expected_val = cond.expected_hash or (
                        cond.expected_value.get("hash") if isinstance(cond.expected_value, dict) else None
                    )
                    observed_val = eval_res.details.get("hash") or eval_res.details.get("actual_hash")
                elif cond.condition_type == "package_version":
                    expected_val = (
                        cond.expected_value.get("version")
                        if isinstance(cond.expected_value, dict) and "version" in cond.expected_value
                        else cond.expected_value
                    )
                    observed_val = eval_res.details.get("version") or eval_res.details.get("actual")
                elif cond.condition_type == "runtime_fact":
                    expected_val = (
                        cond.expected_value.get("value")
                        if isinstance(cond.expected_value, dict) and "value" in cond.expected_value
                        else cond.expected_value.get(cond.target_path, cond.expected_value)
                        if isinstance(cond.expected_value, dict)
                        else cond.expected_value
                    )
                    observed_val = eval_res.details.get("value") or eval_res.details.get("actual")
                else:
                    expected_val = cond.expected_hash or cond.expected_value
                    observed_val = None

                item = ConditionEvaluationItem(
                    condition_id=cond.id,
                    condition_type=cond.condition_type,
                    target_path=cond.target_path,
                    target=cond.target_path,
                    is_critical=cond.is_critical,
                    comparator=cond.comparator,
                    expected_value=expected_val,
                    observed_value=observed_val,
                    status=eval_res.status.value,
                    reason=eval_res.reason,
                    details=eval_res.details,
                )
                condition_results.append(item)

            has_critical_drifted = any(
                item.is_critical and item.status == "DRIFTED" for item in condition_results
            )
            has_critical_unchecked = any(
                item.is_critical and item.status == "UNCHECKED" for item in condition_results
            )

            if has_critical_drifted:
                outcome = "environment_mismatch"
                is_applicable = False
            elif has_critical_unchecked:
                outcome = "indeterminate"
                is_applicable = False
            elif claim.status in ("needs_review", "disputed"):
                outcome = "indeterminate"
                is_applicable = False
            else:
                outcome = "applicable"
                is_applicable = True

            # Persist ClaimVerification record
            verification = ClaimVerification(
                id=uuid.uuid4(),
                workspace_id=context.workspace_id,
                claim_id=claim.id,
                condition_set_version=claim.active_condition_version,
                snapshot_id=snapshot.id,
                verification_type="reverification",
                outcome=outcome,
                evaluation_details={
                    "evaluated_conditions": [i.model_dump(mode="json") for i in condition_results],
                    "total_conditions": len(condition_results),
                    "critical_conditions": sum(1 for c in condition_results if c.is_critical),
                    "satisfied_count": sum(1 for c in condition_results if c.status == "SATISFIED"),
                    "drifted_count": sum(1 for c in condition_results if c.status == "DRIFTED"),
                    "unchecked_count": sum(1 for c in condition_results if c.status == "UNCHECKED"),
                    "conditions_match": not (has_critical_drifted or has_critical_unchecked),
                    "lifecycle_status": claim.status,
                    "claim_status": claim.status,
                },
                verified_by_agent=context.actor_id,
                attestation_notes=params.attestation_notes,
                created_at=now,
            )
            session.add(verification)

            # Stage audit event
            await record_audit_event(
                session=session,
                context=context,
                event_type="CLAIM_REVERIFIED",
                target_type="claim",
                target_id=claim.id,
                payload={
                    "snapshot_id": str(snapshot.id),
                    "condition_set_version": claim.active_condition_version,
                    "verification_id": str(verification.id),
                    "outcome": outcome,
                    "is_applicable": is_applicable,
                    "action": "verify_existing",
                },
            )

            await session.flush()
            return {
                "verification_id": verification.id,
                "claim_id": claim.id,
                "snapshot_id": snapshot.id,
                "condition_set_version": claim.active_condition_version,
                "active_condition_version": claim.active_condition_version,
                "verification_type": "reverification",
                "outcome": outcome,
                "is_applicable": is_applicable,
                "action_taken": "verify_existing",
                "verified_by_agent": context.actor_id,
                "attestation_notes": params.attestation_notes,
                "condition_results": condition_results,
                "created_at": now,
            }

        else:
            # Action: adopt_new_conditions
            # 1. Validate all proposed conditions against snapshot
            assert params.proposed_conditions is not None  # Guaranteed by schema validator
            condition_results: List[ConditionEvaluationItem] = []
            for cond_spec in params.proposed_conditions:
                eval_res = evaluate_condition_against_snapshot(
                    condition=cond_spec,
                    scan_scope=snapshot.scan_scope,
                    snapshot_data=snapshot.snapshot_data,
                )
                if eval_res.status != ConditionStatus.SATISFIED:
                    raise ConditionSnapshotMismatchError(
                        f"Proposed condition '{cond_spec.condition_type}:{cond_spec.target_path}' "
                        f"is not satisfied by snapshot '{snapshot.id}': status={eval_res.status.value}, "
                        f"reason={eval_res.reason}."
                    )
                if cond_spec.condition_type in ("file_hash", "lockfile_hash"):
                    expected_val = cond_spec.expected_hash or (
                        cond_spec.expected_value.get("hash") if isinstance(cond_spec.expected_value, dict) else None
                    )
                    observed_val = eval_res.details.get("hash") or eval_res.details.get("actual_hash")
                elif cond_spec.condition_type == "package_version":
                    expected_val = (
                        cond_spec.expected_value.get("version")
                        if isinstance(cond_spec.expected_value, dict) and "version" in cond_spec.expected_value
                        else cond_spec.expected_value
                    )
                    observed_val = eval_res.details.get("version") or eval_res.details.get("actual")
                elif cond_spec.condition_type == "runtime_fact":
                    expected_val = (
                        cond_spec.expected_value.get("value")
                        if isinstance(cond_spec.expected_value, dict) and "value" in cond_spec.expected_value
                        else cond_spec.expected_value.get(cond_spec.target_path, cond_spec.expected_value)
                        if isinstance(cond_spec.expected_value, dict)
                        else cond_spec.expected_value
                    )
                    observed_val = eval_res.details.get("value") or eval_res.details.get("actual")
                else:
                    expected_val = cond_spec.expected_hash or cond_spec.expected_value
                    observed_val = None

                item = ConditionEvaluationItem(
                    condition_id=None,
                    condition_type=cond_spec.condition_type,
                    target_path=cond_spec.target_path,
                    target=cond_spec.target_path,
                    is_critical=cond_spec.is_critical,
                    comparator=cond_spec.comparator,
                    expected_value=expected_val,
                    observed_value=observed_val,
                    status=eval_res.status.value,
                    reason=eval_res.reason,
                    details=eval_res.details,
                )
                condition_results.append(item)

            new_version = claim.active_condition_version + 1
            prev_version = claim.active_condition_version

            # 2. Create new ClaimConditionSet
            condition_set_id = uuid.uuid4()
            condition_set = ClaimConditionSet(
                id=condition_set_id,
                workspace_id=context.workspace_id,
                claim_id=claim.id,
                version=new_version,
                based_on_snapshot_id=snapshot.id,
                established_by_agent=context.actor_id,
                rationale=params.adopt_rationale or params.attestation_notes,
                created_at=now,
            )
            session.add(condition_set)

            # 3. Create new ClaimCondition rows
            created_conditions: List[ClaimCondition] = []
            for cond_spec, item in zip(params.proposed_conditions, condition_results):
                expected_hash = (
                    cond_spec.expected_hash
                    if cond_spec.expected_hash
                    else cond_spec.expected_value.get("hash")
                )
                cond_row = ClaimCondition(
                    id=uuid.uuid4(),
                    workspace_id=context.workspace_id,
                    claim_id=claim.id,
                    condition_set_version=new_version,
                    condition_type=cond_spec.condition_type,
                    target_path=cond_spec.target_path,
                    comparator=cond_spec.comparator,
                    expected_hash=expected_hash.lower() if expected_hash else None,
                    expected_value=cond_spec.expected_value,
                    is_critical=cond_spec.is_critical,
                    created_at=now,
                )
                session.add(cond_row)
                created_conditions.append(cond_row)
                item.condition_id = cond_row.id

            condition_set.conditions = created_conditions

            if claim.status in ("needs_review", "disputed"):
                adopt_outcome = "indeterminate"
                adopt_is_applicable = False
            else:
                adopt_outcome = "applicable"
                adopt_is_applicable = True

            # 4. Create ClaimVerification record
            verification = ClaimVerification(
                id=uuid.uuid4(),
                workspace_id=context.workspace_id,
                claim_id=claim.id,
                condition_set_version=new_version,
                snapshot_id=snapshot.id,
                verification_type="reverification",
                outcome=adopt_outcome,
                evaluation_details={
                    "evaluated_conditions": [i.model_dump(mode="json") for i in condition_results],
                    "total_conditions": len(condition_results),
                    "critical_conditions": sum(1 for c in condition_results if c.is_critical),
                    "adopted_new_conditions": True,
                    "previous_condition_set_version": prev_version,
                    "new_condition_set_version": new_version,
                    "conditions_match": True,
                    "lifecycle_status": claim.status,
                    "claim_status": claim.status,
                },
                verified_by_agent=context.actor_id,
                attestation_notes=params.attestation_notes,
                created_at=now,
            )
            session.add(verification)
            await session.flush()

            # 5. Atomically update claim pointer and version (claim.status preserved!)
            claim.active_condition_version = new_version
            claim.version += 1
            claim.updated_at = now

            # 6. Stage audit event
            await record_audit_event(
                session=session,
                context=context,
                event_type="CLAIM_CONDITIONS_ADOPTED",
                target_type="claim",
                target_id=claim.id,
                payload={
                    "snapshot_id": str(snapshot.id),
                    "previous_condition_set_version": prev_version,
                    "active_condition_version": new_version,
                    "condition_set_id": str(condition_set.id),
                    "condition_count": len(params.proposed_conditions),
                    "critical_count": sum(1 for c in params.proposed_conditions if c.is_critical),
                    "verification_id": str(verification.id),
                    "action": "adopt_new_conditions",
                },
            )

            await session.flush()
            return {
                "verification_id": verification.id,
                "claim_id": claim.id,
                "snapshot_id": snapshot.id,
                "condition_set_version": new_version,
                "active_condition_version": new_version,
                "verification_type": "reverification",
                "outcome": adopt_outcome,
                "is_applicable": adopt_is_applicable,
                "action_taken": "adopt_new_conditions",
                "verified_by_agent": context.actor_id,
                "attestation_notes": params.attestation_notes,
                "condition_results": condition_results,
                "created_at": now,
            }

