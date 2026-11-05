"""Schemas for Meta Model API usage reporting and budget visibility."""

from datetime import datetime
from typing import Dict, List, Optional
import uuid
from pydantic import BaseModel, Field


class StatusCounts(BaseModel):
    succeeded: int = Field(default=0)
    reserved: int = Field(default=0)
    failed: int = Field(default=0)
    unknown: int = Field(default=0)


class BudgetSummaryResponse(BaseModel):
    """Safe, secret-free summary of application-level budget and spending."""

    lifetime_budget_usd: float
    daily_budget_usd: float
    initial_test_budget_usd: float
    actual_spend_usd: float
    reserved_spend_usd: float
    unknown_spend_usd: float
    total_committed_usd: float
    daily_spend_usd: float
    remaining_lifetime_budget_usd: float
    remaining_daily_budget_usd: float
    remaining_test_budget_usd: float
    total_requests: int
    status_counts: StatusCounts


class ModelUsageRecordResponse(BaseModel):
    """Audit entry for a single model inference request."""

    id: uuid.UUID
    workspace_id: uuid.UUID
    feature: str
    model: str
    estimated_input_tokens: int
    max_reserved_output_tokens: int
    actual_input_tokens: int
    actual_output_tokens: int
    reserved_cost_usd: float
    actual_cost_usd: float
    status: str
    provider_request_id: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None


class UsageByModelResponse(BaseModel):
    model: str
    total_requests: int
    actual_spend_usd: float
    actual_input_tokens: int
    actual_output_tokens: int


class UsageByFeatureResponse(BaseModel):
    feature: str
    total_requests: int
    actual_spend_usd: float
    actual_input_tokens: int
    actual_output_tokens: int

