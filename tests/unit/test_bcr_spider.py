"""Unit test: spider orchestration with mocked fetches."""
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from remates_scraper.spiders.bcr.spider import _run_async

FIX = Path(__file__).parent.parent / "fixtures" / "bcr"


@pytest.mark.asyncio
async def test_run_async_orchestrates_listings_and_details(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://postgres:test@localhost:5499/remates_test",
    )
    listings_html = (FIX / "listings_page.html").read_text(encoding="utf-8")
    detail_html = (FIX / "sample_detail.html").read_text(encoding="utf-8")

    async def fake_fetch(ctx: object, url: str) -> str:  # noqa: ARG001
        return detail_html

    # Mock the listings page Playwright page used in _scrape_type
    mock_listings_page = AsyncMock()
    mock_listings_page.content = AsyncMock(return_value=listings_html)
    mock_listings_page.goto = AsyncMock()
    mock_listings_page.wait_for_load_state = AsyncMock()
    mock_listings_page.wait_for_timeout = AsyncMock()
    mock_listings_page.close = AsyncMock()

    # next-page button: simulate disabled so pagination stops after page 1
    mock_next_li = AsyncMock()
    mock_next_li.count = AsyncMock(return_value=1)
    mock_next_li.evaluate = AsyncMock(return_value=True)  # disabled=True → stop
    mock_listings_page.locator = MagicMock(return_value=mock_next_li)

    mock_context = AsyncMock()
    # First call to new_page() returns the listings page mock; subsequent calls
    # are for _fetch (detail pages) and return a basic AsyncMock.
    call_count = {"n": 0}

    async def new_page_side_effect() -> AsyncMock:
        if call_count["n"] == 0:
            call_count["n"] += 1
            return mock_listings_page
        call_count["n"] += 1
        detail_page = AsyncMock()
        detail_page.goto = AsyncMock()
        detail_page.wait_for_load_state = AsyncMock()
        detail_page.wait_for_timeout = AsyncMock()
        detail_page.content = AsyncMock(return_value=detail_html)
        detail_page.close = AsyncMock()
        return detail_page

    mock_context.new_page = new_page_side_effect

    mock_browser = AsyncMock()
    mock_browser.close = AsyncMock()
    mock_browser.new_context = AsyncMock(return_value=mock_context)

    mock_pw_instance = AsyncMock()
    mock_pw_instance.chromium.launch = AsyncMock(return_value=mock_browser)

    mock_pw_cm = AsyncMock()
    mock_pw_cm.__aenter__ = AsyncMock(return_value=mock_pw_instance)
    mock_pw_cm.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("remates_scraper.spiders.bcr.spider.async_playwright", return_value=mock_pw_cm),
        patch("remates_scraper.spiders.bcr.spider._fetch", new=AsyncMock(side_effect=fake_fetch)),
        patch("remates_scraper.spiders.bcr.spider.time") as mock_time,
    ):
        mock_time.sleep = MagicMock()
        result = await _run_async()

    assert result["found"] >= 1
    assert result["found"] == result["new"] + result["failed"]
