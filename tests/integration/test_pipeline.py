import pytest

from remates_scraper.common.pipeline import ScrapeRunContext, upsert_raw_listing

LOCAL_DSN = "postgresql://postgres:test@localhost:5499/remates_test"


@pytest.fixture(autouse=True)
def _set_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", LOCAL_DSN)


def test_upsert_inserts_when_new():
    with ScrapeRunContext("bcr") as run:
        rid = upsert_raw_listing(
            run_id=run.id,
            source_id="bcr",
            external_id="test-1",
            source_url="https://example.com/1",
            payload={"title": "casa"},
        )
        assert rid is not None


def test_upsert_is_idempotent_with_same_content():
    with ScrapeRunContext("bcr") as run:
        rid1 = upsert_raw_listing(run.id, "bcr", "test-2", "https://e/2", {"k": "v"})
        rid2 = upsert_raw_listing(run.id, "bcr", "test-2", "https://e/2", {"k": "v"})
        assert rid1 == rid2  # same content_hash → no insert


def test_upsert_inserts_when_content_changes():
    with ScrapeRunContext("bcr") as run:
        rid1 = upsert_raw_listing(run.id, "bcr", "test-3", "https://e/3", {"k": "v1"})
        rid2 = upsert_raw_listing(run.id, "bcr", "test-3", "https://e/3", {"k": "v2"})
        assert rid1 != rid2  # different content → new row
