"""BCR spider — uses Playwright to navigate JS-heavy bot-protected portal."""
from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from typing import Any

from playwright.async_api import BrowserContext, Page, async_playwright

from remates_scraper.common.pipeline import ScrapeRunContext, upsert_raw_listing
from remates_scraper.spiders.bcr.parser import (
    normalize_listings_item,
    parse_detail_page,
    parse_listings_page,
)

# Property types to iterate. BCR site exposes at least Casas (1), Apartamentos (2), Lotes (3).
# Confirmed via fixture inspection and site structure; extend if new types appear.
PROPERTY_TYPES = [1, 2, 3]
SECTION_BY_TYPE = {1: "Casas", 2: "Apartamentos", 3: "Lotes"}
LISTINGS_URL_TEMPLATE = (
    "https://ventadebienes.bancobcr.com/wps/portal/bcrb/bcrbienes/bienes/{section}"
    "?&tipo_propiedad={tipo}"
)

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
DETAIL_TIMEOUT_MS = 60_000
NAV_BUFFER_MS = 3_000
# Safety cap: 8 items/page × 20 pages = 160 max per type.
MAX_PAGES_PER_TYPE = 20
# Sleep between page navigations to avoid triggering Radware bot manager.
PAGE_SLEEP_S = 1.5

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
                for tipo in PROPERTY_TYPES:
                    section = SECTION_BY_TYPE[tipo]
                    listings_url = LISTINGS_URL_TEMPLATE.format(section=section, tipo=tipo)
                    log.info("scraping BCR tipo_propiedad=%d (%s)", tipo, section)
                    await _scrape_type(ctx, listings_url, run_ctx)

                return {
                    "found": run_ctx.items_found,
                    "new": run_ctx.items_new,
                    "failed": run_ctx.items_failed,
                }
        finally:
            await browser.close()


async def _scrape_type(
    ctx: BrowserContext,
    listings_url: str,
    run_ctx: ScrapeRunContext,
) -> None:
    """Iterate all pagination pages for a single property type."""
    page = await ctx.new_page()
    try:
        # Navigate to the first page
        await page.goto(listings_url, wait_until="domcontentloaded", timeout=DETAIL_TIMEOUT_MS)
        with contextlib.suppress(Exception):
            await page.wait_for_load_state("networkidle", timeout=30_000)
        await page.wait_for_timeout(NAV_BUFFER_MS)

        seen_external_ids: set[str] = set()

        for page_num in range(1, MAX_PAGES_PER_TYPE + 1):
            html = await page.content()
            items = parse_listings_page(html)
            log.info("page %d: found %d raw items", page_num, len(items))

            new_items = [it for it in items if it["external_id"] not in seen_external_ids]
            if not new_items:
                log.info("no new items on page %d — stopping pagination", page_num)
                break

            for item in new_items:
                seen_external_ids.add(item["external_id"])
                run_ctx.items_found += 1
                try:
                    await _process_item(ctx, item, run_ctx)
                except Exception:
                    log.exception("failed item %s", item.get("external_id"))
                    run_ctx.items_failed += 1

            # Attempt to click "Siguiente" to advance to the next page.
            # The BCR portal uses a client-side JS pager (imtech_pager.js) that
            # renders items already on the page without server round-trips for
            # same-page navigation, but also supports AJAX-loaded next pages via
            # paginacionURL. Clicking the link is the most reliable approach.
            advanced = await _try_next_page(page)
            if not advanced:
                log.info("no 'Siguiente' button available — end of pagination")
                break

            time.sleep(PAGE_SLEEP_S)

    finally:
        await page.close()


async def _try_next_page(page: Page) -> bool:
    """Click the 'Siguiente' pagination button if it exists and is not disabled.

    Returns True if the click was performed (page may now have new content),
    False if we're on the last page or no pager is present.
    """
    # Selectors matching the BCR pager structure:
    # <li class="page-item next"><a title="Siguiente" href="#" class="page-link">…</a></li>
    next_li = page.locator("li.page-item.next")
    count = await next_li.count()
    if count == 0:
        return False

    # Check whether the li has the "disabled" class (last page)
    is_disabled = await next_li.evaluate(
        "(el) => el.classList.contains('disabled')"
    )
    if is_disabled:
        return False

    next_link = next_li.locator("a.page-link")
    await next_link.click()
    with contextlib.suppress(Exception):
        await page.wait_for_load_state("networkidle", timeout=30_000)
    await page.wait_for_timeout(NAV_BUFFER_MS)
    return True


async def _process_item(
    ctx: BrowserContext,
    item: dict[str, Any],
    run_ctx: ScrapeRunContext,
) -> None:
    """Fetch detail page, merge, validate and upsert a single listing."""
    # Start with listings-page data as the base payload (includes image_url)
    payload = normalize_listings_item(item)

    # Attempt to enrich with detail page — non-blocking
    try:
        detail_html = await _fetch(ctx, item["detail_url"])
        detail = parse_detail_page(detail_html, source_url=item["detail_url"])
        # Merge: prefer non-empty values from the detail page
        if detail.get("title"):
            payload["title"] = detail["title"]
        if detail.get("base_price", 0.0) > 0:
            payload["base_price"] = detail["base_price"]
            payload["currency"] = detail["currency"]
        if detail.get("province"):
            payload["province"] = detail["province"]
        if detail.get("canton"):
            payload["canton"] = detail["canton"]
        if detail.get("description"):
            payload["description"] = detail["description"]
        if detail.get("property_type") and detail["property_type"] != "otro":
            payload["property_type"] = detail["property_type"]
        # Always take meta from detail (richer)
        payload["meta"] = detail["meta"]
        # Merge image_urls: listings card image first, then detail-page images (deduplicated)
        if detail.get("image_urls"):
            existing = set(payload["image_urls"])
            extra = [u for u in detail["image_urls"] if u not in existing]
            payload["image_urls"] = payload["image_urls"] + extra
    except Exception:
        log.warning(
            "detail page failed for %s — using listings-page data only",
            item.get("external_id"),
        )

    # Skip if still missing mandatory fields after merge
    if not payload.get("title") or payload.get("base_price", 0.0) <= 0:
        log.warning(
            "skipping %s: title=%r base_price=%s",
            item.get("external_id"),
            payload.get("title"),
            payload.get("base_price"),
        )
        run_ctx.items_failed += 1
        return

    upsert_raw_listing(
        run_id=run_ctx.id,
        source_id="bcr",
        external_id=item["external_id"],
        source_url=item["detail_url"],
        payload=payload,
    )
    run_ctx.items_new += 1


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
