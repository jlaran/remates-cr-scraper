"""Reconcile expired listings."""
from __future__ import annotations

from psycopg.rows import dict_row

from remates_scraper.common.db import connect


def run() -> dict[str, int]:
    with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            UPDATE listings SET status = 'expired'
            WHERE status = 'active'
              AND last_seen_at < now() - interval '14 days'
            RETURNING id
            """
        )
        unseen = len(cur.fetchall())

        # Direct sales don't expire by auction date — only by last_seen.
        cur.execute(
            """
            UPDATE listings l SET status = 'expired'
            WHERE l.status = 'active'
              AND l.for_sale_kind = 'auction'
              AND NOT EXISTS (
                SELECT 1 FROM auctions a
                WHERE a.listing_id = l.id
                  AND a.scheduled_at > now() - interval '30 days'
              )
            RETURNING l.id
            """
        )
        no_recent_auction = len(cur.fetchall())

        conn.commit()
    return {"expired_unseen": unseen, "expired_no_recent_auction": no_recent_auction}
