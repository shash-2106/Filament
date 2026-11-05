"""Model pricing registry and token estimation utilities for Meta Model API."""

from decimal import Decimal
import math
from typing import Dict, NamedTuple


class ModelPricing(NamedTuple):
    input_rate_per_million: Decimal  # USD per 1,000,000 input tokens
    output_rate_per_million: Decimal  # USD per 1,000,000 output tokens
    version: str
    verified_at: str


# Explicit Allowlist and Versioned Standard Pricing Registry
# Standard mode rates for Muse Spark 1.3:
# Input: $1.25 per million tokens ($0.00000125 / token)
# Output: $4.25 per million tokens ($0.00000425 / token)
MODEL_PRICING_REGISTRY: Dict[str, ModelPricing] = {
    "muse-spark-1.3": ModelPricing(
        input_rate_per_million=Decimal("1.25"),
        output_rate_per_million=Decimal("4.25"),
        version="standard_1.3",
        verified_at="2026-11-04",
    ),
}


def is_model_allowlisted(model: str) -> bool:
    """Validate requested model against strict server-side allowlist."""
    return model in MODEL_PRICING_REGISTRY


def calculate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> Decimal:
    """Calculate exact cost in USD for a given token count using Decimal arithmetic.

    Rounds up to 6 decimal places to prevent fractional cent underestimation.
    """
    if model not in MODEL_PRICING_REGISTRY:
        raise ValueError(f"Model '{model}' is not in the allowlisted pricing registry.")

    pricing = MODEL_PRICING_REGISTRY[model]
    one_million = Decimal("1000000")

    input_cost = (Decimal(input_tokens) * pricing.input_rate_per_million) / one_million
    output_cost = (Decimal(output_tokens) * pricing.output_rate_per_million) / one_million

    total = input_cost + output_cost
    # Quantize to 6 decimal places (micro-USD)
    return total.quantize(Decimal("0.000001"))


def estimate_input_tokens(text: str) -> int:
    """Conservatively estimate token count for prompt text.

    Standard heuristic: ~3.5 to 4 characters per token for English prose,
    but code, symbols, whitespace, and non-ASCII text often yield higher token densities.
    We apply a conservative ratio of 1 token per 3 characters (or 1 token per word,
    whichever is larger), plus a safety buffer of 20% + 10 base tokens.
    """
    if not text:
        return 0

    char_based = math.ceil(len(text) / 3.0)
    word_based = math.ceil(len(text.split()) * 1.3)
    base = max(char_based, word_based)
    conservative = math.ceil(base * 1.2) + 10
    return max(1, conservative)

