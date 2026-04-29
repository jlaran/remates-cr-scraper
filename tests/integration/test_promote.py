import uuid

import pytest

from remates_scraper.common.db import connect
from remates_scraper.common.pipeline import ScrapeRunContext, upsert_raw_listing
from remates_scraper.jobs.promote import run as run_promote


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://postgres:test@localhost:5499/remates_test")


def _uid() -> str:
    return uuid.uuid4().hex[:8]


def _valid_auction_payload(suffix: str) -> dict:
    return {
        "title": f"Casa de prueba {suffix}",
        "description": "Bonita casa de prueba",
        "property_type": "casa",
        "province": "San José",
        "canton": "Escazú",
        "base_price": 50_000_000,
        "currency": "CRC",
        "image_urls": [],
        "source_url": f"https://example.com/{suffix}",
        "for_sale_kind": "auction",
        "auctions": [{
            "round": 1,
            "scheduled_at": "2026-06-15T10:00:00",
            "base_price": 50_000_000,
            "currency": "CRC",
        }],
        "meta": {"expediente": f"22-{suffix}-CI"},
    }


def _valid_direct_sale_payload(suffix: str) -> dict:
    return {
        "title": f"Casa adjudicada {suffix}",
        "property_type": "casa",
        "province": "Alajuela",
        "base_price": 60_000_000,
        "currency": "CRC",
        "source_url": f"https://example.com/d{suffix}",
        "for_sale_kind": "direct_sale",
        "auctions": [],
        "image_urls": [],
        "meta": {},
    }


def test_promote_auction_payload_creates_listing():
    ext_id = f"auction-{_uid()}"
    with ScrapeRunContext("bcr") as run:
        upsert_raw_listing(
            run.id, "bcr", ext_id, f"https://e/{ext_id}", _valid_auction_payload(ext_id)
        )
    result = run_promote()
    assert result["promoted"] >= 1

    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT slug, status, for_sale_kind FROM listings "
            "WHERE source_id='bcr' AND external_id=%s",
            (ext_id,),
        )
        row = cur.fetchone()
    assert row is not None
    assert row["status"] == "active"
    assert row["for_sale_kind"] == "auction"


def test_promote_direct_sale_without_auctions_succeeds():
    ext_id = f"direct-{_uid()}"
    with ScrapeRunContext("bcr") as run:
        upsert_raw_listing(
            run.id, "bcr", ext_id, f"https://e/d{ext_id}", _valid_direct_sale_payload(ext_id)
        )
    result = run_promote()
    assert result["promoted"] >= 1

    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT for_sale_kind FROM listings WHERE source_id='bcr' AND external_id=%s",
            (ext_id,),
        )
        row = cur.fetchone()
        cur.execute(
            "SELECT count(*) FROM auctions a JOIN listings l ON l.id = a.listing_id "
            "WHERE l.source_id='bcr' AND l.external_id=%s",
            (ext_id,),
        )
        count_row = cur.fetchone()
    assert row is not None
    assert row["for_sale_kind"] == "direct_sale"
    assert count_row is not None
    assert count_row["count"] == 0  # direct_sale has no auctions


def test_promote_auction_kind_without_auctions_marked_invalid():
    ext_id = f"bad-auction-{_uid()}"
    bad = _valid_auction_payload(ext_id)
    bad["auctions"] = []  # break the constraint
    with ScrapeRunContext("bcr") as run:
        upsert_raw_listing(run.id, "bcr", ext_id, f"https://e/{ext_id}", bad)
    result = run_promote()
    assert result["invalidated"] >= 1


def test_promote_invalid_payload_marked_invalid():
    ext_id = f"bad-payload-{_uid()}"
    bad = {"title": "x"}  # missing required fields
    with ScrapeRunContext("bcr") as run:
        upsert_raw_listing(run.id, "bcr", ext_id, f"https://e/{ext_id}", bad)
    result = run_promote()
    assert result["invalidated"] >= 1
