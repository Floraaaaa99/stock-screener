#!/usr/bin/env python3
"""Compare a Layer 3 staging tree to production v3. Does not write production files."""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from screener_pipeline.cache import read_json
from screener_pipeline.layer3_build import issuer_dir_for, live_layer3_dest, validate_layer3_publish
from screener_pipeline.layer3_concepts import STOCK_ALIGN_DAYS
from screener_pipeline.quarters import values_agree

OVERLAP_FLOW = (
    "ocf",
    "capex",
    "fcf",
    "operatingIncome",
    "interestExpense",
    "depreciationAmortization",
    "ebitda",
)
OVERLAP_STOCK = ("cash", "shortTermDebt", "longTermDebt", "totalDebt", "netDebt")
COVERAGE_KEYS = (
    "revenue",
    "netIncome",
    "grossProfit",
    "costOfRevenue",
    "ocf",
    "capex",
    "fcf",
    "cash",
    "totalDebt",
    "accountsReceivable",
    "inventory",
    "accountsPayable",
    "currentAssets",
    "currentLiabilities",
)
DERIVED_EXPECT_PROVENANCE = {
    "fcf",
    "ebitda",
    "grossMargin",
    "operatingMargin",
    "netMargin",
    "fcfMargin",
    "cashConversion",
    "netDebt",
    "currentRatio",
    "operatingWorkingCapital",
    "dso",
    "dio",
    "dpo",
    "cashConversionCycle",
}
RATIO_LIMITS = {
    "grossMargin": (-0.5, 1.5),
    "operatingMargin": (-5.0, 2.0),
    "netMargin": (-5.0, 2.0),
    "fcfMargin": (-5.0, 2.0),
    "currentRatio": (0.0, 80.0),
    "dso": (0.0, 400.0),
    "dio": (0.0, 500.0),
    "dpo": (0.0, 400.0),
    "cashConversionCycle": (-400.0, 700.0),
    "cashConversion": (-5.0, 20.0),
}


def _num(item: dict | None, key: str) -> float | None:
    if not isinstance(item, dict):
        return None
    val = item.get(key)
    return val if isinstance(val, (int, float)) else None


def _close(a: float | None, b: float | None) -> bool:
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    return values_agree(float(a), float(b)) or math.isclose(float(a), float(b), rel_tol=1e-6, abs_tol=1.0)


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _rel_delta(old: float, new: float) -> float | None:
    if old == 0:
        return None
    return abs(new - old) / abs(old)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--staging-index", required=True)
    ap.add_argument("--live-index", default=str(live_layer3_dest()))
    ap.add_argument("--report", required=True)
    args = ap.parse_args(argv)

    staging_index = Path(args.staging_index)
    live_index = Path(args.live_index)
    if staging_index.resolve() == live_index.resolve():
        raise SystemExit("staging index must not be the production layer3.json")

    staging_dir = issuer_dir_for(staging_index)
    live_dir = issuer_dir_for(live_index)
    publish_errors = validate_layer3_publish(live_dir, staging_dir)

    staged_files = sorted(staging_dir.glob("*.json"))
    live_by_name = {p.name: p for p in live_dir.glob("*.json")}
    live_by_ticker: dict[str, dict] = {}
    live_payloads: dict[str, dict] = {}
    for path in live_by_name.values():
        payload = read_json(path) or {}
        live_payloads[path.name] = payload
        ticker = payload.get("displayTicker")
        if ticker:
            live_by_ticker[str(ticker)] = payload

    extraction = Counter()
    verification = Counter()
    model = Counter()
    scoring = Counter()
    coverage = {k: Counter() for k in COVERAGE_KEYS}
    method = Counter()
    method_by_metric = Counter()
    missing_reasons = defaultdict(Counter)
    identity = Counter()
    gp_cogs_ok = 0
    gp_cogs_fail = 0
    gp_cogs_skip = 0
    overlap_changed = []
    overlap_kind = Counter()
    overlap_metric = Counter()
    extracted_to_pending = []
    status_transitions = Counter()
    ratio_flags = []
    ratio_flag_count = 0
    examples_missing = defaultdict(list)
    examples_conflict = []
    examples_derived_gp = []
    examples_pending = []
    examples_na = []
    alignment_mismatch = []
    alignment_mismatch_count = 0
    ttm_inconsistent = []
    ttm_inconsistent_count = 0
    statement_verified = 0
    filename_cik_mismatch = []
    derived_missing_provenance = []
    derived_missing_provenance_count = 0
    fiscal_gaps = []
    fiscal_gap_count = 0
    failures = []
    versions = Counter()

    for path in staged_files:
        payload = read_json(path) or {}
        cik = path.stem
        payload_cik = str(payload.get("cik") or "").zfill(10)
        extraction[payload.get("extractionStatus") or "unknown"] += 1
        verification[payload.get("verificationStatus") or "unknown"] += 1
        model[payload.get("modelApplicability") or "unknown"] += 1
        scoring[payload.get("scoringStatus") or "unknown"] += 1
        versions[f"extract:{payload.get('extractionVersion')} schema:{payload.get('schemaVersion')}"] += 1
        metrics = payload.get("metrics") or {}
        if not isinstance(metrics, dict):
            metrics = {}

        if payload_cik != cik:
            filename_cik_mismatch.append(
                {
                    "file": cik,
                    "payloadCik": payload_cik,
                    "ticker": payload.get("displayTicker"),
                    "name": payload.get("name"),
                    "extractionStatus": payload.get("extractionStatus"),
                }
            )

        if payload.get("verificationStatus") == "statement_verified":
            statement_verified += 1
        for item in metrics.values():
            if isinstance(item, dict) and item.get("verification") == "statement_verified":
                statement_verified += 1
                break

        live = live_payloads.get(path.name)
        if live is None:
            live = live_by_ticker.get(str(payload.get("displayTicker") or ""))
        if live and live.get("extractionStatus") == "extracted":
            if payload.get("extractionStatus") == "pending_analysis":
                extracted_to_pending.append(
                    {"file": cik, "ticker": payload.get("displayTicker"), "liveCik": live.get("cik")}
                )
        if live:
            status_transitions[
                f"{live.get('extractionStatus') or 'none'}->{payload.get('extractionStatus') or 'none'}"
            ] += 1
        else:
            status_transitions[f"absent->{payload.get('extractionStatus') or 'none'}"] += 1

        if payload.get("extractionStatus") == "pending_analysis" and len(examples_pending) < 8:
            examples_pending.append(
                {
                    "cik": cik,
                    "ticker": payload.get("displayTicker"),
                    "name": payload.get("name"),
                    "flags": payload.get("flags"),
                }
            )
        if (
            payload.get("modelApplicability") == "not_applicable"
            and payload.get("extractionStatus") == "extracted"
            and len(examples_na) < 6
        ):
            examples_na.append(
                {
                    "cik": cik,
                    "ticker": payload.get("displayTicker"),
                    "sicCode": payload.get("sicCode"),
                    "name": payload.get("name"),
                }
            )

        for key in COVERAGE_KEYS:
            item = metrics.get(key) if isinstance(metrics.get(key), dict) else {}
            status = item.get("status") or "missing"
            if status == "extracted" or (item.get("ttm") is not None or item.get("value") is not None):
                coverage[key]["extracted"] += 1
                meth = item.get("calculationMethod") or "extracted"
                method[meth] += 1
                method_by_metric[f"{key}:{meth}"] += 1
            elif status == "not_applicable":
                coverage[key]["notApplicable"] += 1
            else:
                coverage[key]["missing"] += 1
                missing_reasons[key][item.get("reason") or "unknown"] += 1
                if len(examples_missing[key]) < 5:
                    examples_missing[key].append(
                        {
                            "cik": cik,
                            "ticker": payload.get("displayTicker"),
                            "reason": item.get("reason"),
                            "status": status,
                            "modelApplicability": payload.get("modelApplicability"),
                        }
                    )

        ident = (metrics.get("grossProfit") or {}).get("identity") or (
            metrics.get("costOfRevenue") or {}
        ).get("identity")
        if ident:
            identity[ident] += 1
            if ident == "concept_scope_mismatch" and len(examples_conflict) < 8:
                examples_conflict.append(
                    {
                        "cik": cik,
                        "ticker": payload.get("displayTicker"),
                        "name": payload.get("name"),
                        "gp": (metrics.get("grossProfit") or {}).get("ttm"),
                        "cogs": (metrics.get("costOfRevenue") or {}).get("ttm"),
                        "rev": (metrics.get("revenue") or {}).get("ttm"),
                        "gpConcept": (metrics.get("grossProfit") or {}).get("concept"),
                        "cogsConcept": (metrics.get("costOfRevenue") or {}).get("concept"),
                    }
                )

        gp = _num(metrics.get("grossProfit"), "ttm")
        cogs = _num(metrics.get("costOfRevenue"), "ttm")
        rev = _num(metrics.get("revenue"), "ttm")
        if gp is not None and cogs is not None and rev is not None:
            if values_agree(gp + cogs, rev):
                gp_cogs_ok += 1
            else:
                gp_cogs_fail += 1
        else:
            gp_cogs_skip += 1

        if (metrics.get("grossProfit") or {}).get("derivedFrom") == "revenue_minus_cost_of_revenue":
            if len(examples_derived_gp) < 8:
                examples_derived_gp.append(
                    {
                        "cik": cik,
                        "ticker": payload.get("displayTicker"),
                        "gp": gp,
                        "cogs": cogs,
                        "rev": rev,
                        "margin": _num(metrics.get("grossMargin"), "ttm"),
                    }
                )

        ocf_end = None
        ocf_qs = (metrics.get("ocf") or {}).get("quarters") or []
        if ocf_qs:
            ocf_end = ocf_qs[0].get("end")
        if payload.get("dataAsOf") and ocf_end and payload["dataAsOf"] != ocf_end:
            alignment_mismatch_count += 1
            if len(alignment_mismatch) < 8:
                alignment_mismatch.append(
                    {"cik": cik, "ticker": payload.get("displayTicker"), "dataAsOf": payload.get("dataAsOf"), "ocfEnd": ocf_end}
                )

        cash_end = (metrics.get("cash") or {}).get("end")
        cash_dt = _parse_date(cash_end)
        ocf_dt = _parse_date(ocf_end)
        if cash_dt and ocf_dt and abs((cash_dt - ocf_dt).days) > STOCK_ALIGN_DAYS:
            fiscal_gap_count += 1
            if len(fiscal_gaps) < 8:
                fiscal_gaps.append(
                    {
                        "cik": cik,
                        "ticker": payload.get("displayTicker"),
                        "ocfEnd": ocf_end,
                        "cashEnd": cash_end,
                        "days": abs((cash_dt - ocf_dt).days),
                    }
                )

        ocf = metrics.get("ocf") or {}
        capex = metrics.get("capex") or {}
        fcf = metrics.get("fcf") or {}
        if ocf.get("ttm") is not None and capex.get("ttm") is not None and fcf.get("ttm") is not None:
            if not values_agree(ocf["ttm"] - capex["ttm"], fcf["ttm"]):
                ttm_inconsistent_count += 1
                if len(ttm_inconsistent) < 15:
                    ttm_inconsistent.append(
                        {
                            "cik": cik,
                            "ticker": payload.get("displayTicker"),
                            "kind": "fcf_ne_ocf_minus_capex",
                            "ocf": ocf.get("ttm"),
                            "capex": capex.get("ttm"),
                            "fcf": fcf.get("ttm"),
                        }
                    )

        for key in DERIVED_EXPECT_PROVENANCE:
            item = metrics.get(key)
            if not isinstance(item, dict):
                continue
            if item.get("calculationMethod") != "derived":
                continue
            if item.get("ttm") is None and item.get("value") is None:
                continue
            if item.get("formula") or item.get("derivedFrom"):
                continue
            derived_missing_provenance_count += 1
            if len(derived_missing_provenance) < 10:
                derived_missing_provenance.append({"cik": cik, "ticker": payload.get("displayTicker"), "metric": key})

        if live and live.get("metrics"):
            lm = live["metrics"]
            diffs = {}
            for key in OVERLAP_FLOW:
                a, b = _num(lm.get(key), "ttm"), _num(metrics.get(key), "ttm")
                if not _close(a, b):
                    kind = "changed" if a is not None and b is not None else ("gained" if a is None else "lost")
                    overlap_kind[f"{key}:{kind}"] += 1
                    overlap_metric[key] += 1
                    diffs[key] = {"v3": a, "v4": b, "kind": kind, "rel": _rel_delta(a, b) if a is not None and b is not None else None}
            for key in OVERLAP_STOCK:
                a, b = _num(lm.get(key), "value"), _num(metrics.get(key), "value")
                if not _close(a, b):
                    kind = "changed" if a is not None and b is not None else ("gained" if a is None else "lost")
                    overlap_kind[f"{key}:{kind}"] += 1
                    overlap_metric[key] += 1
                    diffs[key] = {"v3": a, "v4": b, "kind": kind, "rel": _rel_delta(a, b) if a is not None and b is not None else None}
            if diffs:
                overlap_changed.append(
                    {"cik": cik, "ticker": payload.get("displayTicker"), "name": payload.get("name"), "diffs": diffs}
                )

        for key, (lo, hi) in RATIO_LIMITS.items():
            val = _num(metrics.get(key), "ttm")
            if val is None:
                val = _num(metrics.get(key), "value")
            if val is None:
                continue
            if val < lo or val > hi:
                ratio_flag_count += 1
                if len(ratio_flags) < 40:
                    ratio_flags.append(
                        {
                            "cik": cik,
                            "ticker": payload.get("displayTicker"),
                            "metric": key,
                            "value": val,
                            "range": [lo, hi],
                        }
                    )

    staged_names = {p.name for p in staged_files}
    live_only = sorted(set(live_by_name) - staged_names)
    staged_only = sorted(staged_names - set(live_by_name))

    # Keep the largest relative overlap changes as examples.
    def _max_rel(row: dict) -> float:
        rels = [d.get("rel") or 0.0 for d in row["diffs"].values() if d.get("rel") is not None]
        return max(rels) if rels else 0.0

    overlap_changed.sort(key=_max_rel, reverse=True)

    index = read_json(staging_index) or {}
    live_index_payload = read_json(live_index) or {}
    report = {
        "productionUntouchedNote": "This script only reads production files.",
        "stagingIndex": str(staging_index),
        "liveIndex": str(live_index),
        "publishBlockedReasons": publish_errors,
        "issuersStaged": len(staged_files),
        "issuersLive": len(live_by_name),
        "liveOnly": live_only[:20],
        "liveOnlyCount": len(live_only),
        "stagedOnly": staged_only[:20],
        "stagedOnlyCount": len(staged_only),
        "filenamePayloadCikMismatch": filename_cik_mismatch,
        "versions": dict(versions),
        "extraction": dict(extraction),
        "verification": dict(verification),
        "modelApplicability": dict(model),
        "scoring": dict(scoring),
        "indexCounts": index.get("counts"),
        "liveIndexCounts": live_index_payload.get("counts"),
        "coverage": {k: dict(v) for k, v in coverage.items()},
        "calculationMethod": {k: v for k, v in method.items()},
        "calculationMethodByMetric": dict(method_by_metric),
        "missingReasons": {k: dict(v) for k, v in missing_reasons.items()},
        "identity": dict(identity),
        "gpCogsIdentity": {"holds": gp_cogs_ok, "fails": gp_cogs_fail, "skipped": gp_cogs_skip},
        "extractedBecamePending": extracted_to_pending,
        "statusTransitions": dict(status_transitions),
        "overlapChangedCount": len(overlap_changed),
        "overlapByMetric": dict(overlap_metric),
        "overlapByKind": dict(overlap_kind),
        "overlapChangedExamples": overlap_changed[:25],
        "ratioFlagCount": ratio_flag_count,
        "ratioFlagExamples": ratio_flags[:25],
        "alignmentMismatchCount": alignment_mismatch_count,
        "alignmentMismatchExamples": alignment_mismatch,
        "fiscalGapCount": fiscal_gap_count,
        "fiscalGapExamples": fiscal_gaps,
        "ttmInconsistentCount": ttm_inconsistent_count,
        "ttmInconsistentExamples": ttm_inconsistent[:15],
        "derivedMissingProvenanceCount": derived_missing_provenance_count,
        "derivedMissingProvenanceExamples": derived_missing_provenance,
        "statementVerifiedCount": statement_verified,
        "examplesMissing": {k: v for k, v in examples_missing.items()},
        "examplesConflict": examples_conflict,
        "examplesDerivedGp": examples_derived_gp,
        "examplesPending": examples_pending,
        "examplesNotApplicableExtracted": examples_na,
        "failures": failures,
    }
    Path(args.report).write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: report[k] for k in (
        "issuersStaged", "issuersLive", "extraction", "modelApplicability",
        "gpCogsIdentity", "overlapChangedCount", "extractedBecamePending",
        "publishBlockedReasons", "statementVerifiedCount",
        "filenamePayloadCikMismatch", "statusTransitions",
        "ratioFlagCount", "ttmInconsistentCount", "derivedMissingProvenanceCount",
    )}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
