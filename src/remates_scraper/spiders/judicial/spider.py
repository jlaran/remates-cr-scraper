"""Boletín Judicial spider — downloads latest PDF, segments edictos, writes raw_listings."""
from __future__ import annotations

import logging
from datetime import date, timedelta
from pathlib import Path

import httpx

from remates_scraper.common.pdf import extract_text, find_edicto_blocks
from remates_scraper.common.pipeline import ScrapeRunContext, upsert_raw_listing
from remates_scraper.spiders.judicial.parser import parse_edicto

USER_AGENT = "remates.cr/0.1 (+https://remates.cr)"
BASE_URL = "https://www.imprentanacional.go.cr/pub-boletin"
MAX_DAYS_BACK = 14
DOWNLOAD_TIMEOUT = 60.0

log = logging.getLogger(__name__)


def run() -> dict[str, int]:
    pdf_url, pdf_bytes = _download_latest_boletin()
    if pdf_url is None:
        raise RuntimeError(f"no Boletín PDF found in the last {MAX_DAYS_BACK} days")

    tmp = Path("/tmp") / f"boletin_{date.today().isoformat()}.pdf"
    tmp.write_bytes(pdf_bytes)
    log.info("downloaded %s (%d bytes) to %s", pdf_url, len(pdf_bytes), tmp)

    pages = extract_text(tmp)
    blocks = find_edicto_blocks("\n".join(pages))
    log.info("found %d candidate blocks", len(blocks))

    with ScrapeRunContext("judicial") as run_ctx:
        for idx, block in enumerate(blocks):
            run_ctx.items_found += 1
            try:
                parsed = parse_edicto(block)
                if parsed is None:
                    run_ctx.items_failed += 1
                    upsert_raw_listing(
                        run_id=run_ctx.id,
                        source_id="judicial",
                        external_id=f"{date.today().isoformat()}-{idx}-unparsed",
                        source_url=pdf_url,
                        payload={"unparsed_text": block},
                    )
                    continue
                parsed["source_url"] = pdf_url
                ext_id = parsed["meta"]["expediente"]
                upsert_raw_listing(
                    run_id=run_ctx.id,
                    source_id="judicial",
                    external_id=ext_id,
                    source_url=pdf_url,
                    payload=parsed,
                )
                run_ctx.items_new += 1
            except Exception:
                log.exception("failed parsing block #%d", idx)
                run_ctx.items_failed += 1
        return {
            "found": run_ctx.items_found,
            "new": run_ctx.items_new,
            "failed": run_ctx.items_failed,
        }


def _download_latest_boletin() -> tuple[str | None, bytes]:
    """Try last MAX_DAYS_BACK dates, return (url, content) of the first that exists."""
    headers = {"User-Agent": USER_AGENT}
    for days_back in range(0, MAX_DAYS_BACK):
        d = date.today() - timedelta(days=days_back)
        url = (
            f"{BASE_URL}/{d.year}/{d.strftime('%m')}/"
            f"bol_{d.strftime('%d')}_{d.strftime('%m')}_{d.year}.pdf"
        )
        try:
            with httpx.Client(
                headers=headers, follow_redirects=True, timeout=DOWNLOAD_TIMEOUT
            ) as client:
                # HEAD first to avoid downloading large PDFs we don't need
                head_response = client.head(url)
                if head_response.status_code != 200:
                    log.debug("HEAD %s -> %d", url, head_response.status_code)
                    continue
                # Some servers return text/html for missing PDFs even with 200 — verify content-type
                ctype = head_response.headers.get("content-type", "").lower()
                if "pdf" not in ctype:
                    log.debug("HEAD %s content-type=%s, skipping", url, ctype)
                    continue
                full_response = client.get(url)
                if full_response.status_code != 200:
                    log.debug("GET %s -> %d", url, full_response.status_code)
                    continue
                log.info("found Boletín at %s", url)
                return url, full_response.content
        except httpx.HTTPError as e:
            log.debug("URL %s failed: %s", url, e)
            continue
    return None, b""
