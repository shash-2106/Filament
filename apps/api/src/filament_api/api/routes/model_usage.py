"""API routes for Meta Model API budget visibility and usage analytics."""

from typing import List
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from filament_api.api.dependencies.auth import get_current_agent_context
from filament_api.config import get_settings
from filament_api.db.session import get_db
from filament_api.models.model_usage import ModelUsageRecord
from filament_api.schemas.model_usage import (
    BudgetSummaryResponse,
    ModelUsageRecordResponse,
    UsageByFeatureResponse,
    UsageByModelResponse,
)
from filament_api.services.context import TrustedContext
from filament_api.services.meta_api.ledger import BudgetLedgerService

router = APIRouter(prefix="/model-usage", tags=["Model Usage & Budget"])


@router.get("/budget", response_model=BudgetSummaryResponse)
async def get_budget_status(
    context: TrustedContext = Depends(get_current_agent_context),
    session: AsyncSession = Depends(get_db),
) -> BudgetSummaryResponse:
    """Retrieve application lifetime, daily, and test budgets with current spend.

    Returns completely secret-free budget headroom metrics.
    """
    settings = get_settings()
    ledger = BudgetLedgerService(session=session, settings=settings)
    summary = await ledger.get_budget_summary(workspace_id=context.workspace_id)
    return BudgetSummaryResponse(**summary)


@router.get("/records", response_model=List[ModelUsageRecordResponse])
async def list_usage_records(
    limit: int = Query(default=50, ge=1, le=200),
    context: TrustedContext = Depends(get_current_agent_context),
    session: AsyncSession = Depends(get_db),
) -> List[ModelUsageRecordResponse]:
    """List recent persistent usage and reservation records for the current workspace."""
    query = (
        select(ModelUsageRecord)
        .where(ModelUsageRecord.workspace_id == context.workspace_id)
        .order_by(ModelUsageRecord.created_at.desc())
        .limit(limit)
    )
    result = await session.execute(query)
    records = result.scalars().all()
    return [
        ModelUsageRecordResponse(
            id=r.id,
            workspace_id=r.workspace_id,
            feature=r.feature,
            model=r.model,
            estimated_input_tokens=r.estimated_input_tokens,
            max_reserved_output_tokens=r.max_reserved_output_tokens,
            actual_input_tokens=r.actual_input_tokens,
            actual_output_tokens=r.actual_output_tokens,
            reserved_cost_usd=float(r.reserved_cost_usd),
            actual_cost_usd=float(r.actual_cost_usd),
            status=r.status,
            provider_request_id=r.provider_request_id,
            created_at=r.created_at,
            completed_at=r.completed_at,
        )
        for r in records
    ]


@router.get("/by-model", response_model=List[UsageByModelResponse])
async def get_usage_by_model(
    context: TrustedContext = Depends(get_current_agent_context),
    session: AsyncSession = Depends(get_db),
) -> List[UsageByModelResponse]:
    """Aggregate token usage and spend grouped by model."""
    query = (
        select(
            ModelUsageRecord.model,
            func.count(ModelUsageRecord.id),
            func.coalesce(func.sum(ModelUsageRecord.actual_cost_usd), 0),
            func.coalesce(func.sum(ModelUsageRecord.actual_input_tokens), 0),
            func.coalesce(func.sum(ModelUsageRecord.actual_output_tokens), 0),
        )
        .where(
            ModelUsageRecord.workspace_id == context.workspace_id,
            ModelUsageRecord.status == "SUCCEEDED",
        )
        .group_by(ModelUsageRecord.model)
    )
    result = await session.execute(query)
    return [
        UsageByModelResponse(
            model=row[0],
            total_requests=row[1],
            actual_spend_usd=float(row[2]),
            actual_input_tokens=row[3],
            actual_output_tokens=row[4],
        )
        for row in result.all()
    ]


@router.get("/by-feature", response_model=List[UsageByFeatureResponse])
async def get_usage_by_feature(
    context: TrustedContext = Depends(get_current_agent_context),
    session: AsyncSession = Depends(get_db),
) -> List[UsageByFeatureResponse]:
    """Aggregate token usage and spend grouped by calling feature."""
    query = (
        select(
            ModelUsageRecord.feature,
            func.count(ModelUsageRecord.id),
            func.coalesce(func.sum(ModelUsageRecord.actual_cost_usd), 0),
            func.coalesce(func.sum(ModelUsageRecord.actual_input_tokens), 0),
            func.coalesce(func.sum(ModelUsageRecord.actual_output_tokens), 0),
        )
        .where(
            ModelUsageRecord.workspace_id == context.workspace_id,
            ModelUsageRecord.status == "SUCCEEDED",
        )
        .group_by(ModelUsageRecord.feature)
    )
    result = await session.execute(query)
    return [
        UsageByFeatureResponse(
            feature=row[0],
            total_requests=row[1],
            actual_spend_usd=float(row[2]),
            actual_input_tokens=row[3],
            actual_output_tokens=row[4],
        )
        for row in result.all()
    ]

