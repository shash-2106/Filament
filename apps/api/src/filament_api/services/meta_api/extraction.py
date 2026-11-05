"""Domain service orchestrating candidate memory extraction via MetaModelGateway and governed persistence."""

import asyncio
import json
import logging
import re
from typing import Any, Dict, List, Optional
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from filament_api.services.context import TrustedContext
from filament_api.config import Settings, get_settings
from filament_api.schemas.claim import CreateClaimParams, LinkEvidenceParams
from filament_api.schemas.evidence import RecordEvidenceParams
from filament_api.schemas.extraction import (
    ApproveCandidateRequest,
    ApproveCandidateResponse,
    CandidateMemory,
    ExtractMemoriesRequest,
    ExtractMemoriesResponse,
    ExtractionEstimateResponse,
)
from filament_api.services.claim import ClaimService
from filament_api.services.condition import ConditionService
from filament_api.services.evidence import EvidenceService
from filament_api.services.meta_api.exceptions import (
    MetaApiDisabledError,
    MetaApiError,
    MetaApiNoUsableOutputError,
)
from filament_api.services.meta_api.gateway import MetaModelGateway
from filament_api.services.meta_api.pricing import calculate_cost_usd, estimate_input_tokens
from filament_api.services.snapshot import SnapshotService

logger = logging.getLogger(__name__)

SYSTEM_EXTRACTION_PROMPT = """You are a Memory Extraction specialist for Filament, an AI knowledge governance system.
Your job is to read an agent transcript or tool output and extract at most 3 concise, factual candidate memories.

CRITICAL GOVERNANCE RULES:
1. Extract at most 3 concise, high-value assertions (architectural decisions, verified facts, constraints, user preferences).
2. Every memory MUST cite an exact verbatim evidence excerpt directly from the text.
3. Keep statements concise. Avoid verbose descriptions, unnecessary repetition, or speculative claims.
4. If an assertion is obsolete, cancelled, or ambiguous, state that concisely in uncertainty_notes; otherwise omit uncertainty_notes.
5. Output MUST be a strictly valid, complete JSON array of objects with NO surrounding markdown backticks or commentary.

Compact Output Schema:
[
  {
    "statement": "concise memory statement",
    "evidence_quote": "exact verbatim quote from transcript",
    "source_reference": "turn number or participant",
    "claim_type": "fact" | "recommendation" | "decision" | "preference" | "constraint",
    "uncertainty_notes": "caveat only if obsolete/ambiguous, else omit"
  }
]
"""


class MemoryExtractionService:
    """Handles prompt construction, bounded inference via MetaModelGateway, schema validation, and persistence."""

    def __init__(
        self,
        session: AsyncSession,
        settings: Optional[Settings] = None,
        gateway: Optional[MetaModelGateway] = None,
    ):
        self.session = session
        self.settings = settings or get_settings()
        self.gateway = gateway or MetaModelGateway(session=session, settings=self.settings)

    async def get_estimate(self, transcript: str) -> ExtractionEstimateResponse:
        """Estimate tokens, cost, and budget headroom before user confirmation."""
        full_text = f"{SYSTEM_EXTRACTION_PROMPT}\n{transcript}"
        est_input = estimate_input_tokens(full_text)
        max_output = min(3000, self.settings.MODEL_API_MAX_OUTPUT_TOKENS)
        est_cost = calculate_cost_usd(self.settings.MODEL_API_MODEL, est_input, max_output)

        summary = await self.gateway.ledger.get_budget_summary(workspace_id=None)

        return ExtractionEstimateResponse(
            estimated_input_tokens=est_input,
            max_output_tokens=max_output,
            estimated_cost_usd=float(est_cost),
            model=self.settings.MODEL_API_MODEL,
            remaining_lifetime_budget_usd=summary["remaining_lifetime_budget_usd"],
            remaining_test_budget_usd=summary["remaining_test_budget_usd"],
            gateway_enabled=self.settings.MODEL_API_ENABLED,
        )

    async def extract_candidates(
        self,
        workspace_id: uuid.UUID,
        request: ExtractMemoriesRequest,
    ) -> ExtractMemoriesResponse:
        """Execute bounded model inference to extract candidate memories with strict validation."""
        if not request.user_confirmed_cost:
            raise ValueError("Explicit user cost confirmation is required prior to paid inference.")

        # Cap output tokens reasonably for memory extraction (max 3000 to allow reasoning + full JSON)
        effective_max_output = min(3000, self.settings.MODEL_API_MAX_OUTPUT_TOKENS)

        prompt = (
            f"Extract at most 3 concise candidate memories from the following transcript according to your system instructions:\n\n"
            f"--- TRANSCRIPT START ---\n{request.transcript}\n--- TRANSCRIPT END ---\n\n"
            f"Respond ONLY with the JSON array."
        )

        # Call centralized MetaModelGateway
        result = await self.gateway.generate_response(
            workspace_id=workspace_id,
            feature="memory_extraction",
            prompt=prompt,
            system_instruction=SYSTEM_EXTRACTION_PROMPT,
            max_output_tokens=effective_max_output,
            temperature=0.1,
        )

        raw_text = result.get("text", "").strip()
        if not raw_text:
            raise MetaApiNoUsableOutputError("Model returned an empty text response.")

        # Clean JSON markdown fences if present
        clean_json_str = raw_text
        if clean_json_str.startswith("```"):
            clean_json_str = re.sub(r"^```(?:json)?\s*", "", clean_json_str)
            clean_json_str = re.sub(r"\s*```$", "", clean_json_str)
        clean_json_str = clean_json_str.strip()

        try:
            parsed = json.loads(clean_json_str)
        except json.JSONDecodeError as exc:
            logger.error("Failed to parse model extraction response as JSON: %s", clean_json_str[:200])
            raise ValueError(f"Model response was not valid JSON: {str(exc)}") from exc

        if not isinstance(parsed, list):
            # If wrapped in a dictionary like {"memories": [...]}, unwrap it
            if isinstance(parsed, dict) and "memories" in parsed and isinstance(parsed["memories"], list):
                parsed = parsed["memories"]
            elif isinstance(parsed, dict) and "candidates" in parsed and isinstance(parsed["candidates"], list):
                parsed = parsed["candidates"]
            else:
                raise ValueError("Model extraction output must be a JSON array of candidate memory objects.")

        candidates: List[CandidateMemory] = []
        transcript_text = request.transcript.strip()

        for item in parsed:
            if not isinstance(item, dict):
                continue
            try:
                # Derive or populate optional metadata locally where safe
                raw_statement = item.get("statement", "")
                if "subject" not in item or not item["subject"]:
                    # Safely derive subject from first 3 words of statement or default to system
                    words = raw_statement.split()[:3]
                    item["subject"] = "_".join(words).lower() if words else "system"
                if "predicate" not in item or not item["predicate"]:
                    item["predicate"] = "assertion"

                cand = CandidateMemory(**item)
                # Evidence quote integrity: verify quote exists as substring of submitted transcript
                # Normalize whitespace to avoid rejecting minor indentation/spacing differences
                clean_quote = " ".join(cand.evidence_quote.split())
                clean_transcript = " ".join(transcript_text.split())
                if clean_quote not in clean_transcript:
                    logger.warning(
                        "Rejecting candidate: evidence quote '%s' is not an exact substring of transcript.",
                        cand.evidence_quote[:60],
                    )
                    continue

                candidates.append(cand)
            except Exception as e:
                logger.warning("Skipping malformed candidate item: %s. Error: %s", item, e)

        if not candidates and len(parsed) > 0:
            raise ValueError(
                "Extracted candidates failed validation: evidence quotes must be exact substrings of the submitted transcript."
            )

        return ExtractMemoriesResponse(
            candidates=candidates,
            usage=result["usage"],
            provider_request_id=result.get("provider_request_id"),
            record_id=result["record_id"],
            model=result["model"],
            explanation="Candidate memories extracted by Muse Spark. Review, edit, and approve each memory before persistence.",
        )

    async def approve_candidate(
        self,
        context: TrustedContext,
        request: ApproveCandidateRequest,
    ) -> ApproveCandidateResponse:
        """Persist an approved candidate memory into governed storage with immutable evidence and optional conditions."""
        # 1. Record immutable evidence record for the transcript excerpt
        evidence_params = RecordEvidenceParams(
            source_type="user_turn",
            source_uri=request.source_uri,
            raw_snippet=request.evidence_quote,
            metadata={"approved_from_model_extraction": True},
        )
        evidence = await EvidenceService.record_evidence(
            session=self.session,
            context=context,
            params=evidence_params,
        )

        # Prevent duplicate identical claims within the same workspace and statement
        from sqlalchemy import select
        from filament_api.models.claim import Claim
        existing_claim_stmt = select(Claim).where(
            Claim.workspace_id == context.workspace_id,
            Claim.raw_statement == request.statement.strip(),
        )
        existing_res = await self.session.execute(existing_claim_stmt)
        if hasattr(existing_res, "scalar_one_or_none"):
            existing = existing_res.scalar_one_or_none()
            if asyncio.iscoroutine(existing):
                existing = await existing
        else:
            existing = None
        if existing:
            return ApproveCandidateResponse(
                claim_id=existing.id,
                evidence_id=evidence.id,
                condition_set_id=None,
                status=existing.status,
                message="Memory already exists in this workspace. Evidence link recorded without duplication.",
            )

        # 2. Record the Claim / Memory
        claim_params = CreateClaimParams(
            subject=request.subject,
            predicate=request.predicate,
            object_value={"statement": request.statement},
            raw_statement=request.statement,
            claim_type=request.claim_type,
            scope=request.scope,
            status="current",
            confidence=request.confidence,
        )
        claim = await ClaimService.create_claim(
            session=self.session,
            context=context,
            params=claim_params,
        )

        # 3. Link Evidence to Claim with provenance
        link_params = LinkEvidenceParams(
            claim_id=claim.id,
            evidence_id=evidence.id,
            support_type="supports",
            confidence_weight=request.confidence,
            extraction_notes=f"Source: {request.source_uri}",
        )
        await ClaimService.link_evidence(
            session=self.session,
            context=context,
            params=link_params,
        )

        # 4. If snapshot_id provided and conditions specified, establish baseline conditions
        condition_set_id = None
        if request.snapshot_id and request.condition_rules:
            # Verify snapshot exists and belongs to workspace
            snapshot = await SnapshotService.get_snapshot_by_id(
                session=self.session,
                context=context,
                snapshot_id=request.snapshot_id,
            )
            if snapshot:
                rules_to_establish = []
                for idx, rule in enumerate(request.condition_rules):
                    rules_to_establish.append({
                        "key": f"condition_{idx + 1}",
                        "operator": "equals",
                        "expected_value": rule,
                        "description": rule,
                    })
                cond_set = await ConditionService.establish_initial_conditions(
                    session=self.session,
                    context=context,
                    claim_id=claim.id,
                    snapshot_id=request.snapshot_id,
                    rules=rules_to_establish,
                )
                condition_set_id = cond_set.id

        await self.session.commit()

        return ApproveCandidateResponse(
            claim_id=claim.id,
            evidence_id=evidence.id,
            condition_set_id=condition_set_id,
            status="current",
            message="Candidate memory approved and successfully stored with provenance.",
        )
