"""Evaluation domain service for transient read-only condition evaluation."""

from typing import Any, List, Optional
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from filament_api.models.claim import Claim
from filament_api.models.condition import ClaimCondition, ClaimConditionSet
from filament_api.models.snapshot import EnvironmentSnapshot
from filament_api.schemas.evaluation import ClaimEvaluationResponse, ConditionEvaluationItem
from filament_api.services.claim import ClaimService
from filament_api.services.condition import evaluate_condition_against_snapshot
from filament_api.services.context import TrustedContext
from filament_api.services.exceptions import (
    EntityNotFoundError,
    UnauthorizedActorError,
    WorkspaceMismatchError,
)


class EvaluationService:
    """Domain service for transient, read-only evaluation of claim conditions against snapshots."""

    @staticmethod
    async def evaluate_claim_conditions(
        session: AsyncSession,
        context: TrustedContext,
        claim_id: uuid.UUID,
        snapshot_id: uuid.UUID,
    ) -> ClaimEvaluationResponse:
        """Evaluate a claim's active conditions against an environment snapshot.

        Strictly read-only:
        - Does NOT update claim status or increment claim version.
        - Does NOT update active_condition_version.
        - Does NOT create a verification record or audit event.
        - Does NOT commit or flush session modifications.
        """
        if not context.is_agent:
            raise UnauthorizedActorError("Claims can only be evaluated by an authorized agent.")

        # 1. Retrieve and validate Claim (enforces workspace isolation and scope visibility)
        claim = await ClaimService.get_claim(session=session, context=context, claim_id=claim_id)

        # 2. Retrieve referenced EnvironmentSnapshot in caller workspace
        snap_stmt = select(EnvironmentSnapshot).where(EnvironmentSnapshot.id == snapshot_id)
        snap_res = await session.execute(snap_stmt)
        snapshot = snap_res.scalar_one_or_none()

        if snapshot is None:
            raise EntityNotFoundError("EnvironmentSnapshot", snapshot_id)
        if snapshot.workspace_id != context.workspace_id:
            raise WorkspaceMismatchError("EnvironmentSnapshot belongs to another workspace.")

        # 3. Check for unconditioned claim
        if claim.active_condition_version is None:
            # If claim is in a non-current state, not_applicable takes precedence per table
            if claim.status in ("retracted", "superseded", "disputed", "needs_review"):
                return ClaimEvaluationResponse(
                    claim_id=claim.id,
                    snapshot_id=snapshot.id,
                    active_condition_version=None,
                    outcome="not_applicable",
                    is_applicable=False,
                    condition_results=[],
                )
            return ClaimEvaluationResponse(
                claim_id=claim.id,
                snapshot_id=snapshot.id,
                active_condition_version=None,
                outcome="unconditioned",
                is_applicable=False,
                condition_results=[],
            )

        # 4. Retrieve active conditions for this claim
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

        # 5. Evaluate every condition deterministically
        condition_results: List[ConditionEvaluationItem] = []
        for cond in conditions:
            eval_res = evaluate_condition_against_snapshot(
                condition=cond,
                scan_scope=snapshot.scan_scope,
                snapshot_data=snapshot.snapshot_data,
            )

            # Extract expected value
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

        # 6. Aggregate overall outcome based on precedence rules
        if claim.status in ("retracted", "superseded", "disputed", "needs_review"):
            outcome = "not_applicable"
            is_applicable = False
        else:
            has_critical_drifted = any(
                item.is_critical and item.status == "DRIFTED" for item in condition_results
            )
            has_critical_unchecked = any(
                item.is_critical and item.status == "UNCHECKED" for item in condition_results
            )

            if has_critical_drifted:
                # Precedence: DRIFTED beats UNCHECKED
                outcome = "environment_mismatch"
                is_applicable = False
            elif has_critical_unchecked:
                outcome = "indeterminate"
                is_applicable = False
            else:
                # All critical conditions are SATISFIED
                outcome = "applicable"
                is_applicable = True

        return ClaimEvaluationResponse(
            claim_id=claim.id,
            snapshot_id=snapshot.id,
            active_condition_version=claim.active_condition_version,
            outcome=outcome,
            is_applicable=is_applicable,
            condition_results=condition_results,
        )

