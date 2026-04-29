"""PDF parsing helpers — wraps pdfplumber for the Boletín Judicial."""
from __future__ import annotations

import re
from pathlib import Path

import pdfplumber

# Section headers that open a block of edictos de remate (auction notices).
# The Boletín Judicial uses these headers in issues that contain auction content.
EDICTO_HEADERS = (
    "AVISO DE REMATE",
    "AVISOS DE REMATE",
    "EDICTO DE REMATE",
    "EDICTOS DE REMATE",
    "AVISO JUDICIAL",
    "AVISOS JUDICIALES",
    # Fallback section headers found in succession-only issues
    "ADMINISTRACIÓN JUDICIAL",
)

# Terminators: each individual notice ends with this pattern in the Boletín
_IN_TERMINATOR = re.compile(
    r"—\s*1\s+vez\.—\s*\(\s*IN\d+\s*\)\.",
    re.IGNORECASE,
)


def extract_text(pdf_path: Path | str) -> list[str]:
    """Extract text from each page of a PDF."""
    pages: list[str] = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            pages.append(text)
    return pages


def find_edicto_blocks(full_text: str) -> list[str]:
    """Segment edictos from the Boletín Judicial.

    Strategy 1 — section-header split: if the text contains known section
    headers (e.g. "AVISO DE REMATE"), split on those headers first.

    Strategy 2 — IN-number split: the Boletín terminates every individual
    notice with a publication-reference marker such as
    '—1 vez.—( IN2023819949 ).'  We split on these to get individual blocks
    and then filter for blocks that look like judicial/notarial notices.
    """
    # Try header-based segmentation first
    header_pattern = re.compile(
        r"(?=" + "|".join(re.escape(h) for h in EDICTO_HEADERS) + r")",
        re.IGNORECASE,
    )
    parts = header_pattern.split(full_text)
    # Keep only parts that look like remate edictos (preferred content)
    remate_blocks = [
        p.strip()
        for p in parts
        if p.strip() and _looks_like_remate_edicto(p)
    ]
    if remate_blocks:
        return remate_blocks

    # Fallback: split by individual-notice terminators and return all
    # judicial/notarial notice blocks (used when the issue has no auctions)
    raw_parts = _IN_TERMINATOR.split(full_text)
    blocks = [
        p.strip()
        for p in raw_parts
        if p.strip() and _looks_like_judicial_notice(p)
    ]
    return blocks


def _looks_like_remate_edicto(text: str) -> bool:
    """Return True if *text* looks like an auction edicto."""
    lower = text.lower()
    return ("remate" in lower or "subasta" in lower) and len(text) > 200


def _looks_like_judicial_notice(text: str) -> bool:
    """Return True if *text* looks like any judicial/notarial notice."""
    lower = text.lower()
    has_content = (
        "sucesorio" in lower
        or "expediente" in lower
        or "juzgado" in lower
        or "notaría" in lower
        or "remate" in lower
        or "subasta" in lower
    )
    return has_content and len(text) > 100
