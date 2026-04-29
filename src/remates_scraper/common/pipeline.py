"""Common scraper pipeline — writes to raw_listings with idempotency."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from psycopg.rows import dict_row

from .db import connect


def _content_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def upsert_raw_listing(
    run_id: int | None,
    source_id: str,
    external_id: str,
    source_url: str,
    payload: dict[str, Any],
) -> int:
    """Insert a raw_listing row if (source, external_id, content_hash) is new.
    Returns the existing or new row id."""
    h = _content_hash(payload)
    with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            INSERT INTO raw_listings
              (source_id, external_id, source_url, scrape_run_id, content_hash, payload)
            VALUES (%s, %s, %s, %s, %s, %s::jsonb)
            ON CONFLICT (source_id, external_id, content_hash) DO UPDATE
              SET scrape_run_id = EXCLUDED.scrape_run_id
            RETURNING id
            """,
            (source_id, external_id, source_url, run_id, h, json.dumps(payload)),
        )
        row = cur.fetchone()
        if row is None:
            raise RuntimeError("INSERT...RETURNING did not return a row")
        conn.commit()
        return int(row["id"])


class ScrapeRunContext:
    """Context manager that creates a scrape_runs row and updates its status on exit."""

    def __init__(self, source_id: str) -> None:
        self.source_id = source_id
        self.id: int | None = None
        self.items_found = 0
        self.items_new = 0
        self.items_updated = 0
        self.items_failed = 0

    def __enter__(self) -> ScrapeRunContext:
        with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "INSERT INTO scrape_runs (source_id, status) VALUES (%s, 'running') RETURNING id",
                (self.source_id,),
            )
            row = cur.fetchone()
            if row is None:
                raise RuntimeError("INSERT...RETURNING did not return a row")
            self.id = int(row["id"])
            conn.commit()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: object,
    ) -> None:
        status = "failed" if exc else ("partial" if self.items_failed else "success")
        with connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                UPDATE scrape_runs SET
                  finished_at = now(),
                  status = %s,
                  items_found = %s,
                  items_new = %s,
                  items_updated = %s,
                  items_failed = %s,
                  error_summary = %s
                WHERE id = %s
                """,
                (
                    status,
                    self.items_found,
                    self.items_new,
                    self.items_updated,
                    self.items_failed,
                    str(exc) if exc else None,
                    self.id,
                ),
            )
            conn.commit()
