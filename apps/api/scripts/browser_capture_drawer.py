import asyncio
from playwright.async_api import async_playwright

ARTIFACT_DIR = "/Users/shash/.gemini/antigravity/brain/1e4e0e5c-f509-4e8f-8298-53e18857c330"

async def capture_drawer():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await context.new_page()

        await page.goto("http://localhost:5173/memory", wait_until="networkidle")
        await page.wait_for_timeout(1000)

        # Inspect button on the first memory row
        row = page.locator("tr:has-text('Inspect')").first
        if await row.count() > 0:
            btn = row.locator("button:has-text('Inspect')")
            await btn.click()
            await page.wait_for_timeout(1000)
            await page.screenshot(path=f"{ARTIFACT_DIR}/redesign_06_claim_drawer.png")
            print("✓ Captured redesign_06_claim_drawer.png")

        await browser.close()

asyncio.run(capture_drawer())
