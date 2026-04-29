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
    assert len(blocks) >= 1
    # Each block must look like a judicial/notarial notice.
    # The fixture is a succession-only issue (no remates), so we accept
    # "sucesorio", "expediente", "juzgado", or "notaría" as valid indicators.
    for b in blocks:
        lower = b.lower()
        assert (
            "remate" in lower
            or "subasta" in lower
            or "sucesorio" in lower
            or "expediente" in lower
            or "juzgado" in lower
            or "notaría" in lower
        ), f"Block does not look like a judicial notice:\n{b[:200]}"
