from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import Counter
from pathlib import Path

from . import config
from .build import DatasetError, IncompleteRun, build
from .cache import read_json
from .gate import evaluate_gate
from .report import write_validation_report
from .sec.client import SecClient
from .sec.edgar import facts_may_lag, freshness_row, newer_filings
from .sec.store import PeriodicStore, SicStore
from .state import pack_state, read_sidecar_sha256, unpack_state


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="screener", description="U.S. Stock Screener data pipeline")
    ap.add_argument("-v", "--verbose", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="Build the static JSON dataset")
    b.add_argument("--universe", default="sample:biotech20", help="sample:<name> or full")
    b.add_argument("--offline", action="store_true", help="Use cached downloads only")
    b.add_argument("--no-verify", action="store_true", help="Skip per-quarter checks against filing statements")
    b.add_argument(
        "--write-live",
        action="store_true",
        help="Write a full-universe dataset over web/public/data only if the publish gate passes",
    )
    b.add_argument("--report", help="Write a validation report (Markdown) to this path")
    b.add_argument("--limit", type=int, help="Process only the first N listings (partial; cannot be published as full)")
    b.add_argument("--time-budget-hours", type=float, help="Stop and save state after this many hours")
    b.add_argument("--no-resume", action="store_true", help="Ignore previous progress.json")
    b.add_argument("--no-bulk", action="store_true", help="Do not use companyfacts.zip (per-CIK API only)")
    b.add_argument("--output-dir", help="Override dataset output directory")
    b.add_argument("--state-dir", help="Override compact state directory")

    sub.add_parser("universe", help="Print NASDAQ Trader universe statistics")
    sub.add_parser("estimate", help="Print the SEC request and runtime estimate")

    p = sub.add_parser("pack-state", help="Pack compact SEC state into a checksummed archive")
    p.add_argument("--state-dir", default=str(config.STATE_DIR))
    p.add_argument("--dest", required=True, help="Path of the .tar.gz to write")

    u = sub.add_parser("unpack-state", help="Verify and unpack a state archive")
    u.add_argument("--archive", required=True)
    u.add_argument("--dest", required=True)
    u.add_argument("--sha256-file", help="Sidecar checksum file")

    g = sub.add_parser("gate", help="Check whether a dataset may be published")
    g.add_argument("--meta", required=True, help="Path to meta.json")
    g.add_argument("--baseline", help="Previous complete meta.json")
    g.add_argument("--publish", action="store_true", help="Require a complete full-universe dataset")

    f = sub.add_parser(
        "freshness",
        help="Compare a built dataset's latest quarters with EDGAR 10-Q/10-K submissions",
    )
    f.add_argument("--data-dir", required=True, help="Directory containing companies/*.json and meta.json")
    f.add_argument("--state-dir", help="Compact state (periodic filings cache)")
    f.add_argument("--offline", action="store_true", help="Do not refresh submissions from EDGAR")
    f.add_argument(
        "--refresh-lagging",
        action="store_true",
        help="Re-fetch EDGAR submissions when Company Facts look past the 10-Q window",
    )

    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    try:
        if args.cmd == "build":
            budget = args.time_budget_hours * 3600 if args.time_budget_hours is not None else None
            try:
                meta = build(
                    args.universe,
                    offline=args.offline,
                    verify_quarters=not args.no_verify,
                    output_dir=Path(args.output_dir) if args.output_dir else None,
                    state_dir=Path(args.state_dir) if args.state_dir else None,
                    limit=args.limit,
                    time_budget_s=budget,
                    resume=not args.no_resume,
                    use_bulk=False if args.no_bulk else None,
                    write_live=args.write_live,
                )
            except IncompleteRun as exc:
                print(f"incomplete: {exc}", file=sys.stderr)
                return 3
            print(json.dumps(
                {"coverage": meta["coverage"], "run": meta.get("run"), "gate": meta.get("gate")},
                indent=2,
            ))
            if args.report:
                out = Path(args.output_dir) if args.output_dir else config.OUTPUT_DIR
                if (meta.get("run") or {}).get("publishedTo"):
                    out = Path(meta["run"]["publishedTo"])
                write_validation_report(out, args.report)
                print(f"validation report: {args.report}")
        elif args.cmd == "universe":
            from .universe.fetch import load_universe

            listings, exclusions, times = load_universe()
            print(json.dumps({
                "eligible": len(listings),
                "byExchange": Counter(x.exchange for x in listings),
                "bySecurityType": Counter(x.security_type for x in listings),
                "excluded": Counter(e.reason for e in exclusions),
                "fileCreated": times,
            }, indent=2, default=dict))
        elif args.cmd == "estimate":
            print(json.dumps(request_estimate(), indent=2))
        elif args.cmd == "pack-state":
            archive, sidecar, manifest = pack_state(Path(args.state_dir), Path(args.dest))
            print(json.dumps({"archive": str(archive), "sha256": sidecar.read_text().split()[0],
                              "fileCount": manifest["fileCount"]}, indent=2))
        elif args.cmd == "unpack-state":
            expected = read_sidecar_sha256(Path(args.sha256_file)) if args.sha256_file else None
            manifest = unpack_state(Path(args.archive), Path(args.dest), expected_sha256=expected)
            print(json.dumps({"fileCount": manifest["fileCount"], "version": manifest["version"]}, indent=2))
        elif args.cmd == "gate":
            meta = read_json(Path(args.meta))
            baseline = read_json(Path(args.baseline)) if args.baseline else None
            result = evaluate_gate(meta, baseline, publish=args.publish)
            print(json.dumps(result.to_dict(), indent=2))
            return 0 if result.ok else 2
        elif args.cmd == "freshness":
            from datetime import date

            report = run_freshness(
                Path(args.data_dir),
                state_dir=Path(args.state_dir) if args.state_dir else None,
                offline=args.offline,
                refresh_lagging=args.refresh_lagging,
                as_of=date.today(),
            )
            print(json.dumps(report, indent=2))
            return 0 if report.get("lagging", 0) == 0 else 2
    except (DatasetError, config.ConfigError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


def request_estimate() -> dict:
    """Documented estimate: Stage 1 measured 12 filings × 2 files for each domestic company."""
    eligible = 5593
    domestic_share = 20 / 22  # Stage 1: 2 of 22 were foreign filers
    domestic = round(eligible * domestic_share)
    filings_per = 12
    files_per_filing = 2  # FilingSummary.xml + one R*.htm
    statement_requests = domestic * filings_per * files_per_filing
    ticker_map = 1
    companyfacts_api = eligible  # avoided by the bulk zip
    per_cik_total = ticker_map + companyfacts_api + statement_requests
    rps = config.SEC_MAX_RPS
    return {
        "eligibleListingsApprox": eligible,
        "stage1": {
            "listings": 22,
            "foreignFilers": 2,
            "filingsWithStatements": 240,
            "filesPerFiling": files_per_filing,
            "companyfactsApiCalls": 22,
        },
        "fullUniverseWithoutBulk": {
            "companyfactsApiCalls": companyfacts_api,
            "statementRequests": statement_requests,
            "totalSecRequests": per_cik_total,
            "hoursAtMaxRps": round(per_cik_total / rps / 3600, 2),
        },
        "fullUniverseWithBulk": {
            "companyfactsZip": {"requests": 1, "bytesApprox": 1_410_000_000},
            "submissionsZip": {"requests": 1, "bytesApprox": 1_570_000_000},
            "tickerMap": ticker_map,
            "statementRequestsFirstRun": statement_requests,
            "totalSecRequestsFirstRun": ticker_map + 2 + statement_requests,
            "hoursAtMaxRpsFirstRun": round((ticker_map + 2 + statement_requests) / rps / 3600, 2),
            "hoursAtMaxRpsWeekly": "0.2–1.5 depending on how many new accessions appear",
        },
        "notes": [
            "The ~125,000 figure is companyfacts API (≈5,600) plus ~12 filings × 2 files × ~4,900 domestic issuers.",
            "The bulk zips remove the companyfacts and submissions API calls; statement fetches remain until cached.",
            "A 5-hour budget leaves headroom under GitHub's 6-hour job limit; incomplete runs exit 3.",
            "Yahoo Finance is not used. Industry comes from SEC SIC; the dataset has no price or market cap.",
            "When Company Facts lag a 10-Q/10-K already on EDGAR, the filing's official income statement is used.",
        ],
    }


def run_freshness(
    data_dir: Path,
    *,
    state_dir: Path | None = None,
    offline: bool = False,
    refresh_lagging: bool = False,
    as_of=None,
) -> dict:
    """Scan company JSON against EDGAR submissions. Does not write live Pages data."""
    from datetime import date

    as_of = as_of or date.today()
    companies_dir = data_dir / "companies"
    if not companies_dir.exists():
        raise DatasetError(f"No companies directory in {data_dir}")
    state_dir = state_dir or config.STATE_DIR
    sec = SecClient(
        offline=offline,
        sic_store=SicStore(state_dir / "sic"),
        periodic_store=PeriodicStore(state_dir / "periodic"),
    )
    rows: list[dict] = []
    for path in sorted(companies_dir.glob("*.json")):
        company = read_json(path) or {}
        cik = company.get("cik")
        if not cik:
            continue
        filings = sec.periodic_filings(cik)
        latest = None
        quarters = (company.get("revenue") or {}).get("quarters") or []
        ends = [q.get("end") for q in quarters if q.get("end") and not q.get("missing")]
        if ends:
            from datetime import date as date_cls

            latest = date_cls.fromisoformat(max(ends))
        if refresh_lagging and not offline and facts_may_lag(latest, as_of) and not newer_filings(filings, latest):
            filings = sec.periodic_filings(cik, refresh=True)
        row = freshness_row(company, filings, as_of)
        if row["newerFilings"]:
            rows.append(row)
    meta = read_json(data_dir / "meta.json") or {}
    return {
        "asOf": as_of.isoformat(),
        "dataset": (meta.get("dataset") or {}).get("id"),
        "generatedAt": meta.get("generatedAt"),
        "checked": len(list(companies_dir.glob("*.json"))),
        "lagging": len(rows),
        "rows": rows,
    }


if __name__ == "__main__":
    sys.exit(main())
