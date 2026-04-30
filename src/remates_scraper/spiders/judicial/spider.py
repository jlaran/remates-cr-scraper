"""La Gaceta spider — downloads latest official-publication PDF.

Segments edictos and writes raw_listings.

Originally targeted the Boletín Judicial, but Imprenta Nacional discontinued that feed
in late 2023. La Gaceta is the active official publication that carries remate edictos.
URL pattern: /pub/<YYYY>/<MM>/<DD>/COMP_<DD>_<MM>_<YYYY>.pdf
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from pathlib import Path

import httpx

from remates_scraper.common.pdf import extract_text, find_edicto_blocks
from remates_scraper.common.pipeline import ScrapeRunContext, upsert_raw_listing
from remates_scraper.spiders.judicial.parser import parse_edicto

USER_AGENT = "remates.cr/0.1 (+https://remates.cr)"
BASE_URL = "https://www.imprentanacional.go.cr/pub"
MAX_DAYS_BACK = 14
DOWNLOAD_TIMEOUT = 120.0  # Gaceta PDFs can be 4–10 MB

log = logging.getLogger(__name__)


def run() -> dict[str, int]:
    pdf_url, pdf_bytes = _download_latest_boletin()
    if pdf_url is None:
        raise RuntimeError(f"no Gaceta PDF found in the last {MAX_DAYS_BACK} days")

    tmp = Path("/tmp") / f"gaceta_{date.today().isoformat()}.pdf"
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
                    # Block was not a parseable remate edicto — skip silently
                    run_ctx.items_failed += 1
                    log.debug("block #%d did not parse as remate edicto, skipping", idx)
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
    """Try last MAX_DAYS_BACK dates, return (url, content) of the first that exists.

    The Imprenta Nacional server returns 200 with `Acceso no valido` HTML for missing
    files, so we verify the GET response's content-type AND magic bytes to confirm it's
    actually a PDF.
    """
    headers = {"User-Agent": USER_AGENT}
    for days_back in range(0, MAX_DAYS_BACK):
        d = date.today() - timedelta(days=days_back)
        # La Gaceta URL pattern: /pub/<YYYY>/<MM>/<DD>/COMP_<DD>_<MM>_<YYYY>.pdf
        yyyy = d.strftime("%Y")
        mm = d.strftime("%m")
        dd = d.strftime("%d")
        url = f"{BASE_URL}/{yyyy}/{mm}/{dd}/COMP_{dd}_{mm}_{yyyy}.pdf"
        try:
            with httpx.Client(
                headers=headers, follow_redirects=True, timeout=DOWNLOAD_TIMEOUT
            ) as client:
                response = client.get(url)
                if response.status_code != 200:
                    log.debug("GET %s -> %d", url, response.status_code)
                    continue
                ctype = response.headers.get("content-type", "").lower()
                if "pdf" not in ctype:
                    log.debug("GET %s content-type=%s, skipping", url, ctype)
                    continue
                # Verify magic bytes — Imprenta sometimes returns 200 with HTML body
                if not response.content.startswith(b"%PDF"):
                    log.debug("GET %s content not PDF (first bytes %r), skipping",
                              url, response.content[:8])
                    continue
                log.info("found Gaceta at %s (%d bytes)", url, len(response.content))
                return url, response.content
        except httpx.HTTPError as e:
            log.debug("URL %s failed: %s", url, e)
            continue
    return None, b""
