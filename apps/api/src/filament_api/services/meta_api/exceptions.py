"""Custom exceptions for Meta Model API cost control and budget violations."""

class MetaApiError(Exception):
    """Base exception for all Meta API gateway operations."""
    pass


class MetaApiDisabledError(MetaApiError):
    """Raised when the Meta Model API gateway is disabled via configuration."""
    pass


class MetaApiKeyMissingError(MetaApiError):
    """Raised when the Meta Model API key is not configured."""
    pass


class ModelNotAllowlistedError(MetaApiError):
    """Raised when an unapproved model is requested."""
    pass


class TokenLimitExceededError(MetaApiError):
    """Raised when input or output token parameters exceed hard limits."""
    pass


class BudgetExceededError(MetaApiError):
    """Raised when a request reservation would exceed lifetime, daily, or test budget."""
    pass


class MaxRequestCostExceededError(MetaApiError):
    """Raised when estimated reservation cost for a single request exceeds ceiling."""
    pass


class ConcurrencyLimitExceededError(MetaApiError):
    """Raised when another request is already in-flight under strict concurrency controls."""
    pass


class UnresolvedSpendingUncertaintyError(MetaApiError):
    """Raised when prior requests with UNKNOWN outcome block further spending."""
    pass


class MetaApiProviderError(MetaApiError):
    """Raised when the external Meta API returns an error response."""
    pass


class MetaApiNoUsableOutputError(MetaApiError):
    """Raised when the model API request succeeds technically (e.g. HTTP 200)
    but produces no usable application text (e.g. empty output or only consumed reasoning tokens).
    Recorded as billable in the ledger but functionally unsuccessful.
    """
    pass


class MetaApiTimeoutError(MetaApiError):
    """Raised when the external Meta API request times out or outcome is ambiguous."""
    pass

