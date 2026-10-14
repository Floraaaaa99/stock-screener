from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import Counter

from . import config
from .build import DatasetError, build
from .report import write_validation_report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="screener", description="U.S. Stock Screener data pipeline")
    ap.add_argument("-v", "--verbose", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="Build the static JSON dataset")
    b.add_argument("--universe", default="sample:biotech20", help="sample:<name> or full")
    b.add_argument("--offline", action="store_true", help="Use cached downloads only")
    b.add_argument("--skip-yahoo", action="store_true", help="Do not refresh Yahoo data (use cache)")
    b.add_argument("--no-verify", action="store_true", help="Skip per-quarter checks against filing statements")
    b.add_argument("--report", help="Write a validation report (Markdown) to this path")

    sub.add_parser("universe", help="Print NASDAQ Trader universe statistics")

    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    try:
        if args.cmd == "build":
            meta = build(args.universe, offline=args.offline, skip_yahoo=args.skip_yahoo,
                         verify_quarters=not args.no_verify)
            print(json.dumps(meta["coverage"], indent=2))
            if args.report:
                write_validation_report(config.OUTPUT_DIR, args.report)
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
    except (DatasetError, config.ConfigError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
