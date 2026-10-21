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

    l2 = sub.add_parser("layer2", help="Build Layer 2 sequential-growth JSON from an existing Layer 1 dataset")
    l2.add_argument(
        "--data-dir",
        default=str(config.OUTPUT_DIR),
        help="Directory with meta.json, screener.json, companies/",
    )
    l2.add_argument("--output", help="Destination layer2.json (default: <data-dir>/layer2.json)")
    l2.add_argument("--config", help="Thresholds JSON (default: pipeline/config/layer2.json)")

    ae = sub.add_parser(
        "attach-earnings",
        help="Add net-income detail to an existing Layer 1 dataset (does not change revenue, TTM, or buckets)",
    )
    ae.add_argument(
        "--data-dir",
        default=str(config.OUTPUT_DIR),
        help="Directory with meta.json, screener.json, companies/",
    )
    ae.add_argument("--state-dir", help="Compact state directory (facts/statements/periodic)")
    ae.add_argument(
        "--no-merge-facts",
        action="store_true",
        help="Do not merge earnings into compact facts from the zip",
    )
    ae.add_argument("--no-verify", action="store_true", help="Skip per-quarter filing checks for net income")

    d = sub.add_parser(
        "daily-update",
        help="Incrementally update the existing dataset from new SEC 10-Q/10-K filings",
    )
    d.add_argument(
        "--data-dir",
        default=str(config.OUTPUT_DIR),
        help="Dataset directory (default: web/public/data)",
    )
    d.add_argument("--lookback-days", type=int, default=None, help="Rolling EDGAR daily-index window (default: 10)")
    d.add_argument("--as-of", help="YYYY-MM-DD (default: today in America/Los_Angeles)")
    d.add_argument("--offline", action="store_true", help="Use cached downloads only")
    d.add_argument("--no-verify", action="store_true", help="Skip per-quarter checks against filing statements")
    d.add_argument("--no-layer3", action="store_true", help="Do not rebuild Layer 3 issuer files")
    d.add_argument("--dry-run", action="store_true", help="Compute the update without writing the dataset")
    d.add_argument(
        "--write-live",
        action="store_true",
        help="Allow writing web/public/data (refused by default, same as build --write-live)",
    )
    d.add_argument("--state-dir", help="Override compact state directory")
    d.add_argument(
        "--rebuild-tickers",
        default="",
        help="Comma-separated tickers to rebuild from current Company Facts even without a new 10-Q/10-K",
    )

    l3 = sub.add_parser(
        "layer3",
        help="Build Layer 3 financial-metric JSON from an existing Layer 1 dataset (no scoring)",
    )
    l3.add_argument(
        "--data-dir",
        default=str(config.OUTPUT_DIR),
        help="Directory with screener.json, issuers.json, and optional companies/",
    )
    l3.add_argument("--output", help="Destination layer3.json (default: <data-dir>/layer3.json)")
    l3.add_argument("--facts-zip", help="SEC companyfacts.zip with full us-gaap concepts")
    l3.add_argument("--facts-dir", help="Directory of raw Company Facts JSON (CIK##########.json)")
    l3.add_argument(
        "--use-cached-facts",
        action="store_true",
        help="Read pipeline/.cache/sec/bulk/companyfacts.zip when --facts-zip is omitted",
    )
    l3.add_argument("--limit", type=int, help="Update only the first N issuers (never wipes others)")
    l3.add_argument(
        "--ciks",
        help="Comma-separated CIKs to update. Other issuer files are left in place.",
    )
    l3.add_argument(
        "--mode",
        choices=("incremental", "full"),
        default="incremental",
        help="incremental updates selected CIKs in place; full writes a staging tree first",
    )
    l3.add_argument("--staging-dir", help="Directory for a full rebuild (default: <output>.staging)")
    l3.add_argument(
        "--publish",
        action="store_true",
        help="After a validated full rebuild, copy staging over dest (requires --mode full)",
    )
    l3.add_argument(
        "--publish-dry-run",
        action="store_true",
        help="Print the publish plan (adds/replaces/removes/migrations) without writing files",
    )
    l3.add_argument(
        "--write-live",
        action="store_true",
        help="Allow writing dest=web/public/data/layer3.json (refused by default)",
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
        elif args.cmd == "layer2":
            from .layer2 import load_thresholds, write_layer2

            data_dir = Path(args.data_dir)
            dest = Path(args.output) if args.output else data_dir / "layer2.json"
            thresholds = load_thresholds(Path(args.config) if args.config else None)
            payload = write_layer2(data_dir, thresholds, dest)
            print(json.dumps(
                {"counts": payload["counts"], "rulesVersion": payload["rulesVersion"], "output": str(dest)},
                indent=2,
            ))
        elif args.cmd == "attach-earnings":
            from .attach_earnings import attach_earnings

            report = attach_earnings(
                Path(args.data_dir),
                state_dir=Path(args.state_dir) if args.state_dir else None,
                merge_facts=not args.no_merge_facts,
                verify_quarters=not args.no_verify,
            )
            print(json.dumps(report, indent=2))
        elif args.cmd == "layer3":
            from .layer3_build import (
                Layer3BuildError,
                default_facts_zip,
                issuer_dir_for,
                plan_layer3_publish,
                resolve_layer3_staging_dest,
                write_layer3,
            )

            data_dir = Path(args.data_dir)
            dest = Path(args.output) if args.output else data_dir / "layer3.json"
            if args.publish_dry_run:
                if args.publish:
                    print("error: --publish-dry-run does not publish; omit --publish", file=sys.stderr)
                    return 2
                staging_dest = resolve_layer3_staging_dest(
                    dest, Path(args.staging_dir) if args.staging_dir else None
                )
                plan = plan_layer3_publish(issuer_dir_for(dest), issuer_dir_for(staging_dest))
                plan["liveDest"] = str(dest)
                plan["stagingDest"] = str(staging_dest)
                plan["published"] = False
                print(json.dumps(plan, indent=2))
                return 0 if plan["ok"] else 2
            facts_zip = Path(args.facts_zip) if args.facts_zip else None
            if facts_zip is None and args.use_cached_facts:
                facts_zip = default_facts_zip()
            ciks = None
            if args.ciks:
                ciks = [part.strip() for part in args.ciks.replace(" ", ",").split(",") if part.strip()]
            try:
                payload = write_layer3(
                    data_dir,
                    dest,
                    facts_dir=Path(args.facts_dir) if args.facts_dir else None,
                    facts_zip=facts_zip,
                    limit=args.limit,
                    ciks=ciks,
                    mode=args.mode,
                    staging_dir=Path(args.staging_dir) if args.staging_dir else None,
                    publish=args.publish,
                    write_live=args.write_live,
                )
            except Layer3BuildError as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 2
            print(json.dumps(
                {
                    "counts": payload["counts"],
                    "extractionVersion": payload["extractionVersion"],
                    "scoring": payload["scoring"],
                    "mode": payload.get("mode"),
                    "updated": payload.get("updated"),
                    "preserved": payload.get("preserved"),
                    "published": payload.get("published"),
                    "stagingDest": payload.get("stagingDest"),
                    "output": str(dest),
                },
                indent=2,
            ))
        elif args.cmd == "daily-update":
            from datetime import date as date_cls

            from .daily_update import run_daily_update

            data_dir = Path(args.data_dir)
            as_of = date_cls.fromisoformat(args.as_of) if args.as_of else None
            report = run_daily_update(
                data_dir,
                lookback_days=args.lookback_days,
                as_of=as_of,
                dry_run=args.dry_run,
                offline=args.offline,
                verify_quarters=not args.no_verify,
                update_layer3=not args.no_layer3,
                write=not args.dry_run,
                write_live=args.write_live,
                state_dir=Path(args.state_dir) if args.state_dir else None,
                rebuild_tickers=args.rebuild_tickers or None,
            )
            print(json.dumps(report, indent=2))
            if not report.get("ok"):
                return 2
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
