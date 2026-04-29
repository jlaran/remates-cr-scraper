"""
Direct capture of detail page with stealth - no prior navigation.
"""
import asyncio
import sys
from pathlib import Path

from playwright.async_api import async_playwright
from playwright_stealth import Stealth

DETAIL_URL = "https://ventadebienes.bancobcr.com/wps/portal/bcrb/bcrbienes/bienes/Casas/detalle/?codigo=2-417772-000&tipo_propiedad=1&descuento=1"
OUT = Path("tests/fixtures/bcr")
OUT.mkdir(parents=True, exist_ok=True)


async def main() -> int:
    async with Stealth().use_async(async_playwright()) as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ]
        )
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
            locale="es-CR",
            timezone_id="America/Costa_Rica",
            extra_http_headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "es-CR,es;q=0.9,en;q=0.8",
                "Referer": "https://ventadebienes.bancobcr.com/wps/portal/bcrb/bcrbienes/bienes/Casas",
            }
        )
        page = await ctx.new_page()

        print(f"Navigating to detail: {DETAIL_URL}", file=sys.stderr)
        await page.goto(DETAIL_URL, wait_until="domcontentloaded", timeout=60_000)
        try:
            await page.wait_for_load_state("networkidle", timeout=25_000)
        except Exception as e:
            print(f"  networkidle timeout: {e}", file=sys.stderr)
        await page.wait_for_timeout(5000)

        detail_html = await page.content()
        detail_size = len(detail_html)
        title = await page.title()
        print(f"  title: {title}, size: {detail_size} bytes", file=sys.stderr)

        is_blocked = 'Radware Bot Manager' in detail_html or 'eres un bot' in detail_html
        if is_blocked:
            print("  BLOCKED", file=sys.stderr)
            await browser.close()
            return 1

        (OUT / "sample_detail.html").write_text(detail_html, encoding="utf-8")
        print(f"saved sample_detail.html ({detail_size} bytes)", file=sys.stderr)
        await browser.close()
        return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
