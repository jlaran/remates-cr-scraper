from remates_scraper.spiders.judicial.parser import parse_edicto

# A minimal synthetic remate edicto block that exercises all parser paths.
# The succession-only PDF fixture (Boletín Nº 195, 2023-10-23) contains no
# remate notices; after segmentation tightening it yields 0 blocks.
# We use an inline synthetic block to keep the parser unit-tested independently
# from the PDF segmentation layer.
SYNTHETIC_REMATE_BLOCK = (
    "AVISO DE REMATE\n"
    "Juzgado Civil y de Trabajo del Primer Circuito Judicial de San José.\n"
    "Expediente: 23-000254-0504-CI-0. Se procede a la venta en remate público de la "
    "finca N° 1-12345-000, ubicada en San José, canton Central, provincia San José. "
    "Precio base: ₡85.000.000,00. El remate se celebrará el 15 de mayo del 2025.\n"
    "—1 vez.—(IN2024123456)."
)

SYNTHETIC_NO_EXPEDIENTE = (
    "Se remata una casa en Alajuela. remate el 10 de junio del 2025. "
    "Precio base ₡50.000.000,00."
)


def test_parse_edicto_extracts_required_fields() -> None:
    """parse_edicto returns a valid listing dict for a well-formed remate block."""
    result = parse_edicto(SYNTHETIC_REMATE_BLOCK)
    assert result is not None, "parser must succeed on a complete remate block"

    assert result["for_sale_kind"] == "auction"

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


def test_parse_edicto_returns_none_without_expediente() -> None:
    """parse_edicto must return None when no expediente number is present."""
    result = parse_edicto(SYNTHETIC_NO_EXPEDIENTE)
    assert result is None, "block without expediente must be rejected"
