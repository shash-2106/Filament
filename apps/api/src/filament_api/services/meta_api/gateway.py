"""Centralized Meta Model API Gateway.

Enforces pre-flight cost controls, token boundaries, atomic budget reservation,
and exact post-call usage reconciliation.

CRITICAL: Never makes an external call unless MODEL_API_ENABLED=true and all budget
and token checks pass. All outgoing requests use Standard mode only.
"""

from datetime import datetime, timezone
from decimal import Decimal
import logging
from typing import Any, Dict, List, Optional
import uuid
import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from filament_api.config import Settings, get_settings
from filament_api.models.model_usage import ModelUsageRecord
from filament_api.services.meta_api.exceptions import (
    MetaApiDisabledError,
    MetaApiKeyMissingError,
    MetaApiNoUsableOutputError,
    MetaApiProviderError,
    MetaApiTimeoutError,
    ModelNotAllowlistedError,
    TokenLimitExceededError,
)
from filament_api.services.meta_api.ledger import BudgetLedgerService
from filament_api.services.meta_api.pricing import (
    estimate_input_tokens,
    is_model_allowlisted,
)

logger = logging.getLogger(__name__)


class MetaModelGateway:
    """Centralized gateway for all Meta Model API requests.

    Every request goes through:
    1. Pre-flight checks (enabled, api_key, model allowlist, token limits).
    2. Conservative token estimation.
    3. Atomic database reservation of estimated cost.
    4. HTTP execution to https://api.meta.ai/v1/responses (Standard mode only).
    5. Post-response usage reconciliation (or timeout/unknown quarantine).
    """

    def __init__(
        self,
        session: AsyncSession,
        settings: Optional[Settings] = None,
        http_client: Optional[httpx.AsyncClient] = None,
    ):
        self.session = session
        self.settings = settings or get_settings()
        self.ledger = BudgetLedgerService(session=session, settings=self.settings)
        self.client = http_client

    async def generate_response(
        self,
        workspace_id: uuid.UUID,
        feature: str,
        prompt: str,
        max_output_tokens: Optional[int] = None,
        model: Optional[str] = None,
        system_instruction: Optional[str] = None,
        temperature: float = 0.0,
    ) -> Dict[str, Any]:
        """Generate a response using Meta Model API with strict budget enforcement.

        Parameters
        ----------
        workspace_id : uuid.UUID
            Target workspace UUID for isolation & ledger attributing.
        feature : str
            Operational feature calling the gateway (e.g., 'claim_extraction').
        prompt : str
            User/input prompt text.
        max_output_tokens : Optional[int]
            Maximum tokens to allow for model completion. Defaults to configured limit.
        model : Optional[str]
            Model name. Defaults to configured MODEL_API_MODEL.
        system_instruction : Optional[str]
            Optional system prompt instruction.
        temperature : float
            Sampling temperature (default 0.0 for deterministic outputs).

        Returns
        -------
        Dict[str, Any]
            Standardized response payload containing text, usage, and ledger record id.
        """
        # 1. Verify API integration is enabled
        if not self.settings.MODEL_API_ENABLED:
            raise MetaApiDisabledError(
                "Meta Model API gateway is disabled by configuration (MODEL_API_ENABLED=false)."
            )

        # 2. Verify API key is present
        api_key = self.settings.MODEL_API_KEY
        if not api_key or not api_key.strip():
            raise MetaApiKeyMissingError(
                "Meta Model API key is not configured (MODEL_API_KEY is empty)."
            )

        # 3. Resolve & validate requested model against allowlist
        target_model = model or self.settings.MODEL_API_MODEL
        if not is_model_allowlisted(target_model):
            raise ModelNotAllowlistedError(
                f"Model '{target_model}' is not allowlisted for Meta API integration."
            )

        # 4. Token limit validations & conservative estimation
        full_input_text = f"{system_instruction or ''}\n{prompt}"
        estimated_input_tokens = estimate_input_tokens(full_input_text)

        if estimated_input_tokens > self.settings.MODEL_API_MAX_INPUT_TOKENS:
            raise TokenLimitExceededError(
                f"Estimated input tokens ({estimated_input_tokens}) exceeds hard limit of "
                f"{self.settings.MODEL_API_MAX_INPUT_TOKENS} tokens."
            )

        effective_max_output = max_output_tokens or self.settings.MODEL_API_MAX_OUTPUT_TOKENS
        if effective_max_output > self.settings.MODEL_API_MAX_OUTPUT_TOKENS:
            raise TokenLimitExceededError(
                f"Requested max output tokens ({effective_max_output}) exceeds ceiling of "
                f"{self.settings.MODEL_API_MAX_OUTPUT_TOKENS} tokens."
            )

        # 5. Atomically reserve estimated budget in durable ledger BEFORE request
        usage_record = await self.ledger.reserve_budget(
            workspace_id=workspace_id,
            feature=feature,
            model=target_model,
            estimated_input_tokens=estimated_input_tokens,
            max_output_tokens=effective_max_output,
        )

        # 6. Execute HTTP request to Meta API (Standard OpenAI-compatible chat completions endpoint)
        endpoint_url = f"{self.settings.MODEL_API_BASE_URL.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key.strip()}",
            "Content-Type": "application/json",
            "User-Agent": "Filament-Governance-Gateway/1.0",
        }

        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": target_model,
            "messages": messages,
            "max_tokens": effective_max_output,
            "temperature": temperature,
            "reasoning_effort": "low",
        }

        # Use injected client if available (for mocking/tests), otherwise create transient client
        client_to_use = self.client
        created_transient = False
        if client_to_use is None:
            client_to_use = httpx.AsyncClient(timeout=30.0)
            created_transient = True

        try:
            response = await client_to_use.post(
                endpoint_url,
                json=payload,
                headers=headers,
            )

            # Check status code
            if response.status_code >= 400:
                error_msg = f"Provider HTTP {response.status_code}: {response.text[:300]}"
                # 4xx bad requests before billing can be marked non-billable FAILED
                # 5xx server errors might be ambiguous if upstream processed; mark FAILED only if verified
                await self.ledger.reconcile_failure(
                    record_id=usage_record.id,
                    error_message=error_msg,
                    billable_tokens=False,
                )
                raise MetaApiProviderError(error_msg)

            data = response.json()

            # Parse provider usage from response
            # Format expected: {"usage": {"prompt_tokens": 120, "completion_tokens": 85, "total_tokens": 205}}
            raw_usage = data.get("usage", {})
            actual_input = raw_usage.get("prompt_tokens", estimated_input_tokens)
            actual_output = raw_usage.get("completion_tokens", effective_max_output)
            provider_req_id = (
                response.headers.get("x-request-id")
                or response.headers.get("x-meta-request-id")
                or data.get("id")
            )

            # Reconcile usage and release excess reservation
            reconciled = await self.ledger.reconcile_success(
                record_id=usage_record.id,
                actual_input_tokens=actual_input,
                actual_output_tokens=actual_output,
                provider_request_id=provider_req_id,
            )

            # Extract response content safely
            # Expected schema: {"choices": [{"message": {"content": "..."}}]} or {"response": "..."}
            text_content = ""
            choices = data.get("choices")
            if choices and len(choices) > 0:
                first_choice = choices[0]
                if isinstance(first_choice, dict):
                    msg = first_choice.get("message", {})
                    text_content = msg.get("content") or ""
            elif "response" in data:
                text_content = str(data["response"])

            text_content = text_content.strip()

            # Phase 1 requirement: Distinguish between provider technical success (HTTP 200)
            # and usable application output. If no usable text was produced (e.g. all tokens
            # were consumed by hidden reasoning), record as billable in the ledger but raise
            # MetaApiNoUsableOutputError.
            if not text_content:
                error_msg = (
                    f"Model execution produced no usable output text (consumed {actual_output} "
                    f"tokens, likely reasoning-only or empty response)."
                )
                logger.warning(
                    "Meta API request %s succeeded technically but produced no usable text. "
                    "Actual cost $%.6f reconciled.",
                    usage_record.id,
                    reconciled.actual_cost_usd,
                )
                raise MetaApiNoUsableOutputError(error_msg)

            return {
                "text": text_content,
                "usage": {
                    "input_tokens": actual_input,
                    "output_tokens": actual_output,
                    "total_tokens": actual_input + actual_output,
                    "cost_usd": float(reconciled.actual_cost_usd),
                },
                "record_id": str(reconciled.id),
                "model": target_model,
                "provider_request_id": provider_req_id,
            }

        except (httpx.TimeoutException, httpx.ConnectTimeout, httpx.ReadTimeout) as exc:
            # Ambiguous outcome: mark UNKNOWN and lock reservation to prevent overruns
            logger.error(
                "Meta API request timed out. Marking record %s as UNKNOWN.",
                usage_record.id,
            )
            await self.ledger.mark_unknown(
                record_id=usage_record.id,
                error_message=f"Network timeout ({type(exc).__name__})",
            )
            raise MetaApiTimeoutError(
                f"Meta Model API timed out. Reservation held in quarantine (id: {usage_record.id})."
            ) from exc

        except httpx.RequestError as exc:
            # Network connect failure before request dispatch
            await self.ledger.reconcile_failure(
                record_id=usage_record.id,
                error_message=f"Network error ({type(exc).__name__}): {str(exc)}",
                billable_tokens=False,
            )
            raise MetaApiProviderError(f"Network error communicating with Meta API: {str(exc)}") from exc

        finally:
            if created_transient and client_to_use is not None:
                await client_to_use.aclose()

