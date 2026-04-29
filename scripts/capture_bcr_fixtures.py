import asyncio
import sys
from pathlib import Path

from playwright.async_api import async_playwright
from playwright_stealth import Stealth

LISTINGS = "https://ventadebienes.bancobcr.com/wps/portal/bcrb/bcrbienes/bienes/Casas?&tipo_propiedad=1"
OUT = Path("tests/fixtures/bcr")
OUT.mkdir(parents=True, exist_ok=True)


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

        print(f"Navigating to {LISTINGS}", file=sys.stderr)
        await page.goto(LISTINGS, wait_until="domcontentloaded", timeout=60_000)

        try:
            await page.wait_for_load_state("networkidle", timeout=30_000)
        except Exception as e:
            print(f"network not idle within 30s ({e}); proceeding anyway", file=sys.stderr)

        await page.wait_for_timeout(5000)

        listings_html = await page.content()
        listings_size = len(listings_html)
        print(f"listings HTML size: {listings_size} bytes", file=sys.stderr)
        print(f"Page title: {await page.title()}", file=sys.stderr)

        is_blocked = 'Radware Bot Manager' in listings_html or 'eres un bot' in listings_html
        if is_blocked:
            print("WARNING: Got bot block page for listings!", file=sys.stderr)
            await browser.close()
            return 1

        (OUT / "listings_page.html").write_text(listings_html, encoding="utf-8")
        print(f"saved listings_page.html ({listings_size} bytes)", file=sys.stderr)

        # Find detail candidates - prefer 'detalle' URLs
        candidates = await page.evaluate(
            """() => {
                const anchors = Array.from(document.querySelectorAll('a'));
                const matches = anchors
                    .map(a => a.href || '')
                    .filter(h =>
                        h && (h.includes('detalle') || h.includes('propiedad') ||
                              h.includes('bien') || /\\?.+id=/.test(h))
                        && !h.startsWith('javascript:')
                    );
                return matches.slice(0, 10);
            }"""
        )
        print(f"detail candidates: {candidates}", file=sys.stderr)

        preferred = [h for h in candidates if 'detalle' in h]
        detail_url = preferred[0] if preferred else (candidates[0] if candidates else None)

        if not detail_url:
            print("ERROR: no detail link found", file=sys.stderr)
            return 1

        # Navigate to detail IN THE SAME PAGE (same session/cookies)
        print(f"navigating to detail: {detail_url}", file=sys.stderr)
        await page.goto(detail_url, wait_until="domcontentloaded", timeout=60_000)
        try:
            await page.wait_for_load_state("networkidle", timeout=30_000)
        except Exception as e:
            print(f"network not idle on detail ({e}); proceeding anyway", file=sys.stderr)
        await page.wait_for_timeout(5000)

        detail_html = await page.content()
        detail_size = len(detail_html)
        print(f"detail HTML size: {detail_size} bytes", file=sys.stderr)
        print(f"Detail page title: {await page.title()}", file=sys.stderr)

        is_detail_blocked = 'Radware Bot Manager' in detail_html or 'eres un bot' in detail_html
        if is_detail_blocked:
            print("WARNING: detail page is also bot-blocked!", file=sys.stderr)

        (OUT / "sample_detail.html").write_text(detail_html, encoding="utf-8")
        print(f"saved sample_detail.html ({detail_size} bytes)", file=sys.stderr)

        await browser.close()
        return 1 if is_detail_blocked else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
