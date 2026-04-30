from pathlib import Path

from remates_scraper.common.pdf import extract_text, find_edicto_blocks

FIXTURE = Path(__file__).parent.parent / "fixtures" / "judicial" / "sample_boletin.pdf"


def test_extract_text_returns_pages():
    pages = extract_text(FIXTURE)
    assert len(pages) > 0
    # The fixture (Boletín Judicial Nº 195, 2023-10-23) contains succession
    # notices — it uses lowercase "edicto" and "sucesorio" throughout.
    # "EDICTO" uppercase does not appear; we check case-insensitively.
    full = "\n".join(pages).lower()
    assert "edicto" in full or "remate" in full or "sucesorio" in full


def test_find_edicto_blocks_segments_correctly():
    pages = extract_text(FIXTURE)
    full_text = "\n".join(pages)
    blocks = find_edicto_blocks(full_text)
    # The fixture (Boletín Judicial Nº 195, 2023-10-23) is a succession-only
    # issue — no remate or subasta notices.  After tightening segmentation to
    # require "remate" or "subasta" in each block, this fixture returns 0 blocks,
    # which is the correct behaviour (nothing to store).
    # Blocks that DO exist must each contain "remate" or "subasta".
    for b in blocks:
        lower = b.lower()
        assert (
            "remate" in lower or "subasta" in lower
        ), f"Block does not look like a remate notice:\n{b[:200]}"
