import asyncio
import os
import sys
from playwright.async_api import async_playwright

ARTIFACT_DIR = "/Users/shash/.gemini/antigravity/brain/1e4e0e5c-f509-4e8f-8298-53e18857c330"

async def capture_screens():
    os.makedirs(ARTIFACT_DIR, exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await context.new_page()

        # 1. Landing Welcome Page
        print("Navigating to Welcome Page...")
        await page.goto("http://localhost:5173/welcome", wait_until="networkidle")
        await page.wait_for_timeout(1000)
        await page.screenshot(path=f"{ARTIFACT_DIR}/redesign_01_welcome.png")
        print("✓ Captured redesign_01_welcome.png")

        # 2. Overview Dashboard
        print("Navigating to Overview Page...")
        await page.goto("http://localhost:5173/", wait_until="networkidle")
        await page.wait_for_timeout(1000)
        await page.screenshot(path=f"{ARTIFACT_DIR}/redesign_02_overview.png")
        print("✓ Captured redesign_02_overview.png")

        # 3. Memories Page
        print("Navigating to Memories Page...")
        await page.goto("http://localhost:5173/memory", wait_until="networkidle")
        await page.wait_for_timeout(1000)
        await page.screenshot(path=f"{ARTIFACT_DIR}/redesign_03_memories.png")
        print("✓ Captured redesign_03_memories.png")

        # 4. Open Extraction Modal
        print("Opening Extraction Modal...")
        extract_btn = page.locator("button:has-text('Extract with Muse Spark')")
        if await extract_btn.count() > 0:
            await extract_btn.first.click()
            await page.wait_for_timeout(600)
            await page.screenshot(path=f"{ARTIFACT_DIR}/redesign_04_modal_transcript.png")
            print("✓ Captured redesign_04_modal_transcript.png")

            # Paste transcript and calculate estimation
            textarea = page.locator("textarea")
            if await textarea.count() > 0:
                await textarea.fill("Turn 1 (Lead Systems Architect):\nWe concluded our evaluation of PostgreSQL connection pooling. We decided that pgvector queries must run with an isolated pool of 5 connections and statement timeouts capped at 15 seconds.")
                est_btn = page.locator("button:has-text('Calculate Tokens & Cost Preview')")
                if await est_btn.count() > 0:
                    await est_btn.click()
                    await page.wait_for_timeout(1500)
                    await page.screenshot(path=f"{ARTIFACT_DIR}/redesign_05_modal_estimation.png")
                    print("✓ Captured redesign_05_modal_estimation.png")

            close_btn = page.locator("button:has(svg.lucide-x)")
            if await close_btn.count() > 0:
                await close_btn.click()
                await page.wait_for_timeout(500)

        # 5. Open Memory Inspection Drawer
        print("Opening Memory Inspection Drawer...")
        inspect_btn = page.locator("button:has-text('Inspect')")
        if await inspect_btn.count() > 0:
            await inspect_btn.first.click()
            await page.wait_for_timeout(1000)
            await page.screenshot(path=f"{ARTIFACT_DIR}/redesign_06_claim_drawer.png")
            print("✓ Captured redesign_06_claim_drawer.png")

        # 6. Supporting Evidence Page
        print("Navigating to Evidence Page...")
        await page.goto("http://localhost:5173/evidence", wait_until="networkidle")
        await page.wait_for_timeout(1000)
        await page.screenshot(path=f"{ARTIFACT_DIR}/redesign_07_evidence.png")
        print("✓ Captured redesign_07_evidence.png")

        # 7. Memory Connections (Dependencies) Page
        print("Navigating to Dependencies Page...")
        await page.goto("http://localhost:5173/dependencies", wait_until="networkidle")
        await page.wait_for_timeout(1000)
        await page.screenshot(path=f"{ARTIFACT_DIR}/redesign_08_connections.png")
        print("✓ Captured redesign_08_connections.png")

        await browser.close()
        print("All visual smoke tests and screenshots captured successfully!")

asyncio.run(capture_screens())
