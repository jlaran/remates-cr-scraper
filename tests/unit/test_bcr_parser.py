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


def test_parse_detail_extracts_area_fields():
    """Area fields must now be populated from the plain-label siblings in the fixture."""
    html = (FIX / "sample_detail.html").read_text(encoding="utf-8")
    detail = parse_detail_page(html, source_url="https://ventadebienes.bancobcr.com/example")
    assert detail["construction_size_m2"] == 165.0, (
        f"expected 165.0, got {detail['construction_size_m2']}"
    )
    assert detail["lot_size_m2"] == 39045.46, (
        f"expected 39045.46, got {detail['lot_size_m2']}"
    )
    assert detail["meta"]["area_terreno"], "area_terreno meta must be non-empty"
    assert detail["meta"]["area_construccion"], "area_construccion meta must be non-empty"


def test_parse_detail_extracts_bedrooms_and_bathrooms():
    """Bedrooms and bathrooms must be extracted from the cell-33 feature grid."""
    html = (FIX / "sample_detail.html").read_text(encoding="utf-8")
    detail = parse_detail_page(html, source_url="https://ventadebienes.bancobcr.com/example")
    assert detail["bedrooms"] == 3, f"expected 3 bedrooms, got {detail['bedrooms']}"
    assert detail["bathrooms"] == 2, f"expected 2 bathrooms, got {detail['bathrooms']}"
    assert detail["parking_spots"] >= 1, "garage present → parking_spots must be ≥ 1"


def test_parse_detail_extracts_image_gallery():
    """Detail page must return multiple gallery images from WCM CDN."""
    html = (FIX / "sample_detail.html").read_text(encoding="utf-8")
    detail = parse_detail_page(html, source_url="https://ventadebienes.bancobcr.com/example")
    assert len(detail["image_urls"]) >= 1, "expected at least one gallery image"
    for url in detail["image_urls"]:
        assert url.startswith("https://"), f"image URL must be absolute: {url}"
        assert "/wps/wcm/" in url, f"expected WCM CDN image, got: {url}"


def test_parse_detail_extracts_folio_and_description():
    """Folio real and description must be non-empty for the fixture listing."""
    html = (FIX / "sample_detail.html").read_text(encoding="utf-8")
    detail = parse_detail_page(html, source_url="https://ventadebienes.bancobcr.com/example")
    assert detail["meta"]["folio_real"], "folio_real must be non-empty"
    assert detail["description"], "description must be non-empty"


def test_parse_detail_extracts_plano_url():
    """Plano catastrado PDF link must be captured when present."""
    html = (FIX / "sample_detail.html").read_text(encoding="utf-8")
    detail = parse_detail_page(html, source_url="https://ventadebienes.bancobcr.com/example")
    assert detail["meta"]["plano_url"].startswith("https://"), (
        f"plano_url must be an absolute URL, got: {detail['meta']['plano_url']!r}"
    )


def test_parse_detail_live_fixture():
    """Validate the live-captured fixture (sample_detail_live.html) against key fields."""
    html = (FIX / "sample_detail_live.html").read_text(encoding="utf-8")
    detail = parse_detail_page(html, source_url="https://ventadebienes.bancobcr.com/live")
    assert detail["title"] == "Casa en San José - BCR-BA1030050523"
    assert detail["base_price"] == 353462000.0
    assert detail["province"] == "San José"
    assert detail["construction_size_m2"] == 268.0
    assert detail["lot_size_m2"] == 1880.89
    assert len(detail["image_urls"]) >= 1
    assert detail["meta"]["folio_real"] == "1-36045-000"
    assert detail["description"], "live fixture description must be non-empty"
    assert detail["meta"]["plano_url"].startswith("https://")
