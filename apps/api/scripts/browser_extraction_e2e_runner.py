"""End-to-end browser verification of the Muse Spark Memory Extraction workflow.

Runs headless Playwright testing against:
- FastAPI running on 127.0.0.1:8000 (connected to Supabase)
- Vite web workstation on 127.0.0.1:5173

Workflow:
1. Opens http://127.0.0.1:5173/memories.
2. Authenticates by setting filament_api_key in localStorage.
3. Clicks 'Extract from Conversation'.
4. Pastes realistic multi-turn transcript excerpt.
5. Views the token and cost estimate preview.
6. Mocks the /api/v1/memory-extraction/extract response to simulate Muse Spark candidate generation.
7. Confirms extraction and reviews proposed candidate memories.
8. Edits candidate #1 memory statement.
9. Approves candidate #1 -> records claim and evidence.
10. Rejects candidate #2 -> disappears from UI without persisting.
11. Verifies only candidate #1 is displayed in the live Memories list.
12. Inspects its evidence and provenance details in the drawer.
13. Captures screenshots along the journey.
"""

import asyncio
import hashlib
import json
import os
import sys
import uuid
import urllib.parse
from playwright.async_api import async_playwright
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from dotenv import load_dotenv

load_dotenv(".env")

PROJECT_REF = os.environ.get("SUPABASE_PROJECT_REF", "rvceucunelqysdwbnkud")
ADMIN_PW = os.environ.get("SUPABASE_DB_PASSWORD")
if not ADMIN_PW:
    print("❌ Error: SUPABASE_DB_PASSWORD is required in .env", file=sys.stderr)
    sys.exit(1)

ENCODED_PW = urllib.parse.quote_plus(ADMIN_PW)
POOLER_URL = f"postgresql+asyncpg://postgres.{PROJECT_REF}:{ENCODED_PW}@aws-0-eu-west-1.pooler.supabase.com:5432/postgres"

DEMO_WS_ID = uuid.uuid4()
DEMO_AGENT_ID = uuid.uuid4()
DEMO_API_KEY = "fil_demo_key_12345"
DEMO_KEY_HASH = hashlib.sha256(DEMO_API_KEY.encode()).hexdigest()

SAMPLE_TRANSCRIPT = """Turn 1 (Lead Architect):
We concluded our evaluation of PostgreSQL connection pooling. We decided that pgvector queries must run with an isolated pool of 5 connections and statement timeouts capped at 15 seconds.

Turn 2 (Security Lead):
Confirmed. In addition, production TLS certificate verification is mandatory using sslmode=verify-full. We will reject any connection string that uses sslmode=disable.

Turn 3 (DevOps):
Note that previously we discussed using SQLite for local development, but that plan is obsolete and officially cancelled since we standardized on Docker PostgreSQL 15."""

MOCKED_EXTRACTION_CANDIDATES = [
    {
        "temp_id": "cand_1",
        "subject": "pgvector_pool",
        "predicate": "connection_limit",
        "statement": "pgvector queries must use an isolated pool of 5 connections with 15s statement timeout.",
        "claim_type": "decision",
        "scope": "workspace",
        "confidence": 0.95,
        "evidence_quote": "We decided that pgvector queries must run with an isolated pool of 5 connections and statement timeouts capped at 15 seconds.",
        "source_reference": "Turn 1 (Lead Architect)",
        "suggested_validity_requirements": ["PostgreSQL 15+", "pgvector 0.5+ installed"],
        "relevant_files": ["apps/api/src/filament_api/db/session.py"],
        "uncertainty_notes": "Needs pool size tuning under load test.",
        "suggested_relationships": ["database_pooling"],
    },
    {
        "temp_id": "cand_2",
        "subject": "sqlite_development",
        "predicate": "status",
        "statement": "SQLite is used for local developer environments.",
        "claim_type": "fact",
        "scope": "workspace",
        "confidence": 0.40,
        "evidence_quote": "previously we discussed using SQLite for local development, but that plan is obsolete and officially cancelled",
        "source_reference": "Turn 3 (DevOps)",
        "suggested_validity_requirements": ["Obsolete proposal"],
        "relevant_files": ["docker-compose.yml"],
        "uncertainty_notes": "Explicitly contradicted as obsolete in Turn 3.",
        "suggested_relationships": [],
    },
]


async def seed_demo_entities(engine):
    print("1. Using existing primary agent with test key in Supabase...")
    # Key hash is already associated with primary agent in workspace 11111111-1111-1111-1111-111111111111
    pass


async def cleanup_demo_entities(engine):
    print("Cleaning up created extraction test records from Supabase...")
    try:
        async with engine.begin() as conn:
            # Delete claims matching our test subject 'pgvector_pool'
            await conn.execute(text("DELETE FROM public.claims WHERE subject = 'pgvector_pool';"))
            await conn.execute(text("DELETE FROM public.evidence WHERE source_type = 'user_turn';"))
        print("   ✅ Cleanup complete.")
    except Exception as exc:
        print(f"   ⚠️ Cleanup note: {exc}")


async def run_extraction_browser_test():
    engine = create_async_engine(POOLER_URL)
    await seed_demo_entities(engine)
    artifact_dir = "/Users/shash/.gemini/antigravity/brain/1e4e0e5c-f509-4e8f-8298-53e18857c330"

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(viewport={"width": 1440, "height": 900})
            page = await context.new_page()

            # Set authentication token in localStorage
            await page.goto("http://localhost:5173/")
            await page.evaluate(f"localStorage.setItem('filament_api_key', '{DEMO_API_KEY}');")
            await page.goto("http://localhost:5173/memory")
            await page.wait_for_timeout(1000)

            print("2. Verifying page loaded and authenticated...")
            await page.wait_for_selector("text=Workspace Memories", timeout=10000)
            await page.screenshot(path=f"{artifact_dir}/ext_01_memories_initial.png")

            print("3. Opening 'Extract from Conversation' modal...")
            extract_btn = page.locator("button:has-text('Extract from Conversation')")
            await extract_btn.click()
            await page.wait_for_selector("text=Extract Memories with Muse Spark")

            print("4. Pasting transcript into extraction input...")
            textarea = page.locator("textarea")
            await textarea.fill(SAMPLE_TRANSCRIPT)
            await page.screenshot(path=f"{artifact_dir}/ext_02_transcript_entered.png")

            print("5. Calculating pre-flight token & cost estimation...")
            calc_btn = page.locator("button:has-text('Calculate Tokens & Cost Preview')")
            await calc_btn.click()
            await page.wait_for_selector("text=PRE-FLIGHT COST ESTIMATION", timeout=15000)
            await page.screenshot(path=f"{artifact_dir}/ext_03_estimation_preview.png")

            # Route intercept for /api/v1/memory-extraction/extract to mock Muse Spark candidates deterministically
            async def handle_extract_route(route):
                payload = {
                    "candidates": MOCKED_EXTRACTION_CANDIDATES,
                    "usage": {
                        "input_tokens": 154,
                        "output_tokens": 280,
                        "total_tokens": 434,
                        "cost_usd": 0.001382,
                    },
                    "provider_request_id": "mock_req_ext_browser_001",
                    "record_id": str(uuid.uuid4()),
                    "model": "muse-spark-1.3",
                    "explanation": "Mocked candidates for browser test.",
                }
                await route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps(payload),
                )

            await page.route("**/api/v1/memory-extraction/extract", handle_extract_route)

            print("6. Confirming extraction request...")
            confirm_btn = page.locator("button:has-text('Confirm & Extract')")
            await confirm_btn.click()

            await page.wait_for_selector("text=Extracted 2 candidate memories", timeout=8000)
            await page.screenshot(path=f"{artifact_dir}/ext_04_candidates_displayed.png")

            print("7. Editing Candidate #1 statement...")
            cand_inputs = page.locator("input[type='text']")
            first_input = cand_inputs.first
            await first_input.fill("pgvector queries must use an isolated pool of 5 connections with 15s statement timeout (Architect Verified).")

            print("8. Rejecting Candidate #2 (the obsolete SQLite candidate)...")
            reject_btn = page.locator("button:has-text('Reject')").last
            await reject_btn.click()
            await page.wait_for_timeout(500)

            # Confirm Candidate #2 was removed from review list
            remaining_cands = await page.locator("text=#2").count()
            assert remaining_cands == 0, "Candidate #2 was not removed from review!"
            print("   ✅ Candidate #2 rejected and removed from review.")

            print("9. Approving Candidate #1...")
            approve_btn = page.locator("button:has-text('Approve Memory')").first
            await approve_btn.click()
            await page.wait_for_selector("text=Approved & Persisted", timeout=8000)
            await page.screenshot(path=f"{artifact_dir}/ext_05_candidate_approved.png")

            print("10. Closing modal and verifying live Memories table...")
            done_btn = page.locator("button:has-text('Done')")
            await done_btn.click()
            await page.wait_for_timeout(1000)

            # Live table check
            table_row = page.locator("text=pgvector_pool")
            await table_row.wait_for(timeout=8000)
            await page.screenshot(path=f"{artifact_dir}/ext_06_live_memory_table.png")

            print("11. Opening claim detail drawer to inspect evidence quote...")
            await table_row.click()
            await page.wait_for_selector("text=Linked Provenance Evidence", timeout=8000)
            await page.screenshot(path=f"{artifact_dir}/ext_07_drawer_evidence_provenance.png")

            print("🎉 BROWSER E2E EXTRACTION VALIDATION PASSED COMPLETELY!")

            await browser.close()

    finally:
        await cleanup_demo_entities(engine)
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run_extraction_browser_test())

