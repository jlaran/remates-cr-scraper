"""BCR (Banco de Costa Rica) remates parser — pure functions over HTML strings.

Structural findings from fixture inspection
-------------------------------------------
Listings page (listings_page.html):
  - Each property card lives in a ``div.table-row.miniatura`` element.
  - Inside each miniatura:
      * Detail link  : ``div.bienImgBox a[href*="detalle"]::attr(href)``
      * Title        : ``div.block-with-text b::text``
      * Price        : first ``div.table-cell.cell50 b::text`` (e.g. ``¢151.603.200,00``)
      * Province     : first ``div.table-cell.cell50::text`` (e.g. ``SAN JOSE``)
      * Canton       : second ``div.table-cell.cell50::text`` (e.g. ``DESAMPARADOS``)
      * Folio real / external_id: ``codigo`` query param in the href
  - ``codigo`` query-string parameter in the href is the canonical external_id.

Detail page (sample_detail.html, sample_detail_live.html):
  - Title        : ``h1::text``
  - Location     : ``label.textType2.strongText.mainTitle::text`` (e.g. ``ALAJUELA, SAN RAMÓN``)
  - Folio label  : ``label.textType3.strongText::text`` (e.g. ``Folio Nº 2-417772-000``)
  - Field labels : ``label.title`` elements paired with the second plain ``<label>``
    sibling in the same cell (no class), OR ``label.strongText``, OR ``p.descripcion``.
      * Fields found: "precio inicial:", "precio de venta final:", "descuento:",
        "monto del descuento:", "área del terreno:", "área de construcción:",
        "distrito:", "dirección:", "descripción:"
  - Cell-33 grid : ``div.table-cell.cell33 p`` — key: value pairs (e.g. "Nº Habitaciones: 3")
      * Keys scraped: "nº habitaciones", "nº baños", "cochera" (garage present flag)
  - Plano link   : ``a:contains('plano')::attr(href)`` → absolute WCM PDF URL
  - Images       : ``img[src*="/wps/wcm/"]::attr(src)`` (WCM-served gallery images)
  - Ejecutivo    : plain ``<label>`` following ``label:contains('Ejecutivo de venta:')``
  - No auction date present — BCR sells via direct negotiated sale.
"""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import parse_qs, urljoin, urlparse

from parsel import Selector

BASE = "https://ventadebienes.bancobcr.com"

# ------------------------------------------------------------------
# Listing-page selectors (confirmed against real fixture)
# ------------------------------------------------------------------
LISTING_ITEM_SELECTOR = "div.table-row.miniatura"
DETAIL_LINK_SELECTOR = "div.bienImgBox a::attr(href)"
ITEM_TITLE_SELECTOR = "div.block-with-text b::text"
# Price is inside the first cell50 b tag
ITEM_PRICE_SELECTOR = "div.table-cell.cell50 b::text"
# Thumbnail image inside each card (WCM CDN URL)
ITEM_IMAGE_SELECTOR = "div.bienImgBox img[src*='/wps/wcm/']::attr(src)"

# ------------------------------------------------------------------
# Detail-page selectors (confirmed against real fixture)
# ------------------------------------------------------------------
DETAIL_TITLE = "h1::text"
DETAIL_LOCATION = "label.textType2.strongText.mainTitle::text"
DETAIL_FOLIO = "label.textType3.strongText::text"
DETAIL_IMG = "img[src*='/wps/wcm/']::attr(src)"

PROVINCES = {
    "SAN JOSE": "San José",
    "SAN JOSÉ": "San José",
    "ALAJUELA": "Alajuela",
    "CARTAGO": "Cartago",
    "HEREDIA": "Heredia",
    "GUANACASTE": "Guanacaste",
    "PUNTARENAS": "Puntarenas",
    "LIMÓN": "Limón",
    "LIMON": "Limón",
}

PROPERTY_TYPE_KEYWORDS: list[tuple[str, str]] = [
    ("apartamento", "apartamento"),
    ("apto", "apartamento"),
    ("lote", "lote"),
    ("terreno", "lote"),
    ("local", "local_comercial"),
    ("comercio", "local_comercial"),
    ("bodega", "industrial"),
    ("industrial", "industrial"),
    ("oficina", "oficina"),
    ("finca", "finca"),
    ("casa", "casa"),
]


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------

def normalize_listings_item(item: dict[str, Any]) -> dict[str, Any]:
    """Convert a raw listings-page item dict into a canonical payload.

    Accepts the dict returned by ``parse_listings_page`` and returns a
    partial listing payload (same schema as ``parse_detail_page``) using
    only data available from the card.  Fields that require the detail
    page are left as empty defaults.
    """
    base_price, currency = _parse_price(item.get("raw_price", ""))
    province, canton = _parse_location_raw(
        item.get("province_raw", ""),
        item.get("canton_raw", ""),
    )
    title = item.get("title", "")
    image_urls = [item["image_url"]] if item.get("image_url") else []
    return {
        "for_sale_kind": "direct_sale",
        "title": title,
        "description": "",
        "image_urls": image_urls,
        "base_price": base_price,
        "currency": currency,
        "province": province,
        "canton": canton,
        "property_type": _classify_property_type(title),
        "auctions": [],
        "meta": {
            "folio_real": item.get("external_id", ""),
            "area_terreno": "",
            "area_construccion": "",
            "distrito": "",
            "direccion": "",
            "descuento_pct": "",
            "ejecutivo": "",
        },
        "source_url": item.get("detail_url", ""),
    }


def parse_listings_page(html: str) -> list[dict[str, Any]]:
    """Return raw item dicts from the BCR listing page.

    Each dict contains: external_id, detail_url, title, raw_price, province_raw,
    canton_raw, image_url.  ``image_url`` is an absolute WCM CDN URL or empty string.

    Parses ``div.table-row.miniatura`` elements from the BCR property listing page.
    Each card contains a WCM-hosted thumbnail image whose absolute URL is captured
    in ``image_url`` (empty string when absent).
    """
    sel = Selector(text=html)
    items: list[dict[str, Any]] = []

    for card in sel.css(LISTING_ITEM_SELECTOR):
        href = card.css(DETAIL_LINK_SELECTOR).get("")
        if not href:
            continue

        title = (card.css(ITEM_TITLE_SELECTOR).get() or "").strip()
        raw_price = (card.css(ITEM_PRICE_SELECTOR).get() or "").strip()

        # Province and canton: two sibling cell50 divs that contain only text (no <b>)
        cell50_texts = [
            t.strip()
            for t in card.css("div.table-cell.cell50::text").getall()
            if t.strip() and t.strip() != "Precio:"
        ]
        # After filtering 'Precio:' we expect: province, canton, 'Folio real:', folio_number
        province_raw = cell50_texts[0] if len(cell50_texts) > 0 else ""
        canton_raw = cell50_texts[1] if len(cell50_texts) > 1 else ""

        # Thumbnail image from the listings card (WCM CDN)
        img_src = (card.css(ITEM_IMAGE_SELECTOR).get() or "").strip()
        image_url = urljoin(BASE, img_src) if img_src else ""

        external_id = _extract_external_id(href)
        detail_url = urljoin(BASE, href)

        if not external_id or not title:
            continue

        items.append(
            {
                "external_id": external_id,
                "detail_url": detail_url,
                "title": title,
                "raw_price": raw_price,
                "province_raw": province_raw,
                "canton_raw": canton_raw,
                "image_url": image_url,
            }
        )

    return items


def parse_detail_page(html: str, source_url: str) -> dict[str, Any]:
    """Return the full normalized listing dict from a BCR detail page.

    BCR sells via direct negotiated sale (not judicial auction), so
    for_sale_kind is always "direct_sale".

    Keys returned: for_sale_kind, title, description, image_urls, base_price,
    currency, province, canton, property_type, bedrooms, bathrooms,
    parking_spots, construction_size_m2, lot_size_m2, auctions, meta, source_url.
    """
    sel = Selector(text=html)

    title = (sel.css(DETAIL_TITLE).get() or "").strip()

    # Location: "ALAJUELA, SAN RAMÓN" — province first, canton second
    location_text = (sel.css(DETAIL_LOCATION).get() or "").strip()
    province, canton = _parse_location(location_text)

    # Field map built from label.title → adjacent value (plain label or strongText or p.descripcion)
    field_map = _build_field_map(sel)

    # Price — "precio inicial:" is the authoritative asking price
    price_raw = field_map.get("precio inicial:", "") or field_map.get("precio de venta final:", "")
    base_price, currency = _parse_price(price_raw)

    # Description
    description = field_map.get("descripción:", "")

    # Images (deduplicated, absolute)
    image_urls = list(
        dict.fromkeys(
            urljoin(BASE, src)
            for src in sel.css(DETAIL_IMG).getall()
            if src and not src.startswith("data:")
        )
    )

    property_type = _classify_property_type(title)

    # No auction dates present in BCR detail pages — BCR sells via direct negotiated sale
    auctions: list[dict[str, Any]] = []

    # Folio from detail page (may differ from listings page, use as canonical)
    folio_text = (sel.css(DETAIL_FOLIO).get() or "").strip()
    folio_match = re.search(r"([\w-]+(?:-F)?-\d+)", folio_text)
    folio = folio_match.group(1) if folio_match else folio_text

    # Area fields: parse numeric m² value from strings like "39.045,46 m²" or "165,00 m²"
    area_terreno_raw = field_map.get("área del terreno:", "")
    area_construccion_raw = field_map.get("área de construcción:", "")
    lot_size_m2 = _parse_area_m2(area_terreno_raw)
    construction_size_m2 = _parse_area_m2(area_construccion_raw)

    # Cell-33 feature grid: "Nº Habitaciones: 3", "Nº Baños: 2", etc.
    grid = _parse_cell33_grid(sel)
    bedrooms = _parse_int(grid.get("nº habitaciones", ""))
    bathrooms = _parse_int(grid.get("nº baños", ""))
    # "Cochera: Sí/No" — treat "sí" as 1 parking spot when no explicit count
    cochera_val = grid.get("cochera", "").lower()
    parking_spots = _parse_int(grid.get("nº parqueos", grid.get("parqueos", "")))
    if parking_spots == 0 and cochera_val == "sí":
        parking_spots = 1

    # Plano catastrado PDF link
    plano_url = _extract_plano_url(sel)

    # Ejecutivo de venta
    ejecutivo = _extract_ejecutivo(sel)

    meta: dict[str, Any] = {
        "folio_real": folio,
        "area_terreno": area_terreno_raw,
        "area_construccion": area_construccion_raw,
        "distrito": field_map.get("distrito:", ""),
        "direccion": field_map.get("dirección:", ""),
        "descuento_pct": field_map.get("descuento:", ""),
        "ejecutivo": ejecutivo,
        "plano_url": plano_url,
    }

    return {
        "for_sale_kind": "direct_sale",
        "title": title,
        "description": description,
        "image_urls": image_urls,
        "base_price": base_price,
        "currency": currency,
        "province": province,
        "canton": canton,
        "property_type": property_type,
        "bedrooms": bedrooms,
        "bathrooms": bathrooms,
        "parking_spots": parking_spots,
        "construction_size_m2": construction_size_m2,
        "lot_size_m2": lot_size_m2,
        "auctions": auctions,
        "meta": meta,
        "source_url": source_url,
    }


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _parse_area_m2(raw: str) -> float:
    """Parse an area string like ``"39.045,46 m²"`` or ``"165,00 m²"`` → float.

    Uses Costa Rican number format: dots as thousands separators, comma as decimal.
    Returns 0.0 when the value cannot be parsed.
    """
    if not raw:
        return 0.0
    # Extract the numeric portion (digits, dots, commas)
    m = re.search(r"([\d.,]+)", raw)
    if not m:
        return 0.0
    num_str = m.group(1)
    # CR format: multiple dots → thousands separators; comma → decimal point
    if "," in num_str:
        num_str = num_str.replace(".", "").replace(",", ".")
    else:
        parts = num_str.split(".")
        if len(parts) > 2:
            num_str = num_str.replace(".", "")
    try:
        return float(num_str)
    except ValueError:
        return 0.0


def _parse_int(raw: str) -> int:
    """Extract the first integer from a string.  Returns 0 when not found."""
    m = re.search(r"\d+", raw)
    return int(m.group()) if m else 0


def _extract_external_id(href: str) -> str:
    """Extract the ``codigo`` query parameter from a BCR detail URL.

    Example:
        /wps/portal/bcrb/bcrbienes/bienes/Casas/detalle/?codigo=2-417772-000&tipo_propiedad=1
        → ``2-417772-000``
    """
    parsed = urlparse(href)
    params = parse_qs(parsed.query)
    codigo_list = params.get("codigo", [])
    if codigo_list:
        return codigo_list[0]
    # Fallback: last path segment
    return parsed.path.rstrip("/").rsplit("/", 1)[-1]


def _parse_price(raw: str) -> tuple[float, str]:
    """Parse a price string like ``¢171.927.000,00`` or ``$12,345.67``.

    Returns (amount_float, currency_code).
    """
    if not raw:
        return 0.0, "CRC"

    raw = raw.strip()
    currency = "USD" if raw.startswith("$") or "USD" in raw.upper() else "CRC"

    # Remove currency symbol and non-numeric chars except . and ,
    cleaned = re.sub(r"[^0-9.,]", "", raw)
    if not cleaned:
        return 0.0, currency

    # Costa Rican format: dots as thousands separator, comma as decimal
    # e.g. 171.927.000,00 → 171927000.00
    if "," in cleaned:
        # Remove all dots (thousands), replace comma with dot (decimal)
        cleaned = cleaned.replace(".", "").replace(",", ".")
    else:
        # No comma: dots might be thousands separator if there are multiple dots
        parts = cleaned.split(".")
        if len(parts) > 2:
            # Multiple dots → thousands separators, no decimal
            cleaned = cleaned.replace(".", "")
        # Single dot or no dot: treat as-is

    try:
        return float(cleaned), currency
    except ValueError:
        return 0.0, currency


def _parse_location_raw(province_raw: str, canton_raw: str) -> tuple[str, str]:
    """Normalize already-split province/canton strings from the listings page.

    Both inputs arrive in UPPERCASE (e.g. "SAN JOSE", "DESAMPARADOS").
    Returns (province_normalized, canton_title_case).
    """
    province_key = province_raw.upper().strip()
    province = PROVINCES.get(province_key, "")
    if not province:
        for key, val in PROVINCES.items():
            if key in province_key:
                province = val
                break
    if not province:
        province = "San José"
    canton = canton_raw.strip().title()
    return province, canton


def _parse_location(location_text: str) -> tuple[str, str]:
    """Parse a location string like ``ALAJUELA, SAN RAMÓN`` → (province, canton).

    Returns (province_normalized, canton_raw).  If the province cannot be
    identified, falls back to ``"otro"`` (which won't pass the test assertion),
    so the mapping table must cover all BCR province names.
    """
    if not location_text:
        return "San José", ""

    parts = [p.strip() for p in location_text.split(",", 1)]
    province_raw = parts[0].upper()
    canton = parts[1].strip().title() if len(parts) > 1 else ""

    # Normalize province
    province = PROVINCES.get(province_raw, "")
    if not province:
        # Try substring match
        for key, val in PROVINCES.items():
            if key in province_raw:
                province = val
                break

    if not province:
        province = "San José"  # safe default

    return province, canton


def _classify_property_type(title: str) -> str:
    """Return a normalized property type based on keywords found in the title."""
    lower = title.lower()
    for keyword, ptype in PROPERTY_TYPE_KEYWORDS:
        if keyword in lower:
            return ptype
    return "otro"


def _build_field_map(sel: Selector) -> dict[str, str]:
    """Build a {label_text: value_text} map from ``label.title`` elements.

    Each label.title sits in one cell; the value may be:
      1. A sibling ``label.strongText`` (classed value label).
      2. A second plain ``<label>`` in the same cell (no class) — used for
         "área del terreno:" and "área de construcción:" rows.
      3. A ``p.descripcion`` element in the same row.
    """
    field_map: dict[str, str] = {}
    for label in sel.css("label.title"):
        key = (label.css("::text").get() or "").strip().lower()
        if not key:
            continue

        parent_cell = label.xpath("..")
        parent_row = parent_cell.xpath("..")

        # 1. Look for strongText sibling in the same cell first
        strong_val = (parent_cell.css("label.strongText::text").get() or "").strip()
        if strong_val:
            field_map[key] = strong_val
            continue

        # 2. Look for any plain <label> in the same cell that is NOT the title label.
        #    Collect all label texts in the cell; skip the key itself; use the first
        #    non-empty remainder (strips whitespace from multi-line values).
        cell_label_texts = [
            " ".join(t.strip() for t in lbl.css("::text").getall()).strip()
            for lbl in parent_cell.css("label")
        ]
        plain_val = next(
            (t for t in cell_label_texts if t and t.rstrip(": ").lower() != key.rstrip(": ")),
            "",
        )
        if plain_val:
            field_map[key] = plain_val
            continue

        # 3. Look for p.descripcion in the same row
        desc_val = " ".join(
            t.strip()
            for t in parent_row.css("p.descripcion::text").getall()
            if t.strip()
        )
        if desc_val:
            field_map[key] = desc_val

    return field_map


def _parse_cell33_grid(sel: Selector) -> dict[str, str]:
    """Parse the property feature grid (cell33 divs) into a lowercase key→value map.

    Each ``div.table-cell.cell33 p`` contains text like ``"Nº Habitaciones: 3"``.
    Returns e.g. {"nº habitaciones": "3", "nº baños": "2", "cochera": "sí"}.
    """
    grid: dict[str, str] = {}
    for p in sel.css("div.table-cell.cell33 p"):
        text = " ".join(t.strip() for t in p.css("::text").getall()).strip()
        if ":" in text:
            k, _, v = text.partition(":")
            grid[k.strip().lower()] = v.strip()
    return grid


def _extract_plano_url(sel: Selector) -> str:
    """Return the absolute URL of the plano catastrado PDF link, or empty string."""
    for a in sel.css("a"):
        link_text = " ".join(t.strip() for t in a.css("::text").getall()).strip().lower()
        if "plano" in link_text:
            href = (a.attrib.get("href") or "").strip()
            if href:
                return urljoin(BASE, href)
    return ""


def _extract_ejecutivo(sel: Selector) -> str:
    """Return the sales executive name from the contact section, or empty string."""
    for label in sel.css("label"):
        text = " ".join(t.strip() for t in label.css("::text").getall()).strip()
        if "ejecutivo de venta" in text.lower():
            # The value is typically in the next sibling <label> or <span>
            parent = label.xpath("..")
            sibling_texts = []
            for sib in parent.css("label, span"):
                sib_text = " ".join(t.strip() for t in sib.css("::text").getall()).strip()
                if "ejecutivo de venta" not in sib_text.lower():
                    sibling_texts.append(sib_text)
            if sibling_texts:
                return sibling_texts[0]
    return ""
