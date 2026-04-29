import pytest

from remates_scraper.common.db import build_dsn


def test_build_dsn_uses_env_var(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h:5432/db")
    assert build_dsn() == "postgresql://u:p@h:5432/db"


def test_build_dsn_raises_when_missing(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        build_dsn()
