"""Geocode listings with geocoding_confidence='unknown'."""
from __future__ import annotations

import logging

from psycopg.rows import dict_row

from remates_scraper.common.db import connect
from remates_scraper.common.geocoder import geocode

log = logging.getLogger(__name__)


def run(batch: int = 50) -> dict[str, int]:
    geocoded = 0
    with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT id, address_text, canton, province
            FROM listings
            WHERE geocoding_confidence = 'unknown' AND status = 'active'
            ORDER BY first_seen_at ASC
            LIMIT %s
            """,
            (batch,),
        )
        rows = list(cur.fetchall())

    for row in rows:
        query = " ".join(
            filter(None, [row.get("address_text"), row.get("canton"), row.get("province")])
        )
        if not query.strip():
            continue
        result = geocode(query, province=row["province"], canton=row.get("canton"))
        with connect() as conn2, conn2.cursor() as cur2:
            cur2.execute(
                """
                UPDATE listings SET
                  location = ST_GeomFromText('POINT(' || %s || ' ' || %s || ')', 4326),
                  geocoding_confidence = %s
                WHERE id = %s
                """,
                (result.lng, result.lat, result.confidence, row["id"]),
            )
            conn2.commit()
        geocoded += 1
    return {"geocoded": geocoded}
