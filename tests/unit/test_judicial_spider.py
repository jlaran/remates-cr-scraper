"""Unit test: judicial spider orchestration with mocked HTTP and DB."""
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from remates_scraper.spiders.judicial import spider as spider_mod

FIX = Path(__file__).parent.parent / "fixtures" / "judicial"


def fake_pdf() -> bytes:
    return (FIX / "sample_boletin.pdf").read_bytes()


def test_download_latest_tries_recent_dates(monkeypatch: object) -> None:
    """Verify the spider walks back through dates until one returns a PDF."""
    pdf_bytes = fake_pdf()

    today = date.today()
    expected_date = today - timedelta(days=2)  # simulate 2 days back has the PDF
    expected_url_marker = expected_date.strftime("%d_%m_%Y")

    class FakeResponse:
        def __init__(self, status: int, ctype: str, content: bytes = b"") -> None:
            self.status_code = status
            self.headers: dict[str, str] = {"content-type": ctype}
            self.content = content

    class FakeClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def __enter__(self) -> "FakeClient":
            return self

        def __exit__(self, *a: object) -> bool:
            return False

        def head(self, url: str) -> FakeResponse:
            if expected_url_marker in url:
                return FakeResponse(200, "application/pdf")
            return FakeResponse(404, "text/html")

        def get(self, url: str) -> FakeResponse:
            if expected_url_marker in url:
                return FakeResponse(200, "application/pdf", pdf_bytes)
            return FakeResponse(404, "text/html")

    with patch("remates_scraper.spiders.judicial.spider.httpx.Client", FakeClient):
        url, content = spider_mod._download_latest_boletin()

    assert url is not None
    assert expected_url_marker in url
    assert content == pdf_bytes


def test_download_returns_none_when_no_pdf_found() -> None:
    """Verify the spider returns None after MAX_DAYS_BACK with no successful download."""

    class AlwaysFails:
        def __init__(self, *a: object, **kw: object) -> None:
            pass

        def __enter__(self) -> "AlwaysFails":
            return self

        def __exit__(self, *a: object) -> bool:
            return False

        def head(self, url: str) -> object:  # noqa: ARG002
            class R:
                status_code = 404
                headers: dict[str, str] = {"content-type": "text/html"}

            return R()

        def get(self, url: str) -> object:  # noqa: ARG002
            class R:
                status_code = 404
                headers: dict[str, str] = {}
                content = b""

            return R()

    with patch("remates_scraper.spiders.judicial.spider.httpx.Client", AlwaysFails):
        url, content = spider_mod._download_latest_boletin()

    assert url is None
    assert content == b""
