from __future__ import annotations

import hashlib
import importlib.util
import json
import tarfile
from pathlib import Path

import pytest
from helpers import companyfacts
from test_layer3_extract import _instant, _ytd_year

from screener_pipeline import config
from screener_pipeline.cache import write_json_atomic
from screener_pipeline.cli import main
from screener_pipeline.layer3_build import (
    Layer3BuildError,
    plan_layer3_publish,
    publish_layer3,
    validate_layer3_publish,
    write_layer3,
)


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
    assert len(hei["metrics"]["fcf"]["quarters"]) == 8
    assert hei["metrics"]["inventory"]["status"] == "not_applicable"
    assert hei["schemaVersion"] == 3
    assert hei["scoring"] is None
    assert out["counts"]["metrics"]["ocf"]["extracted"] == 1
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


def test_write_layer3_without_facts_fails_and_preserves_existing(tmp_path: Path):
    data = _dataset(tmp_path)
    dest = tmp_path / "layer3.json"
    cik_dir = dest.parent / "layer3" / "cik"
    cik_dir.mkdir(parents=True)
    keep = {
        "cik": "0000046619",
        "extractionStatus": "extracted",
        "verificationStatus": "company_facts_only",
        "metrics": {"ocf": {"ttm": 99}},
    }
    (cik_dir / "0000046619.json").write_text(json.dumps(keep))
    with pytest.raises(Layer3BuildError, match="No Company Facts source"):
        write_layer3(data, dest)
    assert json.loads((cik_dir / "0000046619.json").read_text())["metrics"]["ocf"]["ttm"] == 99
    assert not dest.exists()


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


def _hei_facts() -> dict:
    return companyfacts(
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


def _extracted_stub(cik: str, marker: int) -> dict:
    return {
        "cik": cik,
        "extractionStatus": "extracted",
        "verificationStatus": "company_facts_only",
        "modelApplicability": "applicable",
        "scoringStatus": "not_implemented",
        "inputCompleteness": "ready",
        "metrics": {"ocf": {"ttm": marker, "status": "extracted"}},
        "scoring": None,
    }


def test_limit_and_ciks_do_not_wipe_other_extracted_files(tmp_path: Path):
    data = _dataset(tmp_path)
    dest = tmp_path / "layer3.json"
    cik_dir = dest.parent / "layer3" / "cik"
    cik_dir.mkdir(parents=True)
    (cik_dir / "0000046619.json").write_text(json.dumps(_extracted_stub("0000046619", 1)))
    (cik_dir / "0000019617.json").write_text(json.dumps(_extracted_stub("0000019617", 2)))
    out = write_layer3(
        data,
        dest,
        companyfacts_by_cik={"0000046619": _hei_facts()},
        ciks=["0000046619"],
    )
    assert out["mode"] == "incremental"
    assert out["updated"] == ["0000046619"]
    hei = json.loads((cik_dir / "0000046619.json").read_text())
    jpm = json.loads((cik_dir / "0000019617.json").read_text())
    assert hei["extractionStatus"] == "extracted"
    assert hei["metrics"]["fcf"]["ttm"] == 32
    assert jpm["metrics"]["ocf"]["ttm"] == 2
    assert jpm["extractionStatus"] == "extracted"
    assert {p.name for p in cik_dir.glob("*.json")} == {"0000046619.json", "0000019617.json"}

    limited = write_layer3(
        data,
        dest,
        companyfacts_by_cik={"0000046619": _hei_facts()},
        limit=1,
    )
    # Sorted CIKs start with JPM; limit=1 must not delete HEI.
    assert "0000046619.json" in {p.name for p in cik_dir.glob("*.json")}
    assert json.loads((cik_dir / "0000046619.json").read_text())["extractionStatus"] == "extracted"
    assert limited["mode"] == "incremental"


def test_incremental_keeps_extracted_when_new_payload_would_be_pending(tmp_path: Path):
    data = _dataset(tmp_path)
    dest = tmp_path / "layer3.json"
    cik_dir = dest.parent / "layer3" / "cik"
    cik_dir.mkdir(parents=True)
    (cik_dir / "0000046619.json").write_text(json.dumps(_extracted_stub("0000046619", 7)))
    out = write_layer3(
        data,
        dest,
        companyfacts_by_cik={"0000019617": companyfacts({}, cik=19617)},
        ciks=["0000046619"],
    )
    assert "0000046619" in out["preserved"]
    kept = json.loads((cik_dir / "0000046619.json").read_text())
    assert kept["metrics"]["ocf"]["ttm"] == 7
    assert kept["extractionStatus"] == "extracted"


def test_full_rebuild_stays_in_staging_until_publish(tmp_path: Path):
    data = _dataset(tmp_path)
    dest = tmp_path / "layer3.json"
    live_dir = dest.parent / "layer3" / "cik"
    live_dir.mkdir(parents=True)
    (live_dir / "0000046619.json").write_text(json.dumps(_extracted_stub("0000046619", 3)))
    dest.write_text(json.dumps({"payload": "index", "rows": []}))
    staging = tmp_path / "stage"
    out = write_layer3(
        data,
        dest,
        companyfacts_by_cik={"0000046619": _hei_facts()},
        mode="full",
        staging_dir=staging,
        publish=False,
    )
    assert out["published"] is False
    assert json.loads(dest.read_text())["payload"] == "index"
    assert json.loads((live_dir / "0000046619.json").read_text())["metrics"]["ocf"]["ttm"] == 3
    staged = json.loads((staging / "layer3" / "cik" / "0000046619.json").read_text())
    assert staged["metrics"]["fcf"]["ttm"] == 32

    published = write_layer3(
        data,
        dest,
        companyfacts_by_cik={"0000046619": _hei_facts()},
        mode="full",
        staging_dir=staging,
        publish=True,
    )
    assert published["published"] is True
    live = json.loads((live_dir / "0000046619.json").read_text())
    assert live["metrics"]["fcf"]["ttm"] == 32
    assert (tmp_path / published["publish"]["rollbackDir"]).exists()


def test_publish_blocks_extracted_replaced_by_pending_and_rolls_back(tmp_path: Path):
    live_dest = tmp_path / "layer3.json"
    live_dir = tmp_path / "layer3" / "cik"
    live_dir.mkdir(parents=True)
    live_dest.write_text(json.dumps({"payload": "index"}))
    (live_dir / "0000046619.json").write_text(json.dumps(_extracted_stub("0000046619", 4)))
    (live_dir / "0000999999.json").write_text(json.dumps(_extracted_stub("0000999999", 8)))

    staging_dest = tmp_path / "stage" / "layer3.json"
    staging_dir = tmp_path / "stage" / "layer3" / "cik"
    staging_dir.mkdir(parents=True)
    staging_dest.write_text(json.dumps({"payload": "index", "rows": []}))
    (staging_dir / "0000046619.json").write_text(
        json.dumps(
            {
                "cik": "0000046619",
                "extractionStatus": "pending_analysis",
                "metrics": None,
            }
        )
    )
    with pytest.raises(Layer3BuildError, match="pending_analysis"):
        publish_layer3(live_dest, staging_dest)
    assert json.loads((live_dir / "0000046619.json").read_text())["metrics"]["ocf"]["ttm"] == 4

    # Valid staging, then fail while writing the live index and restore rollback.
    (staging_dir / "0000046619.json").write_text(json.dumps(_extracted_stub("0000046619", 5)))
    (staging_dir / "0000999999.json").write_text(json.dumps(_extracted_stub("0000999999", 8)))
    from screener_pipeline import layer3_build as build_mod

    real = build_mod.write_json_atomic
    writes = {"live_index": 0}

    def boom(path, payload, **kwargs):
        if Path(path) == live_dest:
            writes["live_index"] += 1
            if writes["live_index"] == 1:
                raise OSError("disk full")
        return real(path, payload, **kwargs)

    build_mod.write_json_atomic = boom
    try:
        with pytest.raises(OSError, match="disk full"):
            publish_layer3(live_dest, staging_dest, rollback_dir=tmp_path / "rb")
    finally:
        build_mod.write_json_atomic = real
    assert json.loads((live_dir / "0000046619.json").read_text())["metrics"]["ocf"]["ttm"] == 4
    assert json.loads(live_dest.read_text())["payload"] == "index"


def test_write_layer3_refuses_live_dest_without_write_live(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    data = _dataset(tmp_path)
    dest = tmp_path / "layer3.json"
    monkeypatch.setattr("screener_pipeline.layer3_build.live_layer3_dest", lambda: dest)
    with pytest.raises(Layer3BuildError, match="write_live"):
        write_layer3(data, dest, companyfacts_by_cik={"0000046619": _hei_facts()})
    assert not dest.exists()


def test_cli_layer3_ciks_writes_sidecar_not_production(tmp_path: Path):
    data = _dataset(tmp_path)
    facts_dir = tmp_path / "facts"
    facts_dir.mkdir()
    (facts_dir / "0000046619.json").write_text(json.dumps(_hei_facts()))
    dest = tmp_path / "sidecar" / "layer3.json"
    live = config.REPO_ROOT / "web" / "public" / "data" / "layer3" / "cik" / "0000046619.json"
    before = live.read_bytes()
    code = main(
        [
            "layer3",
            "--data-dir",
            str(data),
            "--output",
            str(dest),
            "--facts-dir",
            str(facts_dir),
            "--ciks",
            "0000046619",
            "--mode",
            "incremental",
        ]
    )
    assert code == 0
    assert (dest.parent / "layer3" / "cik" / "0000046619.json").exists()
    assert live.read_bytes() == before


def test_write_layer3_keeps_canonical_cik_when_facts_cik_is_zero(tmp_path: Path):
    data = tmp_path / "data"
    (data / "companies").mkdir(parents=True)
    write_json_atomic(
        data / "screener.json",
        {"rows": [{"ticker": "ZSTK", "name": "ZeroStack Corp.", "sicCode": "7372"}]},
    )
    write_json_atomic(data / "issuers.json", {"schemaVersion": 1, "byTicker": {"ZSTK": "0001790169"}})
    dest = tmp_path / "layer3.json"
    facts = companyfacts(
        {
            "NetCashProvidedByUsedInOperatingActivities": (
                _ytd_year(2025, 1, 1, 1, 1, prefix="O") + _ytd_year(2024, 1, 1, 1, 1, prefix="P")
            ),
            "CashAndCashEquivalentsAtCarryingValue": [
                _instant("2025-12-31", 10, "a", 2025, "FY", form="10-K")
            ],
        },
        cik=0,
        name="ZeroStack Corp.",
    )
    out = write_layer3(data, dest, companyfacts_by_cik={"0001790169": facts})
    path = dest.parent / "layer3" / "cik" / "0001790169.json"
    assert path.exists()
    payload = json.loads(path.read_text())
    assert payload["cik"] == "0001790169"
    assert payload["displayTicker"] == "ZSTK"
    assert payload["companyFactsCik"] == "0000000000"
    assert "company_facts_cik_unusable" in (payload.get("flags") or [])
    assert {r["cik"] for r in out["rows"]} == {"0001790169"}
    assert not (dest.parent / "layer3" / "cik" / "0000000000.json").exists()


def test_publish_blocks_identity_errors_and_unexpected_deletes(tmp_path: Path):
    live_dest = tmp_path / "layer3.json"
    live_dir = tmp_path / "layer3" / "cik"
    live_dir.mkdir(parents=True)
    live_dest.write_text(json.dumps({"payload": "index"}))
    (live_dir / "0000000000.json").write_text(
        json.dumps({**_extracted_stub("0000000000", 1), "displayTicker": "ZSTK"})
    )
    (live_dir / "0000046619.json").write_text(json.dumps(_extracted_stub("0000046619", 2)))

    staging_dest = tmp_path / "stage" / "layer3.json"
    staging_dir = tmp_path / "stage" / "layer3" / "cik"
    staging_dir.mkdir(parents=True)
    staging_dest.write_text(json.dumps({"payload": "index"}))
    (staging_dir / "0001790169.json").write_text(
        json.dumps({**_extracted_stub("0001790169", 3), "displayTicker": "ZSTK"})
    )
    (staging_dir / "0000046619.json").write_text(json.dumps(_extracted_stub("0000046619", 2)))
    (staging_dir / "0000759828.json").write_text(
        json.dumps({**_extracted_stub("0000000000", 4), "displayTicker": "JHI"})
    )

    plan = plan_layer3_publish(live_dir, staging_dir)
    joined = " ".join(plan["errors"])
    assert plan["migrations"] == [
        {
            "legacyFile": "0000000000.json",
            "legacyCik": "0000000000",
            "canonicalFile": "0001790169.json",
            "canonicalCik": "0001790169",
            "ticker": "ZSTK",
            "action": "remap_delete",
        }
    ]
    assert "0000000000.json has zero or invalid cik" not in joined
    assert "0000000000.json would be deleted; ticker ZSTK remapped to 0001790169.json" not in joined
    assert "0000759828.json has zero or invalid cik" in joined
    with pytest.raises(Layer3BuildError, match="publish blocked"):
        publish_layer3(live_dest, staging_dest)
    assert json.loads((live_dir / "0000000000.json").read_text())["metrics"]["ocf"]["ttm"] == 1


def test_approved_zstk_cik_migration_is_classified_not_an_error(tmp_path: Path):
    live_dest = tmp_path / "layer3.json"
    live_dir = tmp_path / "layer3" / "cik"
    live_dir.mkdir(parents=True)
    live_dest.write_text(json.dumps({"payload": "index"}))
    (live_dir / "0000000000.json").write_text(
        json.dumps({**_extracted_stub("0000000000", 1), "displayTicker": "ZSTK", "tickers": ["ZSTK"]})
    )
    (live_dir / "0000046619.json").write_text(json.dumps(_extracted_stub("0000046619", 2)))

    staging_dest = tmp_path / "stage" / "layer3.json"
    staging_dir = tmp_path / "stage" / "layer3" / "cik"
    staging_dir.mkdir(parents=True)
    staging_dest.write_text(json.dumps({"payload": "index"}))
    (staging_dir / "0001790169.json").write_text(
        json.dumps({**_extracted_stub("0001790169", 3), "displayTicker": "ZSTK", "tickers": ["ZSTK"]})
    )
    (staging_dir / "0000046619.json").write_text(json.dumps(_extracted_stub("0000046619", 5)))
    (staging_dir / "0000759828.json").write_text(
        json.dumps({**_extracted_stub("0000759828", 4), "displayTicker": "JHI", "tickers": ["JHI"]})
    )

    plan = plan_layer3_publish(live_dir, staging_dir)
    assert plan["ok"] is True
    assert plan["errors"] == []
    assert plan["added"] == ["0000759828.json", "0001790169.json"]
    assert plan["removed"] == ["0000000000.json"]
    assert plan["replaced"] == ["0000046619.json"]
    assert plan["migrations"][0]["ticker"] == "ZSTK"
    assert validate_layer3_publish(live_dir, staging_dir) == []

    published = publish_layer3(live_dest, staging_dest, rollback_dir=tmp_path / "rb")
    assert published["published"] is True
    assert not (live_dir / "0000000000.json").exists()
    assert json.loads((live_dir / "0001790169.json").read_text())["metrics"]["ocf"]["ttm"] == 3
    assert json.loads((tmp_path / "rb" / "cik" / "0000000000.json").read_text())["metrics"]["ocf"]["ttm"] == 1


def test_publish_still_blocks_unapproved_remap_and_wrong_zero_cik_occupant(tmp_path: Path):
    live_dir = tmp_path / "live"
    staging_dir = tmp_path / "stage"
    live_dir.mkdir()
    staging_dir.mkdir()
    (live_dir / "0000046619.json").write_text(
        json.dumps({**_extracted_stub("0000046619", 1), "displayTicker": "HEI"})
    )
    (staging_dir / "0000999999.json").write_text(
        json.dumps({**_extracted_stub("0000999999", 2), "displayTicker": "HEI"})
    )
    errors = validate_layer3_publish(live_dir, staging_dir)
    assert any("0000046619.json would be deleted; ticker HEI remapped" in e for e in errors)

    live2 = tmp_path / "live2"
    stage2 = tmp_path / "stage2"
    live2.mkdir()
    stage2.mkdir()
    (live2 / "0000000000.json").write_text(
        json.dumps({**_extracted_stub("0000000000", 1), "displayTicker": "JHI", "tickers": ["JHI"]})
    )
    (stage2 / "0000759828.json").write_text(
        json.dumps({**_extracted_stub("0000759828", 2), "displayTicker": "JHI", "tickers": ["JHI"]})
    )
    joined = " ".join(validate_layer3_publish(live2, stage2))
    assert "0000000000.json has zero or invalid cik" in joined
    assert "0000000000.json would be deleted; ticker JHI remapped to 0000759828.json" in joined


def test_cli_publish_dry_run_does_not_write(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    live_dest = tmp_path / "layer3.json"
    live_dir = tmp_path / "layer3" / "cik"
    live_dir.mkdir(parents=True)
    live_dest.write_text(json.dumps({"payload": "index"}))
    (live_dir / "0000000000.json").write_text(
        json.dumps({**_extracted_stub("0000000000", 1), "displayTicker": "ZSTK", "tickers": ["ZSTK"]})
    )
    staging_root = tmp_path / "stage"
    staging_dir = staging_root / "layer3" / "cik"
    staging_dir.mkdir(parents=True)
    (staging_root / "layer3.json").write_text(json.dumps({"payload": "index"}))
    (staging_dir / "0001790169.json").write_text(
        json.dumps({**_extracted_stub("0001790169", 3), "displayTicker": "ZSTK", "tickers": ["ZSTK"]})
    )

    code = main(
        [
            "layer3",
            "--data-dir",
            str(tmp_path / "data"),
            "--output",
            str(live_dest),
            "--staging-dir",
            str(staging_root),
            "--publish-dry-run",
        ]
    )
    captured = capsys.readouterr()
    assert code == 0
    plan = json.loads(captured.out)
    assert plan["published"] is False
    assert plan["ok"] is True
    assert plan["added"] == ["0001790169.json"]
    assert plan["removed"] == ["0000000000.json"]
    assert (live_dir / "0000000000.json").exists()
    assert not (live_dir / "0001790169.json").exists()
    assert main(["layer3", "--output", str(live_dest), "--publish", "--publish-dry-run"]) == 2


def test_publish_blocks_duplicate_payload_ciks(tmp_path: Path):
    live_dir = tmp_path / "live"
    live_dir.mkdir()
    staging_dir = tmp_path / "stage"
    staging_dir.mkdir()
    (staging_dir / "0000046619.json").write_text(json.dumps(_extracted_stub("0000046619", 1)))
    (staging_dir / "0000789019.json").write_text(json.dumps(_extracted_stub("0000046619", 2)))
    errors = validate_layer3_publish(live_dir, staging_dir)
    assert any("duplicate payload cik 0000046619" in e for e in errors)


def _load_restore_layer3_v3():
    path = Path(__file__).resolve().parents[1] / "scripts" / "restore_layer3_v3.py"
    spec = importlib.util.spec_from_file_location("restore_layer3_v3", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_restore_layer3_v3_removes_v4_only_files(tmp_path: Path):
    module = _load_restore_layer3_v3()
    data = tmp_path / "data"
    cik = data / "layer3" / "cik"
    cik.mkdir(parents=True)
    (cik / "0001790169.json").write_text(json.dumps({"cik": "0001790169"}))
    (cik / "0000759828.json").write_text(json.dumps({"cik": "0000759828"}))
    (data / "layer3.json").write_text(json.dumps({"schemaVersion": 3, "extractionVersion": 4}))

    v3 = tmp_path / "v3src"
    (v3 / "layer3" / "cik").mkdir(parents=True)
    (v3 / "layer3.json").write_text(json.dumps({"schemaVersion": 2, "extractionVersion": 3}) + "\n")
    zero = v3 / "layer3" / "cik" / "0000000000.json"
    zero.write_text(json.dumps({"cik": "0000000000", "displayTicker": "ZSTK"}))
    archive = tmp_path / "v3.tar.gz"
    with tarfile.open(archive, "w:gz") as tf:
        tf.add(v3 / "layer3.json", arcname="layer3.json")
        tf.add(zero, arcname="layer3/cik/0000000000.json")

    digest = hashlib.sha256()
    digest.update(b"0000000000.json\0")
    digest.update(str(zero.stat().st_size).encode())
    digest.update(b"\n")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps({"issuerFiles": 1, "nameSizeFingerprint": digest.hexdigest()[:16]})
    )

    report = module.restore_layer3_v3(data, archive, manifest=manifest)
    assert report["ok"] is True
    assert report["issuerFiles"] == 1
    assert (cik / "0000000000.json").exists()
    assert not (cik / "0001790169.json").exists()
    assert not (cik / "0000759828.json").exists()
    assert json.loads((data / "layer3.json").read_text())["schemaVersion"] == 2
