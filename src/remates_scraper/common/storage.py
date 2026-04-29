"""Cloudflare R2 storage helpers (S3-compatible)."""
from __future__ import annotations

import os
from typing import Final

import boto3


class R2Storage:
    def __init__(self) -> None:
        account_id = self._req("R2_ACCOUNT_ID")
        endpoint = f"https://{account_id}.r2.cloudflarestorage.com"
        self._bucket: Final[str] = self._req("R2_BUCKET")
        self._public_url: Final[str] = self._req("R2_PUBLIC_URL").rstrip("/")
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=self._req("R2_ACCESS_KEY_ID"),
            aws_secret_access_key=self._req("R2_SECRET_ACCESS_KEY"),
            region_name="auto",
        )

    @staticmethod
    def _req(name: str) -> str:
        v = os.environ.get(name)
        if not v:
            raise RuntimeError(f"{name} must be set in environment")
        return v

    def upload(self, data: bytes, key: str, content_type: str) -> str:
        self._client.put_object(
            Bucket=self._bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
            CacheControl="public, max-age=31536000, immutable",
        )
        return f"{self._public_url}/{key}"
