"""Postgres connection helpers for the scraper."""
from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator

import psycopg
from psycopg.rows import dict_row


def build_dsn() -> str:
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        raise RuntimeError("DATABASE_URL must be set in environment")
    return dsn


@contextmanager
def connect() -> Iterator[psycopg.Connection]:  # type: ignore[type-arg]
    """Yield a Postgres connection with autocommit off and dict rows."""
    with psycopg.connect(build_dsn(), row_factory=dict_row) as conn:
        yield conn
