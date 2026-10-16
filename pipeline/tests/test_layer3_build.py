from __future__ import annotations

import json
from pathlib import Path

from helpers import companyfacts
from test_layer3_extract import _instant, _ytd_year

from screener_pipeline.cache import write_json_atomic
from screener_pipeline.layer3_build import write_layer3


def _dataset(tmp_path: Path) -> Path:
    data = tmp_path / "data"
    companies = data / "companies"
    companies.mkdir(parents=True)
    write_json_atomic(
        data / "screener.json",
        {
            "rows": [
                {
                    "ticker": "HEI",
                    "name": "HEICO Corporation",
                    "exchange": "NYSE",
                    "sicCode": "3724",
                    "sicIndustry": "3724 — Aircraft Engines",
                    "sicMajorGroup": "Transportation Equipment",
                    "ttmCurrent": 100,
                    "ttmPrevious": 80,
                    "ttmGrowth": 25,
                    "naReason": None,
                    "revenueCurrency": "USD",
                },
                {
                    "ticker": "HEI-A",
                    "name": "HEICO Corporation Class A",
                    "exchange": "NYSE",
                    "sicCode": "3724",
                    "sicIndustry": "3724 — Aircraft Engines",
                    "sicMajorGroup": "Transportation Equipment",
                    "ttmCurrent": 100,
                    "ttmPrevious": 80,
                    "ttmGrowth": 25,
                    "naReason": None,
                    "revenueCurrency": "USD",
                },
                {
                    "ticker": "JPM",
                    "name": "JPMorgan",
                    "exchange": "NYSE",
                    "sicCode": "6021",
                    "sicIndustry": "6021 — National Commercial Banks",
                    "sicMajorGroup": "Finance, Insurance, and Real Estate",
                    "ttmCurrent": 1,
                    "ttmPrevious": 1,
                    "ttmGrowth": 0,
                    "naReason": None,
                    "revenueCurrency": "USD",
                },
            ]
        },
    )
    write_json_atomic(
        data / "issuers.json",
        {"schemaVersion": 1, "byTicker": {"HEI": "0000046619", "HEI-A": "0000046619", "JPM": "0000019617"}},
    )
    write_json_atomic(data / "layer2.json", {"rows": [{"ticker": "HEI", "bucket": "passed"}], "counts": {"passed": 1}})
    return data


def test_write_layer3_groups_share_classes_and_does_not_score(tmp_path: Path):
    data = _dataset(tmp_path)
    facts = {
        "0000046619": companyfacts(
            {
                "NetCashProvidedByUsedInOperatingActivities": (
                    _ytd_year(2025, 10, 10, 10, 10, prefix="O") + _ytd_year(2024, 9, 9, 9, 9, prefix="P")
                ),
                "PaymentsToAcquirePropertyPlantAndEquipment": (
                    _ytd_year(2025, 2, 2, 2, 2, prefix="C") + _ytd_year(2024, 1, 1, 1, 1, prefix="D")
                ),
                "CashAndCashEquivalentsAtCarryingValue": [
                    _instant("2025-12-31", 50, "a", 2025, "FY", form="10-K")
                ],
            },
            cik=46619,
            name="HEICO CORPORATION",
        )
    }
    dest = tmp_path / "layer3.json"
    out = write_layer3(data, dest, companyfacts_by_cik=facts)
    assert out["scoring"] is None
    assert out["payload"] == "index"
    assert out["issuerFileTemplate"] == "layer3/cik/{cik}.json"
    by_cik = {r["cik"]: r for r in out["rows"]}
    hei = by_cik["0000046619"]
    assert set(hei["tickers"]) == {"HEI", "HEI-A"}
    assert hei["extractionStatus"] == "extracted"
    assert hei["verificationStatus"] == "company_facts_only"
    assert hei["modelApplicability"] == "applicable"
    assert hei["scoringStatus"] == "not_implemented"
    assert hei["inputCompleteness"] == "ready"
    assert hei["metrics"]["fcf"]["ttm"] == 32
    assert hei["scoring"] is None
    assert hei["layer1"]["revenueTtm"] == 100
    assert hei["layer1"]["source"] == "layer1_copy"
    written = json.loads(dest.read_text())
    assert written["rows"] == []
    assert written["counts"]["issuers"] == 2
    issuer = json.loads((dest.parent / "layer3" / "cik" / "0000046619.json").read_text())
    assert issuer["metrics"]["fcf"]["ttm"] == 32
    assert issuer["extractionStatus"] == "extracted"
    assert issuer["scoringStatus"] == "not_implemented"
    jpm = by_cik["0000019617"]
    assert jpm["extractionStatus"] == "pending_analysis"
    assert jpm["modelApplicability"] == "not_applicable"
    assert jpm["scoringStatus"] == "not_implemented"
    assert jpm["metrics"] is None
    # Layer 1 / Layer 2 artifacts are untouched.
    layer2 = json.loads((data / "layer2.json").read_text())
    assert layer2["counts"]["passed"] == 1
    screener = json.loads((data / "screener.json").read_text())
    assert screener["rows"][0]["ttmGrowth"] == 25


def test_write_layer3_without_facts_is_pending_analysis(tmp_path: Path):
    data = _dataset(tmp_path)
    out = write_layer3(data, tmp_path / "layer3.json")
    hei = next(r for r in out["rows"] if r["cik"] == "0000046619")
    assert hei["extractionStatus"] == "pending_analysis"
    assert hei["verificationStatus"] == "not_checked"
    assert hei["scoringStatus"] == "not_implemented"
    assert hei["metrics"] is None
    assert hei["reason"] == "layer3_concepts_not_in_compact_facts"


def test_public_metrics_drop_source_legs(tmp_path: Path):
    data = _dataset(tmp_path)
    facts = {
        "0000046619": companyfacts(
            {
                "NetCashProvidedByUsedInOperatingActivities": _ytd_year(2025, 1, 1, 1, 1, prefix="O")
                + _ytd_year(2024, 1, 1, 1, 1, prefix="P"),
                "PaymentsToAcquirePropertyPlantAndEquipment": _ytd_year(2025, 1, 1, 1, 1, prefix="C")
                + _ytd_year(2024, 1, 1, 1, 1, prefix="D"),
                "CashAndCashEquivalentsAtCarryingValue": [_instant("2025-12-31", 9, "a", 2025, "FY", form="10-K")],
            },
            cik=46619,
        )
    }
    dest = tmp_path / "layer3.json"
    out = write_layer3(data, dest, companyfacts_by_cik=facts)
    hei = next(r for r in out["rows"] if r["cik"] == "0000046619")
    q0 = hei["metrics"]["ocf"]["quarters"][0]
    assert "sources" not in q0
    assert q0["method"]
    assert q0["url"]
    disk = json.loads((dest.parent / "layer3" / "cik" / "0000046619.json").read_text())
    assert "sources" not in disk["metrics"]["ocf"]["quarters"][0]
