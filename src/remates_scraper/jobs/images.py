"""Download listing images, validate, resize, upload to R2."""
from __future__ import annotations

import logging

from psycopg.rows import dict_row

from remates_scraper.common.db import connect
from remates_scraper.common.images import download, resize_to_width, validate_mime
from remates_scraper.common.storage import R2Storage

log = logging.getLogger(__name__)

# Referer sent when downloading images that belong to BCR listings.
# BCR's Radware-protected WCM CDN may reject requests without a Referer header.
BCR_REFERER = "https://ventadebienes.bancobcr.com/"


def run(batch: int = 100) -> dict[str, int]:
    storage = R2Storage()
    uploaded = 0
    failed = 0

    with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT li.id, li.listing_id, li.source_url AS img_url,
                   l.source_id
            FROM listing_images li
            JOIN listings l ON l.id = li.listing_id
            WHERE li.r2_key IS NULL
            ORDER BY li.id ASC
            LIMIT %s
            """,
            (batch,),
        )
        rows = list(cur.fetchall())

    for row in rows:
        try:
            referer: str | None = None
            if row["source_id"] == "bcr":
                referer = BCR_REFERER

            data = download(row["img_url"], referer=referer)
            mime = validate_mime(data)
            if mime is None:
                failed += 1
                continue

            ext = mime.split("/", 1)[1]
            base_key = f"listings/{row['listing_id']}/{row['id']}"

            storage.upload(data, f"{base_key}-original.{ext}", mime)

            img1200, w1, h1 = resize_to_width(data, 1200)
            storage.upload(img1200, f"{base_key}-1200.jpg", "image/jpeg")

            img400, _w2, _h2 = resize_to_width(data, 400)
            storage.upload(img400, f"{base_key}-400.jpg", "image/jpeg")

            with connect() as conn2, conn2.cursor() as cur2:
                cur2.execute(
                    """
                    UPDATE listing_images SET
                      r2_key = %s, width = %s, height = %s, bytes = %s
                    WHERE id = %s
                    """,
                    (base_key, w1, h1, len(data), row["id"]),
                )
                conn2.commit()
            uploaded += 1
        except Exception:
            log.exception("failed image %s", row["id"])
            failed += 1

    return {"uploaded": uploaded, "failed": failed}
