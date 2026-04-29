"""BCR spider — uses Playwright to navigate JS-heavy bot-protected portal."""
from __future__ import annotations

import asyncio
import contextlib
import logging

from playwright.async_api import BrowserContext, async_playwright

from remates_scraper.common.pipeline import ScrapeRunContext, upsert_raw_listing
from remates_scraper.spiders.bcr.parser import parse_detail_page, parse_listings_page

LISTINGS_URL = (
    "https://ventadebienes.bancobcr.com/wps/portal/bcrb/bcrbienes/bienes/Casas?&tipo_propiedad=1"
)
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
DETAIL_TIMEOUT_MS = 60_000
NAV_BUFFER_MS = 3000

log = logging.getLogger(__name__)


def run() -> dict[str, int]:
    """Synchronous entry point. Returns {found, new, failed}."""
    return asyncio.run(_run_async())


async def _run_async() -> dict[str, int]:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(user_agent=USER_AGENT)
        try:
            with ScrapeRunContext("bcr") as run_ctx:
                listings_html = await _fetch(ctx, LISTINGS_URL)
                items = parse_listings_page(listings_html)
                log.info("found %d listings on BCR page", len(items))

                for item in items:
                    run_ctx.items_found += 1
                    try:
                        detail_html = await _fetch(ctx, item["detail_url"])
                        detail = parse_detail_page(detail_html, source_url=item["detail_url"])
                        upsert_raw_listing(
                            run_id=run_ctx.id,
                            source_id="bcr",
                            external_id=item["external_id"],
                            source_url=item["detail_url"],
                            payload=detail,
                        )
                        run_ctx.items_new += 1
                    except Exception:
                        log.exception("failed item %s", item.get("external_id"))
                        run_ctx.items_failed += 1
                return {
                    "found": run_ctx.items_found,
                    "new": run_ctx.items_new,
                    "failed": run_ctx.items_failed,
                }
        finally:
            await browser.close()


async def _fetch(ctx: BrowserContext, url: str) -> str:
    page = await ctx.new_page()
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=DETAIL_TIMEOUT_MS)
        with contextlib.suppress(Exception):
            await page.wait_for_load_state("networkidle", timeout=30_000)
        await page.wait_for_timeout(NAV_BUFFER_MS)
        return await page.content()
    finally:
        await page.close()
