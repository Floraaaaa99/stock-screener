"""Regenerate the trimmed real-data fixtures from the local SEC cache.

Usage: python tests/fixtures/extract_fixtures.py  (after `screener build` has populated pipeline/.cache)

Only revenue-concept facts are kept, which keeps the fixtures small while preserving the exact
SEC Company Facts structure.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from screener_pipeline import config
from screener_pipeline.sec.facts import REVENUE_CONCEPTS

HERE = Path(__file__).parent
COMPANIES = {"VRTX": "0000875320", "ALNY": "0001178670", "RARE": "0001515673", "NTLA": "0001652130",
             "SRPT": "0000873303"}
STATEMENTS = {"SRPT": "0001193125-26-335003"}


def main() -> None:
    out = HERE / "companyfacts"
    out.mkdir(exist_ok=True)
    for ticker, cik in COMPANIES.items():
        src = config.CACHE_DIR / "sec" / "companyfacts" / f"CIK{cik}.json"
        d = json.loads(src.read_text())
        gaap = d["facts"]["us-gaap"]
        trimmed = {
            "cik": d["cik"],
            "entityName": d["entityName"],
            "facts": {"us-gaap": {c: gaap[c] for c in REVENUE_CONCEPTS if c in gaap}},
        }
        (out / f"{ticker}.json").write_text(json.dumps(trimmed, separators=(",", ":")))
    sdir = HERE / "statements"
    sdir.mkdir(exist_ok=True)
    for ticker, accn in STATEMENTS.items():
        fdir = config.CACHE_DIR / "sec" / "filings" / accn
        for f in fdir.iterdir():
            shutil.copy(f, sdir / f"{ticker}-{accn}-{f.name}")


if __name__ == "__main__":
    main()
