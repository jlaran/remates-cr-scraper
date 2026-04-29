"""Promote validated raw_listings → listings (and auctions, listing_images)."""
from __future__ import annotations

import json
import logging
import os
import re
import unicodedata
import uuid
from typing import Any

import httpx
from psycopg.rows import dict_row
from pydantic import ValidationError

from remates_scraper.common.db import connect
from remates_scraper.jobs.schemas import ListingInput

log = logging.getLogger(__name__)


def run(limit: int = 500) -> dict[str, int]:
    promoted = 0
    invalidated = 0
    changed_slugs: list[str] = []

    with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT id, source_id, external_id, source_url, payload
            FROM raw_listings
            WHERE validation_status = 'pending'
            ORDER BY scraped_at ASC
            LIMIT %s
            """,
            (limit,),
        )
        rows = list(cur.fetchall())

    for row in rows:
        try:
            payload: dict[str, Any] = row["payload"]
            payload.setdefault("source_url", row["source_url"])
            data = ListingInput.model_validate(payload)
            slug = _promote_one(row["source_id"], row["external_id"], row["source_url"], data)
            _mark_raw(row["id"], "promoted", {})
            changed_slugs.append(slug)
            promoted += 1
        except ValidationError as e:
            _mark_raw(row["id"], "invalid", json.loads(e.json()))
            invalidated += 1
        except Exception as e:
            log.exception("promote failed for raw %s", row["id"])
            _mark_raw(row["id"], "invalid", {"error": str(e)})
            invalidated += 1

    if changed_slugs:
        _trigger_revalidate(changed_slugs)

    return {"promoted": promoted, "invalidated": invalidated}


def _promote_one(source_id: str, external_id: str, source_url: str, data: ListingInput) -> str:
    slug = _build_slug(source_id, external_id, data.title)
    with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            INSERT INTO listings (
              id, slug, source_id, external_id, status, title, description,
              property_type, province, canton, distrito, address_text,
              bedrooms, bathrooms, parking_spots,
              lot_size_m2, construction_size_m2,
              base_price, currency, source_url, meta, for_sale_kind
            ) VALUES (
              gen_random_uuid(), %s, %s, %s, 'active', %s, %s,
              %s, %s, %s, %s, %s,
              %s, %s, %s,
              %s, %s,
              %s, %s, %s, %s::jsonb, %s
            )
            ON CONFLICT (source_id, external_id) DO UPDATE SET
              slug = EXCLUDED.slug,
              title = EXCLUDED.title,
              description = EXCLUDED.description,
              property_type = EXCLUDED.property_type,
              province = EXCLUDED.province,
              canton = EXCLUDED.canton,
              distrito = EXCLUDED.distrito,
              address_text = EXCLUDED.address_text,
              bedrooms = EXCLUDED.bedrooms,
              bathrooms = EXCLUDED.bathrooms,
              parking_spots = EXCLUDED.parking_spots,
              lot_size_m2 = EXCLUDED.lot_size_m2,
              construction_size_m2 = EXCLUDED.construction_size_m2,
              base_price = EXCLUDED.base_price,
              currency = EXCLUDED.currency,
              source_url = EXCLUDED.source_url,
              meta = EXCLUDED.meta,
              for_sale_kind = EXCLUDED.for_sale_kind,
              last_seen_at = now()
            RETURNING id
            """,
            (
                slug, source_id, external_id, data.title, data.description,
                data.property_type, data.province, data.canton, data.distrito,
                data.address_text,
                data.bedrooms, data.bathrooms, data.parking_spots,
                data.lot_size_m2, data.construction_size_m2,
                data.base_price, data.currency,
                str(data.source_url) if data.source_url else source_url,
                json.dumps(data.meta),
                data.for_sale_kind,
            ),
        )
        row = cur.fetchone()
        if row is None:
            raise RuntimeError("INSERT...RETURNING did not return a row")
        listing_id = row["id"]

        # Snapshot
        cur.execute(
            """
            INSERT INTO listing_snapshots (listing_id, price, currency, status)
            VALUES (%s, %s, %s, 'active')
            """,
            (listing_id, data.base_price, data.currency),
        )

        # Replace auctions (only for auction kind; direct_sale leaves them empty)
        cur.execute("DELETE FROM auctions WHERE listing_id = %s", (listing_id,))
        for a in data.auctions:
            if not a.scheduled_at:
                continue
            cur.execute(
                """
                INSERT INTO auctions
                  (listing_id, round, scheduled_at, location_text, base_price, currency, status)
                VALUES (%s, %s, %s, %s, %s, %s, 'scheduled')
                """,
                (listing_id, a.round, a.scheduled_at, a.location_text, a.base_price, a.currency),
            )

        # Replace images (metadata only; r2_key filled later by images.py)
        cur.execute(
            "DELETE FROM listing_images WHERE listing_id = %s AND r2_key IS NULL",
            (listing_id,),
        )
        for pos, url in enumerate(data.image_urls):
            cur.execute(
                """
                INSERT INTO listing_images (listing_id, position, source_url)
                VALUES (%s, %s, %s)
                """,
                (listing_id, pos, url),
            )

        conn.commit()
    return slug


def _mark_raw(raw_id: int, status: str, errors: dict[str, Any]) -> None:
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE raw_listings SET validation_status = %s, validation_errors = %s::jsonb "
            "WHERE id = %s",
            (status, json.dumps(errors), raw_id),
        )
        conn.commit()


def _build_slug(source: str, ext: str, title: str) -> str:
    base = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode().lower()
    base = re.sub(r"[^a-z0-9]+", "-", base).strip("-")
    base = base[:60] if base else "propiedad"
    short_ext = re.sub(r"[^a-z0-9]+", "", ext.lower())[:10] or uuid.uuid4().hex[:8]
    return f"{base}-{source}-{short_ext}"


def _trigger_revalidate(slugs: list[str]) -> None:
    url = os.environ.get("WEBHOOK_REVALIDATE_URL")
    token = os.environ.get("WEBHOOK_REVALIDATE_TOKEN")
    if not url or not token:
        log.info("no revalidate webhook configured, skipping")
        return
    try:
        httpx.post(url, json={"slugs": slugs}, headers={"X-Token": token}, timeout=10)
    except Exception:
        log.exception("revalidate webhook failed")
