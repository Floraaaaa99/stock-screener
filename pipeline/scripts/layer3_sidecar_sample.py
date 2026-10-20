#!/usr/bin/env python3
"""Extract HEI / MSFT / NVDA into a sidecar directory. Never writes production JSON.

Usage (from repo, after `pip install -e pipeline`):

    python pipeline/scripts/layer3_sidecar_sample.py --output /tmp/layer3-sidecar

Looks for Company Facts in this order:
1. --facts-dir / --facts-zip
2. pipeline/.cache/sec/bulk/companyfacts.zip
3. per-CIK API files already cached under pipeline/.cache/sec/companyfacts
4. SEC Company Facts API, only when SEC_USER_AGENT is set
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from screener_pipeline import config
from screener_pipeline.cache import read_json
from screener_pipeline.layer3_build import (
    Layer3BuildError,
    compare_layer3_issuers,
    default_facts_zip,
    issuer_dir_for,
    write_layer3,
)

SAMPLE_CIKS = ("0000046619", "0000789019", "0001045810")
LIVE_DEST = config.REPO_ROOT / "web" / "public" / "data" / "layer3.json"
LIVE_CIK_DIR = issuer_dir_for(LIVE_DEST)


def _load_cached_api_facts(cik: str) -> dict | None:
    path = config.CACHE_DIR / "sec" / "companyfacts" / f"CIK{cik}.json"
    if path.exists():
        return json.loads(path.read_text())
    return None


def _fetch_sec_facts(cik: str) -> dict | None:
    from screener_pipeline.sec.client import SecClient

    return SecClient().companyfacts(cik)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output", default="/tmp/layer3-sidecar")
    ap.add_argument("--data-dir", default=str(config.REPO_ROOT / "web" / "public" / "data"))
    ap.add_argument("--facts-zip")
    ap.add_argument("--facts-dir")
    ap.add_argument("--report", help="Write a JSON comparison report")
    args = ap.parse_args(argv)

    out_root = Path(args.output)
    dest = out_root / "layer3.json" if out_root.suffix != ".json" else out_root
    if dest.resolve() == LIVE_DEST.resolve():
        print("error: sidecar output must not be the production layer3.json", file=sys.stderr)
        return 2

    facts_zip = Path(args.facts_zip) if args.facts_zip else default_facts_zip()
    facts_dir = Path(args.facts_dir) if args.facts_dir else None
    inline: dict[str, dict] = {}
    source = None
    if facts_zip and facts_zip.exists():
        source = f"zip:{facts_zip}"
    elif facts_dir and facts_dir.exists():
        facts_zip = None
        source = f"dir:{facts_dir}"
    else:
        facts_zip = None
        for cik in SAMPLE_CIKS:
            cached = _load_cached_api_facts(cik)
            if cached:
                inline[cik] = cached
        if inline:
            source = "cached-per-cik-api"
        elif os.environ.get("SEC_USER_AGENT", "").strip():
            try:
                for cik in SAMPLE_CIKS:
                    raw = _fetch_sec_facts(cik)
                    if raw:
                        inline[cik] = raw
            except config.ConfigError as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 2
            source = "sec-api" if inline else None
        else:
            print(
                "blocked: no companyfacts.zip, no facts dir, no cached per-CIK files, "
                "and SEC_USER_AGENT is unset. Production issuer files were not modified.",
                file=sys.stderr,
            )
            return 3

    staging_dir = dest.parent / "staging"
    try:
        written = write_layer3(
            Path(args.data_dir),
            dest,
            companyfacts_by_cik=inline or None,
            facts_dir=facts_dir,
            facts_zip=facts_zip,
            ciks=list(SAMPLE_CIKS),
            mode="full",
            staging_dir=staging_dir,
            publish=False,
            write_live=False,
        )
    except Layer3BuildError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    staging_cik = issuer_dir_for(Path(written["stagingDest"]))
    rows = []
    for cik in SAMPLE_CIKS:
        previous = read_json(LIVE_CIK_DIR / f"{cik}.json") or {}
        current = read_json(staging_cik / f"{cik}.json") or {}
        rows.append(compare_layer3_issuers(previous, current))

    report = {
        "source": source,
        "sidecarDest": str(dest),
        "stagingDest": written.get("stagingDest"),
        "productionUntouched": True,
        "published": written.get("published"),
        "rows": rows,
    }
    text = json.dumps(report, indent=2)
    print(text)
    if args.report:
        Path(args.report).write_text(text + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
