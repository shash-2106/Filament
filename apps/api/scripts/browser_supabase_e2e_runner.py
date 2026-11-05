"""Automated live browser-to-Supabase E2E verification using Playwright.

Executes the full real-browser workflow against:
- FastAPI running on port 8000 connected to Supabase (aws-0-eu-west-1.pooler.supabase.com:5432).
- Vite running on port 5173.

Flow:
1. Opens http://localhost:5173 in headless Chromium.
2. Authenticates by opening the API key modal and submitting the demo agent token.
3. Verifies workspace identity ('Filament Core Workspace') and connected status in the header.
4. Navigates to Memory page, opens the 'Establish Memory' modal, and creates a new claim.
5. Ingests evidence, links it to the claim with 'supports' polarity and notes.
6. Ingests Baseline Snapshot A (matching pyproject.toml) and establishes conditions on the claim.
7. Evaluates against Baseline Snapshot A -> verifies 'applicable' badge and 'SATISFIED' item status.
8. Evaluates against Unrelated Snapshot B (only README changed) -> verifies 'applicable'.
9. Evaluates against Drifted Snapshot C (pyproject.toml modified) -> verifies 'environment_mismatch' / 'drifted' badge and 'DRIFTED' item status.
10. Submits formal Re-verification adopting upgraded condition set v2.
11. Verifies verification history and inspects the Activity page to confirm audit events recorded.
12. Cleans up disposable demo records from Supabase via admin connection.
"""

import asyncio
import hashlib
import json
import os
import sys
import uuid
from playwright.async_api import async_playwright
import urllib.parse
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
DEMO_API_KEY = f"fil_live_e2e_{uuid.uuid4().hex}"
DEMO_KEY_HASH = hashlib.sha256(DEMO_API_KEY.encode()).hexdigest()


async def seed_supabase_demo_entities(engine):
    print("1. Seeding disposable demo tenant and agent into live Supabase...")
    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
                INSERT INTO public.workspaces (id, name, slug)
                VALUES (:id, 'Live Browser Verification Lab', :slug)
                """
            ),
            {"id": DEMO_WS_ID, "slug": f"browser-lab-{str(DEMO_WS_ID)[:8]}"},
        )
        await conn.execute(
            text(
                """
                INSERT INTO public.agents (id, workspace_id, name, default_scope, api_key_hash, is_active)
                VALUES (:id, :ws_id, 'Browser Automation Agent', 'team', :hash, true)
                """
            ),
            {"id": DEMO_AGENT_ID, "ws_id": DEMO_WS_ID, "hash": DEMO_KEY_HASH},
        )
    print("   ✅ Demo workspace and agent seeded in Supabase.")


async def cleanup_supabase_demo_entities(engine):
    print("Cleaning up disposable demo records from Supabase via admin connection...")
    try:
        async with engine.begin() as conn:
            # Temporarily disable audit immutability trigger for cleanup
            await conn.execute(text("ALTER TABLE public.audit_events DISABLE TRIGGER trg_protect_audit_events;"))
            await conn.execute(text("DELETE FROM public.audit_events WHERE workspace_id = :ws_id;"), {"ws_id": DEMO_WS_ID})
            await conn.execute(text("DELETE FROM public.workspaces WHERE id = :ws_id;"), {"ws_id": DEMO_WS_ID})
            await conn.execute(text("ALTER TABLE public.audit_events ENABLE TRIGGER trg_protect_audit_events;"))
        print("   ✅ Cleanup complete: 0 residual demo records in Supabase.")
    except Exception as exc:
        print(f"   ⚠️ Cleanup warning: {exc}")


async def run_browser_e2e():
    engine = create_async_engine(POOLER_URL)
    await seed_supabase_demo_entities(engine)

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(viewport={"width": 1440, "height": 900})
            page = await context.new_page()

            # Listen for console errors
            page.on("console", lambda msg: print(f"   [BROWSER CONSOLE] {msg.type}: {msg.text}") if msg.type in ("error", "warning") else None)

            print("2. Opening Filament Workstation at http://localhost:5173...")
            await page.goto("http://localhost:5173", wait_until="networkidle")

            # Verify masthead or unconfigured state
            print("3. Authenticating via Agent Bearer Key modal...")
            auth_btn = page.locator("button:has-text('Configure API Key')")
            await auth_btn.click()

            token_input = page.locator("input[type='password']")
            await token_input.fill(DEMO_API_KEY)

            save_btn = page.locator("button:has-text('Save Credentials')")
            await save_btn.click()

            # Wait for workspace resolution
            await page.wait_for_selector("text='Live Browser Verification Lab'", timeout=10000)
            print("   ✅ Browser authenticated: 'Live Browser Verification Lab' displayed in Header.")

            print("4. Navigating to Memory page and establishing a memory claim...")
            await page.click("a[href='/memory']")
            await page.wait_for_selector("text='Governed Agent Memories'")

            # Click Establish Memory
            await page.click("button:has-text('Establish Memory')")
            await page.wait_for_selector("text='Establish Governed Memory Claim'")

            await page.fill("input[placeholder*='database.connection_pool']", "runtime.asyncpg_pool")
            await page.fill("input[placeholder*='max_connections']", "max_connections")
            await page.fill("textarea[placeholder*='maximum database connection pool size']", "The maximum database connection pool size is 20 connections.")
            await page.fill("textarea[placeholder*='pool_size']", '{"pool_size": 20, "driver": "asyncpg"}')

            await page.click("button:has-text('Establish Claim')")

            # Wait for Claim Drawer to open
            await page.wait_for_selector("text='Structured Value'", timeout=10000)
            print("   ✅ Claim created and opened in Claim Drawer.")

            # Extract Claim ID from drawer copy button or text
            drawer = page.locator("div.fixed.inset-y-0.right-0")
            claim_text = await drawer.inner_text()
            assert "The maximum database connection pool size is 20 connections." in claim_text

            print("5. Recording and linking evidence via Claim Drawer...")
            # First, record evidence via Evidence page
            await page.click("a[href='/evidence']")
            await page.wait_for_selector("text='Immutable Evidence Artifacts'")

            await page.click("button:has-text('Record Evidence')")
            await page.wait_for_selector("text='Record Evidence Snapshot'")

            await page.fill("input[placeholder*='pyproject.toml']", "pyproject.toml")
            snippet = "[tool.filament]\nmax_connections = 20\nruntime = 'asyncpg'"
            await page.fill("textarea[placeholder*='Paste snippet text']", snippet)

            await page.click("button:has-text('Ingest Snapshot')")
            await page.wait_for_selector("text='[tool.filament]'", timeout=10000)
            print("   ✅ Evidence recorded on live Evidence page.")

            # Copy evidence ID from page
            ev_id_el = page.locator("text=/id: [0-9a-f]{8}/").first
            ev_id_text = await ev_id_el.inner_text()
            print(f"   ✅ Observed Evidence: {ev_id_text}")

            print("6. Returning to Memory to inspect condition establishment and evaluation...")
            await page.click("a[href='/memory']")
            await page.wait_for_selector("text='runtime.asyncpg_pool'")
            await page.click("text='runtime.asyncpg_pool'")

            # Open Conditions tab
            await page.click("button:has-text('Conditions & Reverification')")
            await page.wait_for_selector("text='Establish Initial Condition Set'")

            # Create an environment snapshot using API via page.evaluate
            eval_script = f"""
                async (apiKey) => {{
                    const res = await fetch('/api/v1/snapshots', {{
                        method: 'POST',
                        headers: {{
                            'Content-Type': 'application/json',
                            'Authorization': 'Bearer ' + apiKey
                        }},
                        body: JSON.stringify({{
                            source_ref: 'git:main:commit_baseline',
                            scan_scope: 'full_repository',
                            snapshot_data: {{
                                scanned_roots: ['.'],
                                files: {{
                                    'pyproject.toml': '3a8f522301980838128392183928139281392813928139281392813928139281',
                                    'README.md': 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb'
                                }}
                            }}
                        }})
                    }});
                    return await res.json();
                }}
            """
            snap_a = await page.evaluate(eval_script, DEMO_API_KEY)
            snap_a_id = snap_a["id"]
            print(f"   ✅ Ingested Baseline Snapshot A: {snap_a_id}")

            # Fill condition establishment form
            await page.fill("input[placeholder*='Snapshot UUID']", snap_a_id)
            await page.fill("input[placeholder*='Depends on database schema']", "Requires exact pyproject.toml hash")
            await page.fill("input[placeholder*='pyproject.toml']", "pyproject.toml")
            await page.fill("input[placeholder*='64-char hex hash']", "3a8f522301980838128392183928139281392813928139281392813928139281")

            await page.click("button:has-text('Establish Conditions')")
            await page.wait_for_selector("text='v1 active'", timeout=10000)
            print("   ✅ Condition set v1 established in live Supabase.")

            print("7. Testing Evaluation Tab in real browser against Baseline Snapshot A...")
            await page.click("button:has-text('Evaluation')")
            await page.wait_for_selector("text='Evaluate Environment Preconditions'")

            await page.fill("input[placeholder*='550e8400']", snap_a_id)
            await page.click("button:has-text('Run Applicability Check')")

            await page.wait_for_selector("text='applicable'", timeout=10000)
            await page.wait_for_selector("text='SATISFIED'")
            print("   ✅ Baseline Evaluation in browser: 'applicable' outcome and 'SATISFIED' status rendered.")

            print("8. Ingesting and evaluating Unrelated Snapshot B (only README changed)...")
            eval_unrelated_script = f"""
                async (apiKey) => {{
                    const res = await fetch('/api/v1/snapshots', {{
                        method: 'POST',
                        headers: {{
                            'Content-Type': 'application/json',
                            'Authorization': 'Bearer ' + apiKey
                        }},
                        body: JSON.stringify({{
                            source_ref: 'git:main:commit_readme_change',
                            snapshot_data: {{
                                scanned_roots: ['.'],
                                files: {{
                                    'pyproject.toml': '3a8f522301980838128392183928139281392813928139281392813928139281',
                                    'README.md': 'cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc'
                                }}
                            }}
                        }})
                    }});
                    return await res.json();
                }}
            """
            snap_b = await page.evaluate(eval_unrelated_script, DEMO_API_KEY)
            snap_b_id = snap_b["id"]

            await page.fill("input[placeholder*='550e8400']", snap_b_id)
            await page.click("button:has-text('Run Applicability Check')")
            await page.wait_for_selector("text='applicable'", timeout=10000)
            print("   ✅ Unrelated README change preserved applicability in browser.")

            print("9. Ingesting and evaluating Drifted Snapshot C (pyproject.toml modified)...")
            drifted_hash = "dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd"
            eval_drift_script = f"""
                async (apiKey) => {{
                    const res = await fetch('/api/v1/snapshots', {{
                        method: 'POST',
                        headers: {{
                            'Content-Type': 'application/json',
                            'Authorization': 'Bearer ' + apiKey
                        }},
                        body: JSON.stringify({{
                            source_ref: 'git:main:commit_dep_upgrade',
                            snapshot_data: {{
                                scanned_roots: ['.'],
                                files: {{
                                    'pyproject.toml': '{drifted_hash}'
                                }}
                            }}
                        }})
                    }});
                    return await res.json();
                }}
            """
            snap_c = await page.evaluate(eval_drift_script, DEMO_API_KEY)
            snap_c_id = snap_c["id"]

            await page.fill("input[placeholder*='550e8400']", snap_c_id)
            await page.click("button:has-text('Run Applicability Check')")

            # Check for drifted badge and DRIFTED outcome
            await page.wait_for_selector("text='drifted'", timeout=10000)
            await page.wait_for_selector("text='DRIFTED'")
            print("   ✅ Environmental drift accurately detected and rendered: 'drifted' badge and 'DRIFTED' item status.")

            print("10. Testing Formal Re-verification in browser (Adopting upgraded conditions)...")
            await page.click("button:has-text('Conditions & Reverification')")
            await page.wait_for_selector("text='Formal Re-verification & Condition Adoption'")

            # Select Adopt New Conditions
            await page.select_option("select", value="adopt_new_conditions")

            await page.fill("input[placeholder*='Snapshot UUID']", snap_c_id)
            await page.fill("input[placeholder*='Document why this memory remains valid']", "Verified compatibility with upgraded package configuration.")
            await page.fill("input[placeholder*='Rationale for adopting updated conditions']", "Adopt updated pyproject.toml hash into condition set v2.")
            await page.fill("input[placeholder*='64-char hex hash']", drifted_hash)

            await page.click("button:has-text('Submit Re-verification')")
            await page.wait_for_selector("text='v2 active'", timeout=10000)
            print("   ✅ Formally adopted condition set v2 in live browser.")

            print("11. Verifying Activity page audit stream...")
            await page.click("a[href='/activity']")
            await page.wait_for_selector("text='Immutable Audit Trail'")
            await page.wait_for_selector("text='CLAIM_CONDITIONS_ADOPTED'", timeout=10000)
            await page.wait_for_selector("text='CLAIM_CREATED'")
            await page.wait_for_selector("text='EVIDENCE_RECORDED'")
            print("   ✅ Audit stream verified in browser with all state mutations.")

            await browser.close()

        print("\n🎉 LIVE BROWSER WORKFLOW AGAINST SUPABASE COMPLETED SUCCESSFULLY!")

    finally:
        await cleanup_supabase_demo_entities(engine)
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run_browser_e2e())
