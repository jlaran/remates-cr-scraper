from pathlib import Path

from remates_scraper.spiders.bcr.parser import (
    normalize_listings_item,
    parse_detail_page,
    parse_listings_page,
)

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
        # image_url key must always be present (may be empty string if no img in card)
        assert "image_url" in item, "every item must have an image_url key"


def test_parse_listings_page_extracts_image_urls():
    """At least one card in the fixture must have a non-empty, absolute image_url."""
    html = (FIX / "listings_page.html").read_text(encoding="utf-8")
    items = parse_listings_page(html)
    urls_with_img = [it["image_url"] for it in items if it.get("image_url")]
    assert urls_with_img, "expected at least one listings card to have an image_url"
    for url in urls_with_img:
        assert url.startswith("https://"), f"image_url must be absolute: {url}"
        assert "/wps/wcm/" in url, f"expected WCM CDN URL, got: {url}"


def test_normalize_listings_item_includes_image_url():
    """normalize_listings_item should populate image_urls from the card's image_url."""
    item = {
        "external_id": "1-23456-000",
        "detail_url": "https://ventadebienes.bancobcr.com/wps/portal/bcrb/bcrbienes/bienes/Casas/detalle/?codigo=1-23456-000",
        "title": "Casa en San José",
        "raw_price": "¢50.000.000,00",
        "province_raw": "SAN JOSE",
        "canton_raw": "DESAMPARADOS",
        "image_url": "https://ventadebienes.bancobcr.com/wps/wcm/connect/bcrb/abc/foto.jpg",
    }
    payload = normalize_listings_item(item)
    assert payload["image_urls"] == [
        "https://ventadebienes.bancobcr.com/wps/wcm/connect/bcrb/abc/foto.jpg"
    ]


def test_normalize_listings_item_empty_image_url():
    """normalize_listings_item must produce empty image_urls when no card image is available."""
    item = {
        "external_id": "1-99999-000",
        "detail_url": "https://ventadebienes.bancobcr.com/wps/portal/bcrb/bcrbienes/bienes/Casas/detalle/?codigo=1-99999-000",
        "title": "Lote en Cartago",
        "raw_price": "¢20.000.000,00",
        "province_raw": "CARTAGO",
        "canton_raw": "CARTAGO",
        "image_url": "",
    }
    payload = normalize_listings_item(item)
    assert payload["image_urls"] == []


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
