"""
Capture just the detail page, with human-like delays and stealth.
Run this after a few minutes of IP cooldown.
"""
import asyncio
import sys
from pathlib import Path
import random

from playwright.async_api import async_playwright
from playwright_stealth import Stealth

# Use a different detail URL (second one in case first got flagged)
DETAIL_URL = "https://ventadebienes.bancobcr.com/wps/portal/bcrb/bcrbienes/bienes/Casas/detalle/?codigo=2-451296-000&tipo_propiedad=1&descuento=1"
# Start from homepage first to warm up the session
HOME = "https://ventadebienes.bancobcr.com/wps/portal/bcrb/bcrbienes/inicio"
LISTINGS = "https://ventadebienes.bancobcr.com/wps/portal/bcrb/bcrbienes/bienes/Casas"

OUT = Path("tests/fixtures/bcr")
OUT.mkdir(parents=True, exist_ok=True)


async def human_delay(page, ms_min=1000, ms_max=3000):
    """Simulate human think time."""
    delay = random.randint(ms_min, ms_max)
    await page.wait_for_timeout(delay)


async def main() -> int:
    async with Stealth().use_async(async_playwright()) as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-infobars",
                "--disable-dev-shm-usage",
            ]
        )
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
            locale="es-CR",
            timezone_id="America/Costa_Rica",
        )
        page = await ctx.new_page()

        # Step 1: Visit homepage first
        print(f"Step 1: visiting homepage {HOME}", file=sys.stderr)
        await page.goto(HOME, wait_until="domcontentloaded", timeout=60_000)
        try:
            await page.wait_for_load_state("networkidle", timeout=20_000)
        except Exception:
            pass
        title = await page.title()
        print(f"  title: {title}", file=sys.stderr)
        if 'Radware' in title or 'bot' in title.lower():
            print("  BLOCKED at homepage", file=sys.stderr)
            await browser.close()
            return 1

        await human_delay(page, 2000, 4000)

        # Step 2: Navigate to listings
        print(f"Step 2: visiting listings {LISTINGS}", file=sys.stderr)
        await page.goto(LISTINGS, wait_until="domcontentloaded", timeout=60_000)
        try:
            await page.wait_for_load_state("networkidle", timeout=25_000)
        except Exception:
            pass
        title = await page.title()
        print(f"  title: {title}", file=sys.stderr)
        if 'Radware' in title or 'bot' in title.lower():
            print("  BLOCKED at listings", file=sys.stderr)
            await browser.close()
            return 1
        print(f"  listings size: {len(await page.content())} bytes", file=sys.stderr)

        await human_delay(page, 2000, 5000)

        # Step 3: Navigate to detail
        print(f"Step 3: visiting detail {DETAIL_URL}", file=sys.stderr)
        await page.goto(DETAIL_URL, wait_until="domcontentloaded", timeout=60_000)
        try:
            await page.wait_for_load_state("networkidle", timeout=25_000)
        except Exception:
            pass
        await page.wait_for_timeout(4000)

        detail_html = await page.content()
        detail_size = len(detail_html)
        title = await page.title()
        print(f"  title: {title}, size: {detail_size} bytes", file=sys.stderr)

        is_blocked = 'Radware Bot Manager' in detail_html or 'eres un bot' in detail_html
        if is_blocked:
            print("  BLOCKED at detail page", file=sys.stderr)
            await browser.close()
            return 1

        (OUT / "sample_detail.html").write_text(detail_html, encoding="utf-8")
        print(f"saved sample_detail.html ({detail_size} bytes)", file=sys.stderr)

        await browser.close()
        return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
