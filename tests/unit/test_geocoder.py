from remates_scraper.common.geocoder import normalize_province


def test_normalize_province_handles_variants():
    assert normalize_province("San Jose") == "San José"
    assert normalize_province("S.J.") == "San José"
    assert normalize_province("San José") == "San José"
    assert normalize_province("HEREDIA") == "Heredia"
    assert normalize_province("guanacaste") == "Guanacaste"


def test_normalize_province_returns_none_for_unknown():
    assert normalize_province("Florida") is None
