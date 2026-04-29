"""Image download, validation and resizing."""
from __future__ import annotations

import io

import httpx
from PIL import Image

ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp"}
MAX_BYTES = 10 * 1024 * 1024


def download(url: str, timeout: float = 30.0) -> bytes:
    r = httpx.get(url, timeout=timeout, follow_redirects=True)
    r.raise_for_status()
    if len(r.content) > MAX_BYTES:
        raise ValueError(f"image larger than {MAX_BYTES} bytes")
    return r.content


def validate_mime(data: bytes) -> str | None:
    try:
        img = Image.open(io.BytesIO(data))
        img.verify()
    except Exception:
        return None
    fmt = (img.format or "").lower()
    return {
        "jpeg": "image/jpeg",
        "png": "image/png",
        "webp": "image/webp",
    }.get(fmt)


def resize_to_width(data: bytes, target_width: int, quality: int = 82) -> tuple[bytes, int, int]:
    """Returns (jpeg_bytes, width, height)."""
    img = Image.open(io.BytesIO(data)).convert("RGB")
    w, h = img.size
    if w <= target_width:
        return data, w, h
    new_h = int(h * target_width / w)
    img = img.resize((target_width, new_h), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality, optimize=True)
    return buf.getvalue(), target_width, new_h
