from __future__ import annotations

import json
import zipfile
from pathlib import Path

from helpers import FIXTURES

from screener_pipeline.cache import canonical_hash
from screener_pipeline.sec.bulk import extract_compact_facts, extract_compact_sic, zip_member
from screener_pipeline.sec.facts import extract_revenue_facts, revenue_facts_from_compact


def test_extract_compact_facts_from_zip(tmp_path: Path):
    raw = json.loads((FIXTURES / "companyfacts" / "VRTX.json").read_text())
    cik = str(raw["cik"]).zfill(10)
    zpath = tmp_path / "companyfacts.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr(zip_member(cik), json.dumps(raw))
        zf.writestr(zip_member("0000000001"), json.dumps({"cik": 1, "entityName": "Nope", "facts": {}}))

    facts_dir = tmp_path / "facts"
    hashes = extract_compact_facts(zpath, [cik, "0000000999"], facts_dir)
    assert cik in hashes
    assert "0000000999" not in hashes
    compact = json.loads((facts_dir / f"{cik}.json").read_text())
    rf = revenue_facts_from_compact(compact)
    original = extract_revenue_facts(raw)
    assert rf.cik == original.cik
    assert set(rf.by_concept) == set(original.by_concept)
    assert hashes[cik] == canonical_hash(compact)
    # Second run keeps the file (no force)
    again = extract_compact_facts(zpath, [cik], facts_dir)
    assert again[cik] == hashes[cik]


def test_extract_compact_sic_from_zip(tmp_path: Path):
    cik = "0000875320"
    zpath = tmp_path / "submissions.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr(
            f"nested/{zip_member(cik)}",
            json.dumps({
                "sic": "2834",
                "sicDescription": "Pharmaceutical Preparations",
                "filings": {
                    "recent": {
                        "form": ["10-Q"],
                        "filingDate": ["2026-07-28"],
                        "reportDate": ["2026-06-30"],
                        "accessionNumber": ["0000000000-26-000001"],
                    }
                },
            }),
        )
        zf.writestr(zip_member("0000000001"), json.dumps({"sic": "", "sicDescription": ""}))

    sic_dir = tmp_path / "sic"
    periodic_dir = tmp_path / "periodic"
    hashes = extract_compact_sic(zpath, [cik, "0000000999"], sic_dir, periodic_dir=periodic_dir)
    assert cik in hashes
    assert "0000000999" not in hashes
    payload = json.loads((sic_dir / f"{cik}.json").read_text())
    assert payload["code"] == "2834"
    assert payload["majorGroup"] == "Chemicals and Allied Products"
    assert payload["label"] == "Pharmaceutical Preparations — 2834"
    periodic = json.loads((periodic_dir / f"{cik}.json").read_text())
    assert periodic["filings"][0]["accn"] == "0000000000-26-000001"
    assert periodic["filings"][0]["reportDate"] == "2026-06-30"
