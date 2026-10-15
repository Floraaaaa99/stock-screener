from __future__ import annotations

from screener_pipeline.output import SCHEMA_VERSION, screener_row, sort_screener_rows
from screener_pipeline.sec.sic import SicInfo


def test_schema_version_is_sec_only():
    assert SCHEMA_VERSION == 2


def test_screener_row_has_sic_not_yahoo_fields():
    row = screener_row(
        {
            "ticker": "VRTX",
            "name": "Vertex",
            "exchange": "NASDAQ",
            "securityType": "common",
            "sic": SicInfo(
                "2834",
                "Pharmaceutical Preparations",
                "Chemicals and Allied Products",
                "2834 — Pharmaceutical Preparations",
            ).to_dict(),
            "ttm": {"current": 1.0, "previous": 0.5, "growthPct": 100.0, "reason": None, "currency": "USD"},
            "revenue": {"currency": "USD", "quarters": []},
        }
    )
    assert row["sicCode"] == "2834"
    assert row["sicIndustry"].startswith("2834")
    assert row["revenueCurrency"] == "USD"
    assert "sector" not in row
    assert "industry" not in row
    assert "marketCap" not in row
    assert "price" not in row


def test_sort_ttm_growth_desc_na_last():
    rows = [
        {"ticker": "AAA", "ttmGrowth": -3},
        {"ticker": "BBB", "ttmGrowth": 12},
        {"ticker": "CCC", "ttmGrowth": None},
        {"ticker": "DDD", "ttmGrowth": 0},
    ]
    assert [r["ticker"] for r in sort_screener_rows(rows)] == ["BBB", "DDD", "AAA", "CCC"]
