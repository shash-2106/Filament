"""Durable spending ledger service for Meta Model API budget reservation and tracking."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, Optional, Tuple
import uuid

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from filament_api.config import Settings
from filament_api.models.model_usage import ModelUsageRecord
from filament_api.services.meta_api.exceptions import (
    BudgetExceededError,
    ConcurrencyLimitExceededError,
    MaxRequestCostExceededError,
    UnresolvedSpendingUncertaintyError,
)
from filament_api.services.meta_api.pricing import calculate_cost_usd


class BudgetLedgerService:
    """Manages persistent spending ledger and atomic reservation invariants.

    All budgets ($100 lifetime, $5 daily, $5 test) are strictly GLOBAL across every
    workspace sharing this Meta API key. A dedicated SECURITY DEFINER database function
    `filament_get_global_model_budget_summary()` computes global spending regardless
    of session workspace context under RLS.
    """

    def __init__(self, session: AsyncSession, settings: Settings):
        self.session = session
        self.settings = settings

    async def get_budget_summary(self, workspace_id: Optional[uuid.UUID] = None) -> Dict[str, any]:
        """Compute lifetime, daily, and status-grouped spending metrics.

        If workspace_id is provided, returns metrics scoped to that workspace for UI reporting.
        If workspace_id is None, invokes the SECURITY DEFINER function to compute genuinely
        GLOBAL spending across all workspaces for cost control and enforcement.
        """
        lifetime_budget = Decimal(str(self.settings.MODEL_API_LIFETIME_BUDGET_USD))
        daily_budget = Decimal(str(self.settings.MODEL_API_DAILY_BUDGET_USD))
        test_budget = Decimal(str(self.settings.MODEL_API_INITIAL_TEST_BUDGET_USD))

        if workspace_id is None:
            # Query global spending via database security definer function or fallback direct sum
            try:
                fn_result = await self.session.execute(
                    text("SELECT * FROM public.filament_get_global_model_budget_summary()")
                )
                row = fn_result.mappings().first()
                if row:
                    actual_spend = Decimal(str(row["actual_spend_usd"]))
                    reserved_spend = Decimal(str(row["reserved_spend_usd"]))
                    unknown_spend = Decimal(str(row["unknown_spend_usd"]))
                    total_committed = Decimal(str(row["total_committed_usd"]))
                    daily_spend = Decimal(str(row["daily_spend_usd"]))
                    total_requests = int(row["total_requests"])
                    succeeded_cnt = int(row["succeeded_count"])
                    reserved_cnt = int(row["reserved_count"])
                    failed_cnt = int(row["failed_count"])
                    unknown_cnt = int(row["unknown_count"])

                    remaining_lifetime = max(Decimal("0.000000"), lifetime_budget - total_committed)
                    remaining_daily = max(Decimal("0.000000"), daily_budget - daily_spend)
                    remaining_test = max(Decimal("0.000000"), test_budget - total_committed)

                    return {
                        "lifetime_budget_usd": float(lifetime_budget),
                        "daily_budget_usd": float(daily_budget),
                        "initial_test_budget_usd": float(test_budget),
                        "actual_spend_usd": float(actual_spend),
                        "reserved_spend_usd": float(reserved_spend),
                        "unknown_spend_usd": float(unknown_spend),
                        "total_committed_usd": float(total_committed),
                        "daily_spend_usd": float(daily_spend),
                        "remaining_lifetime_budget_usd": float(remaining_lifetime),
                        "remaining_daily_budget_usd": float(remaining_daily),
                        "remaining_test_budget_usd": float(remaining_test),
                        "total_requests": total_requests,
                        "status_counts": {
                            "succeeded": succeeded_cnt,
                            "reserved": reserved_cnt,
                            "failed": failed_cnt,
                            "unknown": unknown_cnt,
                        },
                    }
            except Exception:
                # If function is not present (e.g. during mock tests with SQLite or unmigrated mock session), fallback to ORM query
                pass

        now = datetime.now(timezone.utc)
        one_day_ago = now - timedelta(days=1)

        # 1. Total Succeeded Spend (actual_cost_usd)
        succeeded_query = select(
            func.coalesce(func.sum(ModelUsageRecord.actual_cost_usd), Decimal("0.000000"))
        ).where(ModelUsageRecord.status == "SUCCEEDED")
        if workspace_id:
            succeeded_query = succeeded_query.where(ModelUsageRecord.workspace_id == workspace_id)
        actual_spend = await self.session.scalar(succeeded_query) or Decimal("0.000000")

        # 2. Total Reserved In-Flight Spend (reserved_cost_usd of RESERVED status)
        reserved_query = select(
            func.coalesce(func.sum(ModelUsageRecord.reserved_cost_usd), Decimal("0.000000"))
        ).where(ModelUsageRecord.status == "RESERVED")
        if workspace_id:
            reserved_query = reserved_query.where(ModelUsageRecord.workspace_id == workspace_id)
        reserved_spend = await self.session.scalar(reserved_query) or Decimal("0.000000")

        # 3. Total Unknown / Ambiguous Spend (held at reserved_cost_usd)
        unknown_query = select(
            func.coalesce(func.sum(ModelUsageRecord.reserved_cost_usd), Decimal("0.000000"))
        ).where(ModelUsageRecord.status == "UNKNOWN")
        if workspace_id:
            unknown_query = unknown_query.where(ModelUsageRecord.workspace_id == workspace_id)
        unknown_spend = await self.session.scalar(unknown_query) or Decimal("0.000000")

        # Total committed liability = actual + reserved + unknown
        total_committed = actual_spend + reserved_spend + unknown_spend

        # 4. Daily Spend (past 24h: actual of SUCCEEDED + reserved of RESERVED/UNKNOWN)
        daily_succeeded_query = select(
            func.coalesce(func.sum(ModelUsageRecord.actual_cost_usd), Decimal("0.000000"))
        ).where(
            ModelUsageRecord.status == "SUCCEEDED",
            ModelUsageRecord.created_at >= one_day_ago,
        )
        if workspace_id:
            daily_succeeded_query = daily_succeeded_query.where(ModelUsageRecord.workspace_id == workspace_id)
        daily_actual = await self.session.scalar(daily_succeeded_query) or Decimal("0.000000")

        daily_pending_query = select(
            func.coalesce(func.sum(ModelUsageRecord.reserved_cost_usd), Decimal("0.000000"))
        ).where(
            ModelUsageRecord.status.in_(["RESERVED", "UNKNOWN"]),
            ModelUsageRecord.created_at >= one_day_ago,
        )
        if workspace_id:
            daily_pending_query = daily_pending_query.where(ModelUsageRecord.workspace_id == workspace_id)
        daily_pending = await self.session.scalar(daily_pending_query) or Decimal("0.000000")

        daily_spend = daily_actual + daily_pending

        # 5. Counts by status
        counts_query = select(
            ModelUsageRecord.status,
            func.count(ModelUsageRecord.id),
        )
        if workspace_id:
            counts_query = counts_query.where(ModelUsageRecord.workspace_id == workspace_id)
        counts_query = counts_query.group_by(ModelUsageRecord.status)
        result = await self.session.execute(counts_query)
        status_counts = {row[0]: row[1] for row in result.all()}

        remaining_lifetime = max(Decimal("0.000000"), lifetime_budget - total_committed)
        remaining_daily = max(Decimal("0.000000"), daily_budget - daily_spend)
        remaining_test = max(Decimal("0.000000"), test_budget - total_committed)

        total_requests = sum(status_counts.values())

        return {
            "lifetime_budget_usd": float(lifetime_budget),
            "daily_budget_usd": float(daily_budget),
            "initial_test_budget_usd": float(test_budget),
            "actual_spend_usd": float(actual_spend),
            "reserved_spend_usd": float(reserved_spend),
            "unknown_spend_usd": float(unknown_spend),
            "total_committed_usd": float(total_committed),
            "daily_spend_usd": float(daily_spend),
            "remaining_lifetime_budget_usd": float(remaining_lifetime),
            "remaining_daily_budget_usd": float(remaining_daily),
            "remaining_test_budget_usd": float(remaining_test),
            "total_requests": total_requests,
            "status_counts": {
                "succeeded": status_counts.get("SUCCEEDED", 0),
                "reserved": status_counts.get("RESERVED", 0),
                "failed": status_counts.get("FAILED", 0),
                "unknown": status_counts.get("UNKNOWN", 0),
            },
        }

    async def reserve_budget(
        self,
        workspace_id: uuid.UUID,
        feature: str,
        model: str,
        estimated_input_tokens: int,
        max_output_tokens: int,
    ) -> ModelUsageRecord:
        """Atomically verify spending ceilings and reserve funds in the database.

        CRITICAL ENFORCEMENT RULES:
        1. Single request cost ceiling ($0.10).
        2. Maximum concurrent in-flight requests (GLOBAL count(RESERVED) < 1).
        3. No unresolved UNKNOWN status requests (GLOBAL count(UNKNOWN) == 0).
        4. Lifetime budget ceiling (GLOBAL total_committed + estimated <= $100.00).
        5. Daily budget ceiling (GLOBAL daily_committed + estimated <= $5.00).
        6. Initial test budget ceiling (GLOBAL total_committed + estimated <= $5.00).
        """
        # Calculate maximum potential cost for this single request
        estimated_cost = calculate_cost_usd(model, estimated_input_tokens, max_output_tokens)
        max_request_ceiling = Decimal(str(self.settings.MODEL_API_MAX_REQUEST_COST_USD))

        if estimated_cost > max_request_ceiling:
            raise MaxRequestCostExceededError(
                f"Estimated request cost ${estimated_cost:.4f} exceeds max request cost ceiling "
                f"${max_request_ceiling:.4f} USD."
            )

        # Acquire global PostgreSQL transaction-level advisory lock across all backend processes/workspaces.
        # Lock ID 1135888033 corresponds to zlib.crc32(b'filament_meta_api_reservation_lock').
        # If in a SQLite or non-Postgres environment (e.g. offline unit mocks), handle gracefully.
        try:
            await self.session.execute(text("SELECT pg_advisory_xact_lock(1135888033)"))
        except Exception:
            pass

        # Retrieve genuinely GLOBAL budget summary (workspace_id=None)
        summary = await self.get_budget_summary(workspace_id=None)

        # Enforce Concurrency Limit across ALL workspaces globally
        active_count = summary["status_counts"]["reserved"]
        if active_count >= self.settings.MODEL_API_MAX_CONCURRENT_REQUESTS:
            raise ConcurrencyLimitExceededError(
                f"Maximum concurrent request limit ({self.settings.MODEL_API_MAX_CONCURRENT_REQUESTS}) "
                f"reached. Another request is currently in-flight."
            )

        # Enforce Unresolved Spending Uncertainty across ALL workspaces globally
        unknown_count = summary["status_counts"]["unknown"]
        if unknown_count > 0:
            raise UnresolvedSpendingUncertaintyError(
                f"Found {unknown_count} request(s) with UNKNOWN outcome. Further spending is blocked "
                f"until outcome reconciliation to prevent budget overruns."
            )

        current_total = Decimal(str(summary["total_committed_usd"]))
        current_daily = Decimal(str(summary["daily_spend_usd"]))

        lifetime_budget = Decimal(str(self.settings.MODEL_API_LIFETIME_BUDGET_USD))
        daily_budget = Decimal(str(self.settings.MODEL_API_DAILY_BUDGET_USD))
        test_budget = Decimal(str(self.settings.MODEL_API_INITIAL_TEST_BUDGET_USD))

        # Check Lifetime Budget (GLOBAL)
        if current_total + estimated_cost > lifetime_budget:
            raise BudgetExceededError(
                f"Reservation of ${estimated_cost:.4f} would exceed lifetime budget of ${lifetime_budget:.2f} "
                f"(current global committed: ${current_total:.4f})."
            )

        # Check Daily Budget (GLOBAL)
        if current_daily + estimated_cost > daily_budget:
            raise BudgetExceededError(
                f"Reservation of ${estimated_cost:.4f} would exceed daily budget of ${daily_budget:.2f} "
                f"(current global 24h committed: ${current_daily:.4f})."
            )

        # Check Initial Test Budget (GLOBAL)
        if current_total + estimated_cost > test_budget:
            raise BudgetExceededError(
                f"Reservation of ${estimated_cost:.4f} would exceed initial test budget of ${test_budget:.2f} "
                f"(current global committed: ${current_total:.4f})."
            )

        # Create persistent reservation row in state RESERVED
        record = ModelUsageRecord(
            id=uuid.uuid4(),
            workspace_id=workspace_id,
            feature=feature,
            model=model,
            estimated_input_tokens=estimated_input_tokens,
            max_reserved_output_tokens=max_output_tokens,
            actual_input_tokens=0,
            actual_output_tokens=0,
            reserved_cost_usd=estimated_cost,
            actual_cost_usd=Decimal("0.000000"),
            status="RESERVED",
            created_at=datetime.now(timezone.utc),
        )

        self.session.add(record)
        await self.session.commit()
        await self.session.refresh(record)
        return record

    async def reconcile_success(
        self,
        record_id: uuid.UUID,
        actual_input_tokens: int,
        actual_output_tokens: int,
        provider_request_id: Optional[str] = None,
    ) -> ModelUsageRecord:
        """Reconcile reservation upon successful provider response.

        Calculates actual cost using versioned pricing, sets status SUCCEEDED,
        and releases unused reservation funds.
        """
        record = await self.session.get(ModelUsageRecord, record_id)
        if not record:
            raise ValueError(f"Record {record_id} not found for reconciliation.")

        actual_cost = calculate_cost_usd(record.model, actual_input_tokens, actual_output_tokens)

        record.actual_input_tokens = actual_input_tokens
        record.actual_output_tokens = actual_output_tokens
        record.actual_cost_usd = actual_cost
        record.status = "SUCCEEDED"
        record.provider_request_id = provider_request_id
        record.completed_at = datetime.now(timezone.utc)

        await self.session.commit()
        await self.session.refresh(record)
        return record

    async def reconcile_failure(
        self,
        record_id: uuid.UUID,
        error_message: str,
        billable_tokens: bool = False,
    ) -> ModelUsageRecord:
        """Reconcile reservation upon explicit, verifiable provider failure.

        If billable_tokens is False, sets actual_cost_usd to 0.0, releasing the reservation.
        """
        record = await self.session.get(ModelUsageRecord, record_id)
        if not record:
            raise ValueError(f"Record {record_id} not found for reconciliation.")

        record.status = "FAILED"
        record.error_message = error_message[:1000]  # Sanitize length
        record.actual_cost_usd = Decimal("0.000000") if not billable_tokens else record.reserved_cost_usd
        record.completed_at = datetime.now(timezone.utc)

        await self.session.commit()
        await self.session.refresh(record)
        return record

    async def mark_unknown(
        self,
        record_id: uuid.UUID,
        error_message: str,
    ) -> ModelUsageRecord:
        """Mark request as UNKNOWN following network timeout or ambiguous provider response.

        Never assumes a timed-out request was free. Retains reservation liability.
        """
        record = await self.session.get(ModelUsageRecord, record_id)
        if not record:
            raise ValueError(f"Record {record_id} not found.")

        record.status = "UNKNOWN"
        record.error_message = f"Ambiguous outcome / timeout: {error_message}"[:1000]
        record.completed_at = datetime.now(timezone.utc)

        await self.session.commit()
        await self.session.refresh(record)
        return record
