from __future__ import annotations

import json
import zipfile
from pathlib import Path

from helpers import FIXTURES

from screener_pipeline.cache import canonical_hash
from screener_pipeline.sec.bulk import extract_compact_facts, zip_member
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
