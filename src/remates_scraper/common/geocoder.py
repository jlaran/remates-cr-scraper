"""Geocoding helpers — Nominatim primary + canton centroid fallback."""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Literal

import httpx
from psycopg.rows import dict_row

from .db import connect

GeoConfidence = Literal["exact", "approx_canton", "approx_province", "unknown"]

PROVINCE_ALIASES = {
    "san jose": "San José",
    "san josé": "San José",
    "s.j.": "San José",
    "sj": "San José",
    "alajuela": "Alajuela",
    "cartago": "Cartago",
    "heredia": "Heredia",
    "guanacaste": "Guanacaste",
    "puntarenas": "Puntarenas",
    "limon": "Limón",
    "limón": "Limón",
}


def normalize_province(text: str) -> str | None:
    """Map any variant of a Costa Rican province name to its canonical form."""
    return PROVINCE_ALIASES.get(text.strip().lower())


@dataclass
class GeocodeResult:
    lat: float
    lng: float
    confidence: GeoConfidence


def geocode(
    query: str,
    province: str | None = None,
    canton: str | None = None,
) -> GeocodeResult:
    """Return lat/lng for an address. Uses cache -> Nominatim -> canton -> provincia."""
    cached = _cache_get(query)
    if cached:
        return GeocodeResult(cached[0], cached[1], "exact")

    nominatim = _try_nominatim(query)
    if nominatim:
        _cache_set(query, nominatim.lat, nominatim.lng)
        return nominatim

    if canton:
        c = _canton_centroid(canton)
        if c:
            return GeocodeResult(c[0], c[1], "approx_canton")

    if province:
        p = _province_centroid(province)
        if p:
            return GeocodeResult(p[0], p[1], "approx_province")

    return GeocodeResult(9.9281, -84.0907, "unknown")  # San José as last fallback


def _try_nominatim(query: str) -> GeocodeResult | None:
    try:
        r = httpx.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": query + ", Costa Rica", "format": "json", "limit": 1},
            headers={"User-Agent": "remates.cr/0.1 (contact@example.com)"},
            timeout=10,
        )
        time.sleep(1.1)  # Nominatim ToS: 1 req/sec
        if r.status_code != 200 or not r.json():
            return None
        item = r.json()[0]
        return GeocodeResult(float(item["lat"]), float(item["lon"]), "exact")
    except Exception:
        return None


def _canton_centroid(name: str) -> tuple[float, float] | None:
    with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "SELECT ST_Y(centroid) AS lat, ST_X(centroid) AS lng "
            "FROM cantones_cr WHERE LOWER(name) = LOWER(%s) LIMIT 1",
            (name,),
        )
        row: dict[str, Any] | None = cur.fetchone()
        if not row:
            return None
        return float(row["lat"]), float(row["lng"])


def _province_centroid(name: str) -> tuple[float, float] | None:
    centroids = {
        "San José": (9.9281, -84.0907),
        "Alajuela": (10.0162, -84.2117),
        "Cartago": (9.8638, -83.9197),
        "Heredia": (10.0023, -84.1167),
        "Guanacaste": (10.6346, -85.4407),
        "Puntarenas": (9.9763, -84.8384),
        "Limón": (10.0000, -83.0333),
    }
    return centroids.get(name)


def _cache_get(query: str) -> tuple[float, float] | None:
    with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "UPDATE geocoding_cache SET hit_count = hit_count + 1, last_used_at = now() "
            "WHERE query_text = %s RETURNING lat, lng",
            (query,),
        )
        row: dict[str, Any] | None = cur.fetchone()
        conn.commit()
        return (row["lat"], row["lng"]) if row else None


def _cache_set(query: str, lat: float, lng: float) -> None:
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO geocoding_cache (query_text, lat, lng) VALUES (%s, %s, %s) "
            "ON CONFLICT (query_text) DO NOTHING",
            (query, lat, lng),
        )
        conn.commit()
