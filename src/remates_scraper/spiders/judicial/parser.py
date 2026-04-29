"""Parser for individual Boletín Judicial edictos."""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from remates_scraper.common.geocoder import normalize_province

# Expediente formats seen in the Boletín:
#   Court format:  23-000254-0504-CI-0  /  22-000069-0386-CI-4
#   Notarial:      0001-2023  /  08-2023  /  2023-0003
EXPEDIENTE_RE = re.compile(
    r"\b(?:"
    r"\d{2}-\d{4,6}-\d{3,4}-[A-Z][\w-]*"  # court expediente
    r"|"
    r"(?:Exp(?:ediente)?[\s:.N°#]*)?(\d{3,6}-\d{2,4}(?:-[A-Za-z.]+)?)"  # notarial
    r")\b",
    re.IGNORECASE,
)

JUZGADO_RE = re.compile(r"(Juzgado[^,;.\n]{3,80})", re.IGNORECASE)
FINCA_RE = re.compile(r"finca\s+(?:N[°º]?\s*)?([0-9]+-[0-9]+(?:-[0-9]+)?)", re.IGNORECASE)
PLANO_RE = re.compile(
    r"plano\s+(?:catastrado\s+)?(?:N[°º]?\s*)?([A-Z]{1,3}-[0-9]+-[0-9]+)", re.IGNORECASE
)
PRICE_RE = re.compile(
    r"(?:precio|base|monto)[^₡$]{0,30}(₡|\$|US\$|USD|CRC)\s*([\d.,]+)",
    re.IGNORECASE,
)
DATE_RE = re.compile(
    r"(\d{1,2})\s+de\s+(enero|febrero|marzo|abril|mayo|junio|julio|agosto|"
    r"septiembre|octubre|noviembre|diciembre)\s+(?:del?\s+)?(\d{4})",
    re.IGNORECASE,
)
PROPERTY_TYPE_KEYWORDS = {
    "casa": "casa",
    "apartamento": "apartamento",
    "apto": "apartamento",
    "lote": "lote",
    "local": "local_comercial",
    "oficina": "oficina",
    "bodega": "industrial",
    "industrial": "industrial",
    "finca": "finca",
}
MONTHS = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}


def parse_edicto(block: str) -> dict[str, Any] | None:
    """Return a normalised dict for *block*, or None if minimal fields are missing.

    Minimal requirements: at least one expediente number.
    base_price may be 0.0 when the block is a succession notice with no
    price information (common in non-auction issues of the Boletín Judicial).
    """
    expediente = _extract_expediente(block)
    if not expediente:
        return None

    base_price, currency = _parse_price(block)
    auctions = _parse_auctions(block, base_price, currency)

    juzgado = _first(JUZGADO_RE, block, group=1)
    finca = _first(FINCA_RE, block, group=1)
    plano = _first(PLANO_RE, block, group=1)
    province = _detect_province(block)
    property_type = _detect_property_type(block)

    title = _build_title(property_type, finca, juzgado)

    return {
        "title": title,
        "description": _condense(block),
        "image_urls": [],
        "base_price": base_price,
        "currency": currency,
        "province": province or "San José",
        "canton": None,
        "property_type": property_type,
        "auctions": auctions,
        "meta": {
            "expediente": expediente,
            "juzgado": juzgado,
            "numero_finca": finca,
            "plano_catastrado": plano,
        },
        "source_url": None,  # set by spider
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _extract_expediente(text: str) -> str | None:
    """Extract any expediente number from *text*.

    Tries the full combined regex first, then falls back to the simpler
    notarial pattern (e.g. 'Expediente 0001-2023').
    """
    # Primary: full EXPEDIENTE_RE
    m = EXPEDIENTE_RE.search(text)
    if m:
        # group(0) is the full match; may include the label "Expediente N°..."
        # Return whichever capture group is non-empty, else group(0)
        return (m.group(1) or m.group(0)).strip()

    # Fallback: bare label + number (catches e.g. "Expediente 08-2023")
    fb = re.search(
        r"Exp(?:ediente)?[\s:.N°#]*(\d{2,6}[-/]\d{2,4})",
        text,
        re.IGNORECASE,
    )
    return fb.group(1).strip() if fb else None


def _first(pattern: re.Pattern[str], text: str, group: int = 1) -> str | None:
    m = pattern.search(text)
    return m.group(group).strip() if m else None


def _parse_price(text: str) -> tuple[float, str]:
    m = PRICE_RE.search(text)
    if not m:
        return 0.0, "CRC"
    sym, raw = m.group(1), m.group(2)
    cleaned = raw.replace(".", "").replace(",", "")
    try:
        amount = float(cleaned)
    except ValueError:
        return 0.0, "CRC"
    currency = "USD" if sym in ("US$", "USD", "$") else "CRC"
    return amount, currency


def _parse_auctions(
    text: str, base_price: float, currency: str
) -> list[dict[str, Any]]:
    matches = DATE_RE.findall(text)
    auctions: list[dict[str, Any]] = []
    for round_idx, (day, month, year) in enumerate(matches[:3], start=1):
        try:
            scheduled = datetime(int(year), MONTHS[month.lower()], int(day))
        except (ValueError, KeyError):
            continue
        auctions.append(
            {
                "round": round_idx,
                "scheduled_at": scheduled.isoformat(),
                "location_text": None,
                "base_price": base_price,
                "currency": currency,
            }
        )
    return auctions


def _detect_province(text: str) -> str | None:
    for word in re.findall(r"[A-ZÁÉÍÓÚ][a-záéíóú]+", text):
        norm = normalize_province(word)
        if norm:
            return norm
    return None


def _detect_property_type(text: str) -> str:
    lower = text.lower()
    for key, value in PROPERTY_TYPE_KEYWORDS.items():
        if key in lower:
            return value
    return "otro"


def _build_title(property_type: str, finca: str | None, juzgado: str | None) -> str:
    parts = [property_type.replace("_", " ").capitalize()]
    if finca:
        parts.append(f"finca {finca}")
    if juzgado:
        parts.append(juzgado.split(",")[0].strip())
    return " · ".join(parts)


def _condense(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()[:2000]
