import io

from PIL import Image

from remates_scraper.common.images import resize_to_width, validate_mime


def test_resize_preserves_aspect_ratio():
    img = Image.new("RGB", (1600, 1200), "red")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    resized, w, h = resize_to_width(buf.getvalue(), target_width=400)
    assert w == 400
    assert h == 300


def test_validate_mime_accepts_jpeg():
    img = Image.new("RGB", (10, 10))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    assert validate_mime(buf.getvalue()) == "image/jpeg"


def test_validate_mime_rejects_unknown():
    assert validate_mime(b"not an image") is None
