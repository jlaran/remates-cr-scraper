"""Unit test: spider orchestration with mocked fetches."""
from pathlib import Path
from unittest.mock import AsyncMock, patch

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
        if "Casas" in url:
            return listings_html
        return detail_html

    with patch("remates_scraper.spiders.bcr.spider._fetch", new=AsyncMock(side_effect=fake_fetch)):
        # Patch async_playwright so no real browser launches
        mock_browser = AsyncMock()
        mock_browser.close = AsyncMock()
        mock_context = AsyncMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)

        mock_pw_instance = AsyncMock()
        mock_pw_instance.chromium.launch = AsyncMock(return_value=mock_browser)

        mock_pw_cm = AsyncMock()
        mock_pw_cm.__aenter__ = AsyncMock(return_value=mock_pw_instance)
        mock_pw_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("remates_scraper.spiders.bcr.spider.async_playwright", return_value=mock_pw_cm):
            result = await _run_async()

    assert result["found"] >= 1
    assert result["found"] == result["new"] + result["failed"]
