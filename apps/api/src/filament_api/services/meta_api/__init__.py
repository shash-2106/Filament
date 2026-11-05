"""Package entry point for Meta Model API integration."""

from filament_api.services.meta_api.exceptions import (
    BudgetExceededError,
    ConcurrencyLimitExceededError,
    MaxRequestCostExceededError,
    MetaApiDisabledError,
    MetaApiError,
    MetaApiKeyMissingError,
    MetaApiProviderError,
    MetaApiTimeoutError,
    ModelNotAllowlistedError,
    TokenLimitExceededError,
    UnresolvedSpendingUncertaintyError,
)
from filament_api.services.meta_api.gateway import MetaModelGateway
from filament_api.services.meta_api.ledger import BudgetLedgerService
from filament_api.services.meta_api.pricing import (
    MODEL_PRICING_REGISTRY,
    ModelPricing,
    calculate_cost_usd,
    estimate_input_tokens,
    is_model_allowlisted,
)

__all__ = [
    "BudgetExceededError",
    "BudgetLedgerService",
    "ConcurrencyLimitExceededError",
    "MaxRequestCostExceededError",
    "MetaApiDisabledError",
    "MetaApiError",
    "MetaApiKeyMissingError",
    "MetaApiProviderError",
    "MetaApiTimeoutError",
    "MetaModelGateway",
    "ModelNotAllowlistedError",
    "ModelPricing",
    "MODEL_PRICING_REGISTRY",
    "TokenLimitExceededError",
    "UnresolvedSpendingUncertaintyError",
    "calculate_cost_usd",
    "estimate_input_tokens",
    "is_model_allowlisted",
]

