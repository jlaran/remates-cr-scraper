from unittest.mock import MagicMock, patch

from remates_scraper.common.storage import R2Storage


def test_r2_upload_uses_correct_bucket_and_key(monkeypatch):
    monkeypatch.setenv("R2_ACCOUNT_ID", "acct")
    monkeypatch.setenv("R2_ACCESS_KEY_ID", "key")
    monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "secret")
    monkeypatch.setenv("R2_BUCKET", "test-bucket")
    monkeypatch.setenv("R2_PUBLIC_URL", "https://cdn.example.com")

    mock_client = MagicMock()
    with patch("remates_scraper.common.storage.boto3.client", return_value=mock_client):
        storage = R2Storage()
        url = storage.upload(b"data", "listings/abc/1.jpg", content_type="image/jpeg")

    mock_client.put_object.assert_called_once_with(
        Bucket="test-bucket",
        Key="listings/abc/1.jpg",
        Body=b"data",
        ContentType="image/jpeg",
        CacheControl="public, max-age=31536000, immutable",
    )
    assert url == "https://cdn.example.com/listings/abc/1.jpg"
