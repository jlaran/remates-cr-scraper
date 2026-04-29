from pathlib import Path

from remates_scraper.common.pdf import extract_text, find_edicto_blocks
from remates_scraper.spiders.judicial.parser import parse_edicto

FIX = Path(__file__).parent.parent / "fixtures" / "judicial"


def _all_blocks() -> list[str]:
    pages = extract_text(FIX / "sample_boletin.pdf")
    return find_edicto_blocks("\n".join(pages))


def test_parse_edicto_extracts_required_fields() -> None:
    """At least one edicto block must parse with the mandatory fields.

    Notes on fixture adaptation
    ---------------------------
    The fixture (Boletín Judicial Nº 195, 2023-10-23) is a succession-only
    issue that contains no auction notices (remates) and therefore no price
    information.  The parser still extracts the fields that are present:
    - expediente number (required — block is skipped if missing)
    - province (detected from text; falls back to "San José")
    - auctions list (populated from any Spanish dates in the block)
    - base_price is 0.0 when the block has no price text (accepted here)

    In production, boletines that include "AVISO DE REMATE" sections will
    have full price + auction data.
    """
    blocks = _all_blocks()
    assert blocks, "fixture has no blocks"

    parsed_count = 0
    for block in blocks:
        result = parse_edicto(block)
        if result is None:
            continue
        parsed_count += 1

        # Mandatory: title must be non-empty
        assert result["title"]

        # currency is always set (defaults to CRC)
        assert result["currency"] in ("CRC", "USD")

        # expediente must be present (parse_edicto returns None without it)
        assert result["meta"].get("expediente")

        # auctions list is present (may be empty if no Spanish dates found)
        assert "auctions" in result

        # province must be a valid Costa Rican province or the default
        assert result["province"] in (
            "San José",
            "Alajuela",
            "Cartago",
            "Heredia",
            "Guanacaste",
            "Puntarenas",
            "Limón",
        )

    assert parsed_count > 0, "no edicto could be parsed"
