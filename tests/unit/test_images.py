import io
from unittest.mock import patch

from PIL import Image

from remates_scraper.common.images import download, resize_to_width, validate_mime


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


def test_download_passes_referer():
    with patch("remates_scraper.common.images.httpx.get") as mock_get:
        mock_get.return_value.content = b"x"
        mock_get.return_value.raise_for_status = lambda: None
        download("https://example.com/img.jpg", referer="https://referer.example/")
        mock_get.assert_called_once()
        kwargs = mock_get.call_args.kwargs
        assert kwargs.get("headers", {}).get("Referer") == "https://referer.example/"


def test_download_no_referer_sends_empty_headers():
    with patch("remates_scraper.common.images.httpx.get") as mock_get:
        mock_get.return_value.content = b"x"
        mock_get.return_value.raise_for_status = lambda: None
        download("https://example.com/img.jpg")
        mock_get.assert_called_once()
        kwargs = mock_get.call_args.kwargs
        assert kwargs.get("headers", {}) == {}
