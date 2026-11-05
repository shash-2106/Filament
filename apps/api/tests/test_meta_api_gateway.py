"""Comprehensive test suite for Meta Model API Gateway, Budget Ledger, and Cost Controls.

CRITICAL INVARIANT: Zero real external API calls are made. All requests are mocked.
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict
from unittest.mock import AsyncMock, patch
import uuid
import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from filament_api.config import Settings
from filament_api.db.base import Base
from filament_api.models.model_usage import ModelUsageRecord
from filament_api.models.workspace import Workspace
from filament_api.services.meta_api.exceptions import (
    BudgetExceededError,
    ConcurrencyLimitExceededError,
    MaxRequestCostExceededError,
    MetaApiDisabledError,
    MetaApiKeyMissingError,
    MetaApiProviderError,
    MetaApiTimeoutError,
    ModelNotAllowlistedError,
    TokenLimitExceededError,
    UnresolvedSpendingUncertaintyError,
)
from filament_api.services.meta_api.gateway import MetaModelGateway
from filament_api.services.meta_api.ledger import BudgetLedgerService
from filament_api.services.meta_api.pricing import calculate_cost_usd, estimate_input_tokens


@pytest.fixture
def test_settings() -> Settings:
    """Fixture providing isolated, strictly configured settings."""
    return Settings(
        ENVIRONMENT="test",
        MODEL_API_KEY="test_mock_meta_key_never_live",
        MODEL_API_BASE_URL="https://api.meta.ai/v1",
        MODEL_API_MODEL="muse-spark-1.3",
        MODEL_API_ENABLED=True,
        MODEL_API_LIFETIME_BUDGET_USD=100.0,
        MODEL_API_DAILY_BUDGET_USD=5.0,
        MODEL_API_INITIAL_TEST_BUDGET_USD=5.0,
        MODEL_API_MAX_REQUEST_COST_USD=0.10,
        MODEL_API_MAX_INPUT_TOKENS=20000,
        MODEL_API_MAX_OUTPUT_TOKENS=2000,
        MODEL_API_MAX_CONCURRENT_REQUESTS=1,
    )


@pytest.fixture
def mock_workspace_id() -> uuid.UUID:
    return uuid.uuid4()


# =========================================================================
# 1. Pricing and Token Estimation Tests
# =========================================================================

def test_cost_calculation_standard_rates():
    """Verify standard rates for muse-spark-1.3:
    Input: $1.25 / 1M ($0.00000125 / token)
    Output: $4.25 / 1M ($0.00000425 / token)
    """
    # 1,000,000 input tokens = $1.25
    cost_in = calculate_cost_usd("muse-spark-1.3", 1000000, 0)
    assert cost_in == Decimal("1.250000")

    # 1,000,000 output tokens = $4.25
    cost_out = calculate_cost_usd("muse-spark-1.3", 0, 1000000)
    assert cost_out == Decimal("4.250000")

    # 10,000 in + 1,000 out:
    # (10000 * 1.25)/1M = 0.0125
    # (1000 * 4.25)/1M = 0.00425
    # total = 0.016750
    cost_combo = calculate_cost_usd("muse-spark-1.3", 10000, 1000)
    assert cost_combo == Decimal("0.016750")


def test_unallowlisted_model_rejected_by_pricing():
    with pytest.raises(ValueError, match="not in the allowlisted pricing registry"):
        calculate_cost_usd("unauthorized-gpt-5", 100, 100)


def test_conservative_token_estimation():
    text = "Filament is a governed memory system for autonomous AI agents."
    tokens = estimate_input_tokens(text)
    # Must be non-zero and include the conservative buffer
    assert tokens > len(text.split())
    assert tokens >= 15


# =========================================================================
# 2. Pre-Flight Hard Fail-Closed Gateway Tests (No Mock Client Needed)
# =========================================================================

@pytest.mark.asyncio
async def test_gateway_rejects_when_disabled(mock_workspace_id: uuid.UUID):
    settings = Settings(MODEL_API_ENABLED=False)
    session = AsyncMock(spec=AsyncSession)
    gateway = MetaModelGateway(session=session, settings=settings)

    with pytest.raises(MetaApiDisabledError, match="disabled by configuration"):
        await gateway.generate_response(
            workspace_id=mock_workspace_id,
            feature="test",
            prompt="Hello world",
        )


@pytest.mark.asyncio
async def test_gateway_rejects_missing_api_key(mock_workspace_id: uuid.UUID):
    settings = Settings(MODEL_API_ENABLED=True, MODEL_API_KEY="")
    session = AsyncMock(spec=AsyncSession)
    gateway = MetaModelGateway(session=session, settings=settings)

    with pytest.raises(MetaApiKeyMissingError, match="key is not configured"):
        await gateway.generate_response(
            workspace_id=mock_workspace_id,
            feature="test",
            prompt="Hello world",
        )


@pytest.mark.asyncio
async def test_gateway_rejects_unallowlisted_model(test_settings: Settings, mock_workspace_id: uuid.UUID):
    session = AsyncMock(spec=AsyncSession)
    gateway = MetaModelGateway(session=session, settings=test_settings)

    with pytest.raises(ModelNotAllowlistedError, match="not allowlisted"):
        await gateway.generate_response(
            workspace_id=mock_workspace_id,
            feature="test",
            prompt="Hello world",
            model="llama-3.3-70b-arbitrary",
        )


@pytest.mark.asyncio
async def test_gateway_rejects_input_token_limit_exceeded(test_settings: Settings, mock_workspace_id: uuid.UUID):
    session = AsyncMock(spec=AsyncSession)
    gateway = MetaModelGateway(session=session, settings=test_settings)

    # Generate a massive prompt exceeding 20,000 tokens
    huge_prompt = "word " * 30000
    with pytest.raises(TokenLimitExceededError, match="Estimated input tokens"):
        await gateway.generate_response(
            workspace_id=mock_workspace_id,
            feature="test",
            prompt=huge_prompt,
        )


@pytest.mark.asyncio
async def test_gateway_rejects_output_token_limit_exceeded(test_settings: Settings, mock_workspace_id: uuid.UUID):
    session = AsyncMock(spec=AsyncSession)
    gateway = MetaModelGateway(session=session, settings=test_settings)

    with pytest.raises(TokenLimitExceededError, match="Requested max output tokens"):
        await gateway.generate_response(
            workspace_id=mock_workspace_id,
            feature="test",
            prompt="Short prompt",
            max_output_tokens=5000,  # Limit is 2000
        )


# =========================================================================
# 3. Budget & Concurrency Enforcement Tests (Mocked DB Session)
# =========================================================================

@pytest.mark.asyncio
async def test_budget_reservation_rejects_max_request_cost(test_settings: Settings, mock_workspace_id: uuid.UUID):
    """When a single request's worst-case reservation exceeds MODEL_API_MAX_REQUEST_COST_USD ($0.10)."""
    session = AsyncMock(spec=AsyncSession)
    ledger = BudgetLedgerService(session=session, settings=test_settings)

    # 100,000 output tokens * $4.25/1M = $0.425 (exceeds $0.10 ceiling)
    with pytest.raises(MaxRequestCostExceededError, match="exceeds max request cost ceiling"):
        await ledger.reserve_budget(
            workspace_id=mock_workspace_id,
            feature="test",
            model="muse-spark-1.3",
            estimated_input_tokens=1000,
            max_output_tokens=100000,
        )


@pytest.mark.asyncio
async def test_concurrency_limit_enforced(test_settings: Settings, mock_workspace_id: uuid.UUID):
    """Reject new request if another request currently has status RESERVED."""
    session = AsyncMock(spec=AsyncSession)
    ledger = BudgetLedgerService(session=session, settings=test_settings)

    with patch.object(
        ledger,
        "get_budget_summary",
        return_value={
            "total_committed_usd": 0.0,
            "daily_spend_usd": 0.0,
            "status_counts": {"succeeded": 0, "reserved": 1, "failed": 0, "unknown": 0},
        },
    ):
        with pytest.raises(ConcurrencyLimitExceededError, match="Maximum concurrent request limit"):
            await ledger.reserve_budget(
                workspace_id=mock_workspace_id,
                feature="test",
                model="muse-spark-1.3",
                estimated_input_tokens=500,
                max_output_tokens=500,
            )


@pytest.mark.asyncio
async def test_spending_uncertainty_blocks_new_requests(test_settings: Settings, mock_workspace_id: uuid.UUID):
    """If any prior request has UNKNOWN outcome, refuse further requests."""
    session = AsyncMock(spec=AsyncSession)
    ledger = BudgetLedgerService(session=session, settings=test_settings)

    with patch.object(
        ledger,
        "get_budget_summary",
        return_value={
            "total_committed_usd": 0.0,
            "daily_spend_usd": 0.0,
            "status_counts": {"succeeded": 0, "reserved": 0, "failed": 0, "unknown": 1},
        },
    ):
        with pytest.raises(UnresolvedSpendingUncertaintyError, match="with UNKNOWN outcome"):
            await ledger.reserve_budget(
                workspace_id=mock_workspace_id,
                feature="test",
                model="muse-spark-1.3",
                estimated_input_tokens=500,
                max_output_tokens=500,
            )


@pytest.mark.asyncio
async def test_lifetime_budget_exhaustion_rejects_reservation(test_settings: Settings, mock_workspace_id: uuid.UUID):
    session = AsyncMock(spec=AsyncSession)
    ledger = BudgetLedgerService(session=session, settings=test_settings)

    # Mock get_budget_summary returning committed spend equal to $100.00
    with patch.object(
        ledger,
        "get_budget_summary",
        return_value={
            "total_committed_usd": 100.0,
            "daily_spend_usd": 1.0,
            "status_counts": {"succeeded": 10, "reserved": 0, "failed": 0, "unknown": 0},
        },
    ):
        with pytest.raises(BudgetExceededError, match="would exceed lifetime budget"):
            await ledger.reserve_budget(
                workspace_id=mock_workspace_id,
                feature="test",
                model="muse-spark-1.3",
                estimated_input_tokens=500,
                max_output_tokens=500,
            )


@pytest.mark.asyncio
async def test_daily_budget_exhaustion_rejects_reservation(test_settings: Settings, mock_workspace_id: uuid.UUID):
    session = AsyncMock(spec=AsyncSession)
    ledger = BudgetLedgerService(session=session, settings=test_settings)

    with patch.object(
        ledger,
        "get_budget_summary",
        return_value={
            "total_committed_usd": 10.0,
            "daily_spend_usd": 5.0,  # Daily cap reached
            "status_counts": {"succeeded": 5, "reserved": 0, "failed": 0, "unknown": 0},
        },
    ):
        with pytest.raises(BudgetExceededError, match="would exceed daily budget"):
            await ledger.reserve_budget(
                workspace_id=mock_workspace_id,
                feature="test",
                model="muse-spark-1.3",
                estimated_input_tokens=500,
                max_output_tokens=500,
            )


@pytest.mark.asyncio
async def test_initial_test_budget_exhaustion_rejects(test_settings: Settings, mock_workspace_id: uuid.UUID):
    session = AsyncMock(spec=AsyncSession)
    ledger = BudgetLedgerService(session=session, settings=test_settings)

    with patch.object(
        ledger,
        "get_budget_summary",
        return_value={
            "total_committed_usd": 5.0,  # Initial test limit reached
            "daily_spend_usd": 1.0,
            "status_counts": {"succeeded": 2, "reserved": 0, "failed": 0, "unknown": 0},
        },
    ):
        with pytest.raises(BudgetExceededError, match="would exceed initial test budget"):
            await ledger.reserve_budget(
                workspace_id=mock_workspace_id,
                feature="test",
                model="muse-spark-1.3",
                estimated_input_tokens=500,
                max_output_tokens=500,
            )


# =========================================================================
# 4. End-to-End Mocked Network Execution & Reconciliation Tests
# =========================================================================

@pytest.mark.asyncio
async def test_gateway_successful_call_and_reconciliation(test_settings: Settings, mock_workspace_id: uuid.UUID):
    """Verify standard happy-path: reserve, dispatch mock POST, reconcile actual usage, release excess."""
    session = AsyncMock(spec=AsyncSession)
    session.scalar.side_effect = [0, 0]  # active_count=0, unknown_count=0

    # Mock usage record returned by DB
    mock_record = ModelUsageRecord(
        id=uuid.uuid4(),
        workspace_id=mock_workspace_id,
        feature="unit_test",
        model="muse-spark-1.3",
        estimated_input_tokens=50,
        max_reserved_output_tokens=100,
        reserved_cost_usd=Decimal("0.000488"),
        actual_cost_usd=Decimal("0.000000"),
        status="RESERVED",
    )
    session.get.return_value = mock_record

    # Mock HTTP client returning 200 OK with valid Meta response format
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_response = AsyncMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.headers = {"x-meta-request-id": "req_meta_test_888"}
    mock_response.json.return_value = {
        "id": "resp_test_123",
        "choices": [
            {"message": {"role": "assistant", "content": "Governed memory validated."}}
        ],
        "usage": {
            "prompt_tokens": 45,
            "completion_tokens": 20,
            "total_tokens": 65,
        },
    }
    mock_client.post.return_value = mock_response

    gateway = MetaModelGateway(session=session, settings=test_settings, http_client=mock_client)

    with patch.object(
        gateway.ledger,
        "get_budget_summary",
        return_value={
            "total_committed_usd": 0.0,
            "daily_spend_usd": 0.0,
            "status_counts": {"succeeded": 0, "reserved": 0, "failed": 0, "unknown": 0},
        },
    ):
        result = await gateway.generate_response(
            workspace_id=mock_workspace_id,
            feature="unit_test",
            prompt="Verify invariant",
        )

        assert result["text"] == "Governed memory validated."
        assert result["usage"]["input_tokens"] == 45
        assert result["usage"]["output_tokens"] == 20
        assert result["usage"]["cost_usd"] > 0
        assert result["provider_request_id"] == "req_meta_test_888"

        # Verify state was marked SUCCEEDED in record
        assert mock_record.status == "SUCCEEDED"
        assert mock_record.actual_input_tokens == 45
        assert mock_record.actual_output_tokens == 20


@pytest.mark.asyncio
async def test_gateway_provider_error_releases_reservation(test_settings: Settings, mock_workspace_id: uuid.UUID):
    """When Meta returns an HTTP error (e.g. 400 Bad Request), fail safely and release reservation."""
    session = AsyncMock(spec=AsyncSession)
    session.scalar.side_effect = [0, 0]

    mock_record = ModelUsageRecord(
        id=uuid.uuid4(),
        workspace_id=mock_workspace_id,
        feature="unit_test",
        model="muse-spark-1.3",
        status="RESERVED",
    )
    session.get.return_value = mock_record

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_response = AsyncMock(spec=httpx.Response)
    mock_response.status_code = 400
    mock_response.text = '{"error": {"message": "Invalid parameter"}}'
    mock_client.post.return_value = mock_response

    gateway = MetaModelGateway(session=session, settings=test_settings, http_client=mock_client)

    with patch.object(
        gateway.ledger,
        "get_budget_summary",
        return_value={
            "total_committed_usd": 0.0,
            "daily_spend_usd": 0.0,
            "status_counts": {"succeeded": 0, "reserved": 0, "failed": 0, "unknown": 0},
        },
    ):
        with pytest.raises(MetaApiProviderError, match="Provider HTTP 400"):
            await gateway.generate_response(
                workspace_id=mock_workspace_id,
                feature="unit_test",
                prompt="Bad input",
            )

        assert mock_record.status == "FAILED"
        assert mock_record.actual_cost_usd == Decimal("0.000000")


@pytest.mark.asyncio
async def test_gateway_timeout_quarantines_record_as_unknown(test_settings: Settings, mock_workspace_id: uuid.UUID):
    """Network timeout MUST mark the record UNKNOWN and retain the reservation liability."""
    session = AsyncMock(spec=AsyncSession)
    session.scalar.side_effect = [0, 0]

    mock_record = ModelUsageRecord(
        id=uuid.uuid4(),
        workspace_id=mock_workspace_id,
        feature="unit_test",
        model="muse-spark-1.3",
        reserved_cost_usd=Decimal("0.008500"),
        status="RESERVED",
    )
    session.get.return_value = mock_record

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post.side_effect = httpx.ReadTimeout("Connection timed out after 30s")

    gateway = MetaModelGateway(session=session, settings=test_settings, http_client=mock_client)

    with patch.object(
        gateway.ledger,
        "get_budget_summary",
        return_value={
            "total_committed_usd": 0.0,
            "daily_spend_usd": 0.0,
            "status_counts": {"succeeded": 0, "reserved": 0, "failed": 0, "unknown": 0},
        },
    ):
        with pytest.raises(MetaApiTimeoutError, match="Reservation held in quarantine"):
            await gateway.generate_response(
                workspace_id=mock_workspace_id,
                feature="unit_test",
                prompt="Will time out",
            )

        # UNKNOWN status ensures funds are NOT refunded and blocks future requests
        assert mock_record.status == "UNKNOWN"
        assert "Ambiguous outcome / timeout" in mock_record.error_message
