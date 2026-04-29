from pathlib import Path

from remates_scraper.spiders.bcr.parser import parse_detail_page, parse_listings_page

FIX = Path(__file__).parent.parent / "fixtures" / "bcr"


def test_parse_listings_page_extracts_items():
    html = (FIX / "listings_page.html").read_text(encoding="utf-8")
    items = parse_listings_page(html)
    assert len(items) > 0, "no listings extracted from real BCR fixture"
    for item in items:
        assert item["external_id"], "every item must have an external_id"
        assert item["detail_url"].startswith("https://"), (
            f"detail_url must be absolute: {item['detail_url']}"
        )
        assert item["title"], "every item must have a title"


def test_parse_detail_extracts_required_fields():
    html = (FIX / "sample_detail.html").read_text(encoding="utf-8")
    detail = parse_detail_page(html, source_url="https://ventadebienes.bancobcr.com/example")
    assert detail["title"], "detail must have a title"
    assert detail["base_price"] > 0, "detail must have a positive base_price"
    assert detail["currency"] in ("CRC", "USD")
    assert detail["province"] in (
        "San José", "Alajuela", "Cartago", "Heredia",
        "Guanacaste", "Puntarenas", "Limón",
    )
    assert detail["property_type"] in (
        "casa", "apartamento", "lote", "local_comercial",
        "oficina", "industrial", "finca", "otro",
    )
    assert "auctions" in detail
    assert "image_urls" in detail
    assert detail["for_sale_kind"] == "direct_sale"
