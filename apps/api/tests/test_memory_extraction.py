"""Comprehensive unit and integration tests for candidate memory extraction with mocked Meta responses."""

import json
from unittest.mock import AsyncMock, patch
import uuid
import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from filament_api.services.context import TrustedContext
from filament_api.config import Settings
from filament_api.models.claim import Claim
from filament_api.models.evidence import Evidence
from filament_api.models.model_usage import ModelUsageRecord
from filament_api.schemas.extraction import (
    ApproveCandidateRequest,
    CandidateMemory,
    ExtractMemoriesRequest,
)
from filament_api.services.meta_api.exceptions import (
    BudgetExceededError,
    ConcurrencyLimitExceededError,
    MetaApiDisabledError,
    MetaApiNoUsableOutputError,
    MetaApiTimeoutError,
)
from filament_api.services.meta_api.extraction import MemoryExtractionService
from filament_api.services.meta_api.gateway import MetaModelGateway


@pytest.fixture
def test_settings() -> Settings:
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


@pytest.fixture
def mock_agent_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def mock_context(mock_workspace_id: uuid.UUID, mock_agent_id: uuid.UUID) -> TrustedContext:
    return TrustedContext(
        workspace_id=mock_workspace_id,
        actor_id=mock_agent_id,
        actor_type="agent",
        is_active=True,
    )


@pytest.fixture
def valid_candidate_json() -> str:
    return json.dumps([
        {
            "subject": "database_connection",
            "predicate": "requires_ssl",
            "statement": "Production PostgreSQL database requires SSL mode with verify-full.",
            "claim_type": "decision",
            "scope": "workspace",
            "confidence": 0.95,
            "evidence_quote": "We decided to enforce sslmode=verify-full across all database connections.",
            "source_reference": "Architect review turn 4",
            "suggested_validity_requirements": ["PostgreSQL 15+", "Valid CA certificate in trust store"],
            "relevant_files": ["apps/api/src/filament_api/config.py"],
            "uncertainty_notes": "Needs verification on staging environment.",
            "suggested_relationships": ["database_configuration"],
        }
    ])


@pytest.mark.asyncio
async def test_successful_candidate_memory_extraction(
    test_settings: Settings,
    mock_workspace_id: uuid.UUID,
    valid_candidate_json: str,
):
    """Test standard happy-path: mock Meta returns valid JSON array of candidates."""
    session = AsyncMock(spec=AsyncSession)
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_response = AsyncMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.headers = {"x-meta-request-id": "req_meta_ext_001"}
    mock_response.json.return_value = {
        "id": "resp_ext_001",
        "choices": [
            {"message": {"content": valid_candidate_json}}
        ],
        "usage": {
            "prompt_tokens": 120,
            "completion_tokens": 85,
            "total_tokens": 205,
        },
    }
    mock_client.post.return_value = mock_response

    mock_record = ModelUsageRecord(
        id=uuid.uuid4(),
        workspace_id=mock_workspace_id,
        feature="memory_extraction",
        model="muse-spark-1.3",
        status="RESERVED",
    )
    session.get.return_value = mock_record

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
        service = MemoryExtractionService(session=session, settings=test_settings, gateway=gateway)
        req = ExtractMemoriesRequest(
            transcript="Turn 4: We decided to enforce sslmode=verify-full across all database connections.",
            user_confirmed_cost=True,
        )
        res = await service.extract_candidates(workspace_id=mock_workspace_id, request=req)

        assert len(res.candidates) == 1
        cand = res.candidates[0]
        assert cand.subject == "database_connection"
        assert cand.predicate == "requires_ssl"
        assert cand.claim_type == "decision"
        assert "sslmode=verify-full" in cand.evidence_quote
        assert res.usage["input_tokens"] == 120
        assert res.usage["output_tokens"] == 85
        assert res.provider_request_id == "req_meta_ext_001"


@pytest.mark.asyncio
async def test_extraction_fails_when_user_cost_not_confirmed(
    test_settings: Settings,
    mock_workspace_id: uuid.UUID,
):
    """Refuse execution if user_confirmed_cost is false."""
    session = AsyncMock(spec=AsyncSession)
    service = MemoryExtractionService(session=session, settings=test_settings)
    req = ExtractMemoriesRequest(
        transcript="Some agent transcript here",
        user_confirmed_cost=False,
    )
    with pytest.raises(ValueError, match="Explicit user cost confirmation is required"):
        await service.extract_candidates(workspace_id=mock_workspace_id, request=req)


@pytest.mark.asyncio
async def test_extraction_handles_empty_model_output(
    test_settings: Settings,
    mock_workspace_id: uuid.UUID,
):
    """When provider returns 200 OK but choices content is empty, raise MetaApiNoUsableOutputError."""
    session = AsyncMock(spec=AsyncSession)
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_response = AsyncMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.headers = {}
    mock_response.json.return_value = {
        "choices": [{"message": {"content": ""}}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 200, "total_tokens": 300},
    }
    mock_client.post.return_value = mock_response

    mock_record = ModelUsageRecord(
        id=uuid.uuid4(),
        workspace_id=mock_workspace_id,
        feature="memory_extraction",
        model="muse-spark-1.3",
        status="RESERVED",
    )
    session.get.return_value = mock_record

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
        service = MemoryExtractionService(session=session, settings=test_settings, gateway=gateway)
        req = ExtractMemoriesRequest(transcript="Some conversation", user_confirmed_cost=True)
        with pytest.raises(MetaApiNoUsableOutputError, match="no usable output text"):
            await service.extract_candidates(workspace_id=mock_workspace_id, request=req)


@pytest.mark.asyncio
async def test_extraction_handles_invalid_json_output(
    test_settings: Settings,
    mock_workspace_id: uuid.UUID,
):
    """When provider returns plain non-JSON text, fail gracefully with clear validation error."""
    session = AsyncMock(spec=AsyncSession)
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_response = AsyncMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.headers = {}
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "Here are your memories: 1. DB needs SSL."}}],
        "usage": {"prompt_tokens": 50, "completion_tokens": 20, "total_tokens": 70},
    }
    mock_client.post.return_value = mock_response

    mock_record = ModelUsageRecord(
        id=uuid.uuid4(),
        workspace_id=mock_workspace_id,
        feature="memory_extraction",
        model="muse-spark-1.3",
        status="RESERVED",
    )
    session.get.return_value = mock_record

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
        service = MemoryExtractionService(session=session, settings=test_settings, gateway=gateway)
        req = ExtractMemoriesRequest(transcript="Some transcript excerpt", user_confirmed_cost=True)
        with pytest.raises(ValueError, match="not valid JSON"):
            await service.extract_candidates(workspace_id=mock_workspace_id, request=req)


@pytest.mark.asyncio
async def test_approve_candidate_memory_workflow(
    test_settings: Settings,
    mock_context: TrustedContext,
):
    """Test approving a candidate persists evidence, claim, and provenance link atomically."""
    session = AsyncMock(spec=AsyncSession)

    service = MemoryExtractionService(session=session, settings=test_settings)
    appr_req = ApproveCandidateRequest(
        subject="vector_index",
        predicate="indexing_algorithm",
        statement="HNSW index with cosine distance chosen for semantic search.",
        claim_type="decision",
        scope="workspace",
        confidence=0.90,
        evidence_quote="Turn 2: We selected HNSW indexing with cosine distance metric for fast vector queries.",
        source_uri="conversation_transcript_turn_2",
    )

    with patch("filament_api.services.evidence.EvidenceService.record_evidence") as mock_record_ev, \
         patch("filament_api.services.claim.ClaimService.create_claim") as mock_create_claim, \
         patch("filament_api.services.claim.ClaimService.link_evidence") as mock_link_ev:

        mock_ev = AsyncMock(spec=Evidence)
        mock_ev.id = uuid.uuid4()
        mock_record_ev.return_value = mock_ev

        mock_cl = AsyncMock(spec=Claim)
        mock_cl.id = uuid.uuid4()
        mock_create_claim.return_value = mock_cl

        mock_link_ev.return_value = AsyncMock()

        mock_exec_result = AsyncMock()
        mock_exec_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_exec_result

        res = await service.approve_candidate(context=mock_context, request=appr_req)

        assert res.claim_id == mock_cl.id
        assert res.evidence_id == mock_ev.id
        assert res.status == "current"
        session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_extraction_rejects_hallucinated_quotes_not_in_transcript(
    test_settings: Settings,
    mock_workspace_id: uuid.UUID,
):
    """Quotes not found in submitted transcript must be rejected, not silently accepted."""
    session = AsyncMock(spec=AsyncSession)
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_response = AsyncMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.headers = {}
    
    # Model hallucinated a quote not present in transcript
    hallucinated_json = json.dumps([
        {
            "subject": "cache_layer",
            "predicate": "enabled",
            "statement": "Redis caching is enabled.",
            "claim_type": "fact",
            "scope": "workspace",
            "confidence": 0.9,
            "evidence_quote": "We implemented Redis cluster caching yesterday.",
            "source_reference": "turn 1",
        }
    ])
    mock_response.json.return_value = {
        "choices": [{"message": {"content": hallucinated_json}}],
        "usage": {"prompt_tokens": 50, "completion_tokens": 40, "total_tokens": 90},
    }
    mock_client.post.return_value = mock_response

    mock_record = ModelUsageRecord(
        id=uuid.uuid4(),
        workspace_id=mock_workspace_id,
        feature="memory_extraction",
        model="muse-spark-1.3",
        status="RESERVED",
    )
    session.get.return_value = mock_record
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
        service = MemoryExtractionService(session=session, settings=test_settings, gateway=gateway)
        # The transcript does NOT contain the quote
        req = ExtractMemoriesRequest(
            transcript="Turn 1: We talked about PostgreSQL database configurations and SSL.",
            user_confirmed_cost=True,
        )
        with pytest.raises(ValueError, match="evidence quotes must be exact substrings"):
            await service.extract_candidates(workspace_id=mock_workspace_id, request=req)


@pytest.mark.asyncio
async def test_repeated_approval_does_not_duplicate_claims(
    test_settings: Settings,
    mock_context: TrustedContext,
):
    """Repeated approval of the same statement returns the existing claim rather than duplicating."""
    session = AsyncMock(spec=AsyncSession)
    service = MemoryExtractionService(session=session, settings=test_settings)
    appr_req = ApproveCandidateRequest(
        subject="vector_index",
        predicate="indexing_algorithm",
        statement="HNSW index with cosine distance chosen for semantic search.",
        claim_type="decision",
        scope="workspace",
        confidence=0.90,
        evidence_quote="Turn 2: We selected HNSW indexing with cosine distance metric for fast vector queries.",
        source_uri="conversation_transcript_turn_2",
    )

    with patch("filament_api.services.evidence.EvidenceService.record_evidence") as mock_record_ev:
        mock_ev = AsyncMock(spec=Evidence)
        mock_ev.id = uuid.uuid4()
        mock_record_ev.return_value = mock_ev

        # Simulate existing claim found in DB with matching workspace_id
        existing_claim = AsyncMock(spec=Claim)
        existing_claim.id = uuid.uuid4()
        existing_claim.workspace_id = mock_context.workspace_id
        existing_claim.status = "current"

        mock_exec_result = AsyncMock()
        mock_exec_result.scalar_one_or_none.return_value = existing_claim
        session.execute.return_value = mock_exec_result

        with patch("filament_api.services.claim.ClaimService.link_evidence") as mock_link_ev:
            mock_link_ev.return_value = AsyncMock()

            res = await service.approve_candidate(context=mock_context, request=appr_req)
            assert res.claim_id == existing_claim.id
            assert "already exists" in res.message


@pytest.mark.asyncio
async def test_extraction_rejects_when_budget_exhausted(
    test_settings: Settings,
    mock_workspace_id: uuid.UUID,
):
    """Test gateway blocks extraction when lifetime or daily budget is exhausted."""
    session = AsyncMock(spec=AsyncSession)
    gateway = MetaModelGateway(session=session, settings=test_settings)

    with patch.object(
        gateway.ledger,
        "get_budget_summary",
        return_value={
            "total_committed_usd": 100.0,
            "daily_spend_usd": 0.0,
            "status_counts": {"succeeded": 10, "reserved": 0, "failed": 0, "unknown": 0},
        },
    ):
        service = MemoryExtractionService(session=session, settings=test_settings, gateway=gateway)
        req = ExtractMemoriesRequest(transcript="Some transcript excerpt", user_confirmed_cost=True)
        with pytest.raises(BudgetExceededError, match="would exceed lifetime budget"):
            await service.extract_candidates(workspace_id=mock_workspace_id, request=req)


@pytest.mark.asyncio
async def test_compact_valid_output_and_missing_optional_metadata(
    test_settings: Settings,
    mock_workspace_id: uuid.UUID,
):
    """Test compact valid JSON output where optional metadata fields are omitted and safely derived."""
    session = AsyncMock(spec=AsyncSession)
    gateway = MetaModelGateway(session=session, settings=test_settings)

    transcript = "We established that all production clusters must run Postgres 15 with SSL mode verify-full."
    compact_candidates = [
        {
            "statement": "Production clusters must run Postgres 15 with SSL mode verify-full.",
            "evidence_quote": "all production clusters must run Postgres 15 with SSL mode verify-full",
            "source_reference": "Lead Architect",
            "claim_type": "decision",
            "uncertainty_notes": None,
        }
    ]

    mock_response_data = {
        "text": json.dumps(compact_candidates),
        "usage": {"prompt_tokens": 120, "completion_tokens": 150, "total_tokens": 270, "cost_usd": 0.0007875},
        "model": "muse-spark-1.3",
        "provider_request_id": "test_req_compact_01",
        "record_id": str(uuid.uuid4()),
    }

    with patch.object(gateway, "generate_response", return_value=mock_response_data):
        service = MemoryExtractionService(session=session, settings=test_settings, gateway=gateway)
        req = ExtractMemoriesRequest(transcript=transcript, user_confirmed_cost=True)
        resp = await service.extract_candidates(workspace_id=mock_workspace_id, request=req)

        assert len(resp.candidates) == 1
        cand = resp.candidates[0]
        assert cand.statement == "Production clusters must run Postgres 15 with SSL mode verify-full."
        assert cand.claim_type == "decision"
        assert cand.evidence_quote == "all production clusters must run Postgres 15 with SSL mode verify-full"
        assert cand.subject != ""
        assert cand.predicate != ""
        assert cand.scope == "team"  # Default
        assert cand.suggested_validity_requirements == []  # Optional field cleanly defaulted


@pytest.mark.asyncio
async def test_truncated_json_is_strictly_rejected_no_salvage(
    test_settings: Settings,
    mock_workspace_id: uuid.UUID,
):
    """Test that truncated JSON output raises a strict ValueError and does not attempt partial recovery."""
    session = AsyncMock(spec=AsyncSession)
    gateway = MetaModelGateway(session=session, settings=test_settings)

    transcript = "Turn 1: We configured pool size to 5 connections. Turn 2: SSL mode verify-full."
    # Truncated string cutting off mid-object
    truncated_json = '[{"statement": "Pool size configured to 5 connections", "evidence_quote": "pool size to 5 connections", "claim_type": "decision"'

    mock_response_data = {
        "text": truncated_json,
        "usage": {"prompt_tokens": 150, "completion_tokens": 1500, "total_tokens": 1650, "cost_usd": 0.0065625},
        "model": "muse-spark-1.3",
        "provider_request_id": "test_req_trunc_01",
        "record_id": str(uuid.uuid4()),
    }

    with patch.object(gateway, "generate_response", return_value=mock_response_data):
        service = MemoryExtractionService(session=session, settings=test_settings, gateway=gateway)
        req = ExtractMemoriesRequest(transcript=transcript, user_confirmed_cost=True)
        with pytest.raises(ValueError, match="Model response was not valid JSON"):
            await service.extract_candidates(workspace_id=mock_workspace_id, request=req)


@pytest.mark.asyncio
async def test_invalid_evidence_quote_rejected(
    test_settings: Settings,
    mock_workspace_id: uuid.UUID,
):
    """Test candidate whose evidence quote is not in transcript is rejected."""
    session = AsyncMock(spec=AsyncSession)
    gateway = MetaModelGateway(session=session, settings=test_settings)

    transcript = "Turn 1: We deployed the database on GCP Compute Engine."
    hallucinated_candidates = [
        {
            "statement": "Database runs on AWS Aurora.",
            "evidence_quote": "We deployed the database on AWS Aurora RDS",
            "source_reference": "DevOps",
            "claim_type": "fact",
        }
    ]

    mock_response_data = {
        "text": json.dumps(hallucinated_candidates),
        "usage": {"prompt_tokens": 100, "completion_tokens": 80, "total_tokens": 180, "cost_usd": 0.000465},
        "model": "muse-spark-1.3",
        "provider_request_id": "test_req_hallucinated_01",
        "record_id": str(uuid.uuid4()),
    }

    with patch.object(gateway, "generate_response", return_value=mock_response_data):
        service = MemoryExtractionService(session=session, settings=test_settings, gateway=gateway)
        req = ExtractMemoriesRequest(transcript=transcript, user_confirmed_cost=True)
        with pytest.raises(ValueError, match="evidence quotes must be exact substrings"):
            await service.extract_candidates(workspace_id=mock_workspace_id, request=req)


@pytest.mark.asyncio
async def test_three_candidate_extraction_success(
    test_settings: Settings,
    mock_workspace_id: uuid.UUID,
):
    """Test extracting exactly 3 candidate memories from the 3-turn transcript with exact quotes."""
    session = AsyncMock(spec=AsyncSession)
    gateway = MetaModelGateway(session=session, settings=test_settings)

    transcript = (
        "Turn 1 (Lead Systems Architect):\n"
        "We concluded our evaluation of PostgreSQL connection pooling. We decided that pgvector queries must run with an isolated pool of 5 connections and statement timeouts capped at 15 seconds.\n\n"
        "Turn 2 (Security Lead):\n"
        "Confirmed. In addition, production TLS certificate verification is mandatory using sslmode=verify-full. We will reject any connection string that uses sslmode=disable.\n\n"
        "Turn 3 (DevOps):\n"
        "Note that previously we discussed using SQLite for local development, but that plan is obsolete and officially cancelled since we standardized on Docker PostgreSQL 15."
    )

    three_candidates = [
        {
            "statement": "pgvector queries must run with an isolated pool of 5 connections and statement timeouts capped at 15 seconds.",
            "evidence_quote": "pgvector queries must run with an isolated pool of 5 connections and statement timeouts capped at 15 seconds",
            "source_reference": "Turn 1 (Lead Systems Architect)",
            "claim_type": "decision",
        },
        {
            "statement": "Production TLS certificate verification is mandatory using sslmode=verify-full.",
            "evidence_quote": "production TLS certificate verification is mandatory using sslmode=verify-full",
            "source_reference": "Turn 2 (Security Lead)",
            "claim_type": "constraint",
        },
        {
            "statement": "Plan to use SQLite for local development is obsolete and officially cancelled.",
            "evidence_quote": "previously we discussed using SQLite for local development, but that plan is obsolete and officially cancelled",
            "source_reference": "Turn 3 (DevOps)",
            "claim_type": "decision",
            "uncertainty_notes": "Obsolete/cancelled architecture plan",
        },
    ]

    mock_response_data = {
        "text": json.dumps(three_candidates),
        "usage": {"prompt_tokens": 450, "completion_tokens": 350, "total_tokens": 800, "cost_usd": 0.00205},
        "model": "muse-spark-1.3",
        "provider_request_id": "test_req_three_01",
        "record_id": str(uuid.uuid4()),
    }

    with patch.object(gateway, "generate_response", return_value=mock_response_data):
        service = MemoryExtractionService(session=session, settings=test_settings, gateway=gateway)
        req = ExtractMemoriesRequest(transcript=transcript, user_confirmed_cost=True)
        resp = await service.extract_candidates(workspace_id=mock_workspace_id, request=req)

        assert len(resp.candidates) == 3
        assert resp.candidates[0].claim_type == "decision"
        assert resp.candidates[1].claim_type == "constraint"
        assert resp.candidates[2].uncertainty_notes == "Obsolete/cancelled architecture plan"
        for c in resp.candidates:
            clean_q = " ".join(c.evidence_quote.split())
            clean_t = " ".join(transcript.split())
            assert clean_q in clean_t


@pytest.mark.asyncio
async def test_zero_automatic_retries_on_failure(
    test_settings: Settings,
    mock_workspace_id: uuid.UUID,
):
    """Verify that if model inference or validation fails, exactly 1 call was attempted (zero retries)."""
    session = AsyncMock(spec=AsyncSession)
    gateway = MetaModelGateway(session=session, settings=test_settings)

    transcript = "Turn 1: Some transcript line."
    call_count = 0

    async def mock_generate(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        raise httpx.ConnectTimeout("Connection timed out to Meta API endpoint")

    with patch.object(gateway, "generate_response", side_effect=mock_generate):
        service = MemoryExtractionService(session=session, settings=test_settings, gateway=gateway)
        req = ExtractMemoriesRequest(transcript=transcript, user_confirmed_cost=True)
        with pytest.raises(httpx.ConnectTimeout):
            await service.extract_candidates(workspace_id=mock_workspace_id, request=req)

        assert call_count == 1, "Must execute exactly one attempt without automatic retries."
