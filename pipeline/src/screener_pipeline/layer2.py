"""Layer 2 sequential growth: four-quarter YoY eligibility and descriptive QoQ badges.

Reads Layer 1 company JSON only. Does not fetch or reinterpret SEC revenue.
Classification rules version is RULES_VERSION. Threshold-dependent QoQ badges are
not applied until qoqStableSpreadPctPoints / qoqRecentJumpPctPoints are set.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from . import config
from .cache import read_json, write_json_atomic

RULES_VERSION = 2
LAYER2_SCHEMA_VERSION = 1
N_YOY = 4
N_WINDOW = 8

BUCKET_PASSED = "passed"
BUCKET_WATCHLIST = "watchlist"
BUCKET_DATA_REVIEW = "data_review"
BUCKET_TTM_NONPOSITIVE = "ttm_nonpositive"

CAT_STABLE = "stable_sequential_growth"
CAT_ACCEL = "accelerating_sequential_growth"
CAT_JUMP = "recent_qoq_jump"
CAT_VOL = "qoq_volatility"
CAT_DECLINE = "latest_quarter_revenue_decline"
CAT_OTHER = "other_flat"
CAT_UNABLE = "unable_to_classify"

CAT_LABELS = {
    CAT_STABLE: "Stable sequential growth",
    CAT_ACCEL: "Accelerating sequential growth",
    CAT_JUMP: "Recent QoQ jump",
    CAT_VOL: "QoQ volatility",
    CAT_DECLINE: "Latest-quarter revenue decline",
    CAT_OTHER: "Other / flat",
    CAT_UNABLE: "Unable to classify",
}

THRESHOLD_DEPENDENT = {CAT_STABLE, CAT_JUMP}


@dataclass(frozen=True)
class Thresholds:
    stable_spread_pp: float | None
    recent_jump_pp: float | None

    @classmethod
    def from_mapping(cls, data: dict | None) -> Thresholds:
        data = data or {}
        return cls(_opt_float(data.get("qoqStableSpreadPctPoints")), _opt_float(data.get("qoqRecentJumpPctPoints")))


def _opt_float(v) -> float | None:
    if v is None or v == "":
        return None
    return float(v)


def load_thresholds(path: Path | None = None) -> Thresholds:
    path = path or (config.PIPELINE_DIR / "config" / "layer2.json")
    return Thresholds.from_mapping(read_json(path, default={}) or {})


def pct_change(current: float, previous: float) -> tuple[float | None, str | None]:
    """Unrounded (current/previous − 1) × 100. Nonpositive denominator → N/A, never zero."""
    if previous <= 0:
        return None, "nonpositive_denominator"
    return (current / previous - 1.0) * 100.0, None


def _fiscal(q: dict) -> dict:
    return {
        "fiscalYear": q.get("fiscalYear"),
        "fiscalQuarter": q.get("fiscalQuarter"),
        "start": q.get("start"),
        "end": q.get("end"),
        "label": (
            f"FY{q['fiscalYear']} Q{q['fiscalQuarter']}" if q.get("fiscalYear") and q.get("fiscalQuarter") else None
        ),
    }


def quarter_block_reason(q: dict | None) -> str | None:
    if not q:
        return "missing_quarter"
    if q.get("missing") or q.get("value") is None:
        return "missing_quarter"
    check = q.get("check") or {}
    status = check.get("status")
    if status == "mismatch":
        return "unverified_mismatch"
    if status in ("unavailable", "no_filing"):
        return "unverified"
    if status != "match":
        return "unverified"
    return None


def pair_yoy_reason(current: dict | None, prior: dict | None) -> str | None:
    for q, tag in ((current, "current"), (prior, "prior_year")):
        r = quarter_block_reason(q)
        if r:
            return f"{r}_{tag}" if r == "missing_quarter" else r
    if current.get("concept") and prior.get("concept") and current["concept"] != prior["concept"]:
        return "incomparable_concept"
    if prior["value"] <= 0:
        return "nonpositive_denominator"
    return None


def pair_qoq_reason(current: dict | None, previous: dict | None) -> str | None:
    for q in (current, previous):
        r = quarter_block_reason(q)
        if r:
            return r
    if current.get("concept") and previous.get("concept") and current["concept"] != previous["concept"]:
        return "incomparable_concept"
    if previous["value"] <= 0:
        return "nonpositive_denominator"
    return None


def _rate_entry(*, current, other, rate, reason, kind: str) -> dict:
    abs_change = None
    if current and not current.get("missing") and other and not other.get("missing"):
        if current.get("value") is not None and other.get("value") is not None:
            abs_change = current["value"] - other["value"]
    return {
        **_fiscal(current or {}),
        "rate": rate,
        "reason": reason,
        "kind": kind,
        "currentValue": None if not current or current.get("missing") else current.get("value"),
        "otherValue": None if not other or other.get("missing") else other.get("value"),
        "absoluteChange": abs_change,
        "currentUrl": None if not current else current.get("url"),
        "otherUrl": None if not other else other.get("url"),
        "currentForm": None if not current else current.get("form"),
        "otherForm": None if not other else other.get("form"),
        "currentCheck": None if not current else (current.get("check") or {}).get("status"),
        "otherCheck": None if not other else (other.get("check") or {}).get("status"),
    }


def _badge(cat: str, tooltip: str, *, applied: bool, blocked: bool = False) -> dict:
    return {
        "id": cat,
        "label": CAT_LABELS[cat],
        "tooltip": tooltip,
        "applied": applied,
        "blockedByThreshold": blocked,
        "rulesVersion": RULES_VERSION,
    }


def _fmt(rate: float | None) -> str:
    if rate is None:
        return "N/A"
    sign = "+" if rate > 0 else "−" if rate < 0 else ""
    return f"{sign}{abs(rate):.4f}%"


def classify_qoq_badges(qoq_oldest_to_newest: list[float | None], thresholds: Thresholds) -> list[dict]:
    """Independent QoQ category rules. Multiple applied badges are allowed."""
    rates = list(qoq_oldest_to_newest)
    if len(rates) != 4:
        rates = (rates + [None, None, None, None])[:4]
    latest = rates[3]
    preceding = rates[:3]
    complete = all(r is not None for r in rates)
    all_positive = complete and all(r > 0 for r in rates)
    badges: list[dict] = []

    # Accelerating: all four > 0 and strictly increasing oldest → newest.
    if all_positive and rates[0] < rates[1] < rates[2] < rates[3]:
        seq = ", ".join(_fmt(r) for r in rates)
        badges.append(
            _badge(
                CAT_ACCEL,
                f"All four QoQ rates > 0% and strictly increasing oldest→newest: {seq}. Rules v{RULES_VERSION}.",
                applied=True,
            )
        )

    # Stable: all four > 0 and range ≤ configured spread.
    if thresholds.stable_spread_pp is None:
        badges.append(
            _badge(
                CAT_STABLE,
                "Stable sequential growth requires all four QoQ > 0% and (max − min) ≤ a configured spread in "
                "percentage points. Threshold not configured.",
                applied=False,
                blocked=True,
            )
        )
    elif all_positive:
        spread = max(rates) - min(rates)
        if spread <= thresholds.stable_spread_pp:
            seq = ", ".join(_fmt(r) for r in rates)
            badges.append(
                _badge(
                    CAT_STABLE,
                    f"All four QoQ > 0% and spread {spread:.4f} pp ≤ {thresholds.stable_spread_pp:g} pp: {seq}. "
                    f"Rules v{RULES_VERSION}.",
                    applied=True,
                )
            )

    # Recent jump: latest − max(preceding three) ≥ configured jump. Needs all four values.
    if thresholds.recent_jump_pp is None:
        badges.append(
            _badge(
                CAT_JUMP,
                "Recent QoQ jump requires latest QoQ − max(preceding three) ≥ a configured jump in percentage "
                "points. Threshold not configured.",
                applied=False,
                blocked=True,
            )
        )
    elif complete and latest is not None:
        gap = latest - max(preceding)  # type: ignore[arg-type]
        if gap >= thresholds.recent_jump_pp:
            badges.append(
                _badge(
                    CAT_JUMP,
                    f"Latest QoQ {_fmt(latest)} minus max of preceding three ({', '.join(_fmt(r) for r in preceding)}) "
                    f"is {gap:.4f} pp ≥ {thresholds.recent_jump_pp:g} pp. Rules v{RULES_VERSION}.",
                    applied=True,
                )
            )

    # Volatility: ≥2 sign changes among the four rates, ignoring exact zeros.
    if complete:
        signs = [1 if r > 0 else -1 for r in rates if r != 0]
        changes = sum(a != b for a, b in zip(signs, signs[1:], strict=False))
        if changes >= 2:
            seq = ", ".join(_fmt(r) for r in rates)
            badges.append(
                _badge(
                    CAT_VOL,
                    f"Sign changes (ignoring exact zeros) = {changes} ≥ 2 across QoQ {seq}. Rules v{RULES_VERSION}.",
                    applied=True,
                )
            )

    # Latest-quarter decline: only the latest QoQ is required.
    if latest is not None and latest < 0:
        badges.append(
            _badge(
                CAT_DECLINE,
                f"Latest QoQ {_fmt(latest)} is < 0%. Earlier quarters are not required. Rules v{RULES_VERSION}.",
                applied=True,
            )
        )

    applied = [b for b in badges if b["applied"]]
    thresholds_pending = any(b["blockedByThreshold"] for b in badges)
    # Other/flat only after every rule that could apply has been evaluated.
    # Unconfigured thresholds and incomplete QoQ must not land here.
    if complete and not applied and not thresholds_pending:
        seq = ", ".join(_fmt(r) for r in rates)
        badges.append(
            _badge(
                CAT_OTHER,
                f"All four QoQ rates are present ({seq}) but no other category rule matched. Rules v{RULES_VERSION}.",
                applied=True,
            )
        )
    if not applied and not any(b["id"] == CAT_OTHER and b["applied"] for b in badges):
        if not complete and not (latest is not None and latest < 0):
            badges.append(
                _badge(
                    CAT_UNABLE,
                    f"Insufficient valid QoQ data to apply an objective category rule. Rules v{RULES_VERSION}.",
                    applied=True,
                )
            )
    return badges


def analyze_company(company: dict, thresholds: Thresholds | None = None) -> dict:
    """Derive Layer 2 metrics from one Layer 1 company JSON object."""
    thresholds = thresholds or Thresholds(None, None)
    ttm = company.get("ttm") or {}
    rev = company.get("revenue") or {}
    sic = company.get("sic") or {}
    quarters = list(rev.get("quarters") or [])
    window = quarters[:N_WINDOW]
    ttm_growth = ttm.get("growthPct")
    reasons: list[str] = []

    if len(window) < N_WINDOW:
        reasons.append("insufficient_quarters")

    yoy_newest_first: list[dict] = []
    for i in range(N_YOY):
        cur = window[i] if i < len(window) else None
        prior = window[i + 4] if i + 4 < len(window) else None
        reason = "insufficient_quarters" if len(window) < N_WINDOW else pair_yoy_reason(cur, prior)
        rate = None
        if reason is None:
            rate, reason = pct_change(cur["value"], prior["value"])
        if reason:
            reasons.append(reason)
        yoy_newest_first.append(_rate_entry(current=cur, other=prior, rate=rate, reason=reason, kind="yoy"))

    qoq_newest_first: list[dict] = []
    for i in range(N_YOY):
        cur = window[i] if i < len(window) else None
        prev = window[i + 1] if i + 1 < len(window) else None
        reason = pair_qoq_reason(cur, prev)
        rate = None
        if reason is None:
            rate, reason = pct_change(cur["value"], prev["value"])
        qoq_newest_first.append(_rate_entry(current=cur, other=prev, rate=rate, reason=reason, kind="qoq"))

    yoy = list(reversed(yoy_newest_first))
    qoq = list(reversed(qoq_newest_first))
    yoy_rates = [e["rate"] for e in yoy]
    qoq_rates = [e["rate"] for e in qoq]
    yoy_complete = all(r is not None for r in yoy_rates)
    unique_reasons = list(dict.fromkeys(reasons))

    if ttm_growth is not None and ttm_growth <= 0:
        bucket = BUCKET_TTM_NONPOSITIVE
    elif not yoy_complete:
        bucket = BUCKET_DATA_REVIEW
        if ttm.get("reason") and ttm["reason"] not in unique_reasons:
            unique_reasons.append(ttm["reason"])
        if not unique_reasons:
            unique_reasons.append("incomplete_yoy")
    elif ttm_growth is None or ttm_growth <= 0:
        bucket = BUCKET_DATA_REVIEW
        unique_reasons.append(ttm.get("reason") or "no_ttm_growth")
    elif all(r > 0 for r in yoy_rates):
        bucket = BUCKET_PASSED
    else:
        bucket = BUCKET_WATCHLIST

    badges = classify_qoq_badges(qoq_rates, thresholds)
    return {
        "ticker": company["ticker"],
        "name": company["name"],
        "exchange": company.get("exchange"),
        "type": company.get("securityType"),
        "sicCode": sic.get("code"),
        "sicMajorGroup": sic.get("majorGroup"),
        "sicIndustry": sic.get("label"),
        "revenueCurrency": rev.get("currency") or ttm.get("currency"),
        "revenueConcept": rev.get("concept"),
        "layer1SchemaVersion": company.get("schemaVersion"),
        "ttmGrowth": ttm_growth,
        "ttmReason": ttm.get("reason"),
        "bucket": bucket,
        "dataReviewReasons": unique_reasons if bucket == BUCKET_DATA_REVIEW else [],
        "yoy": yoy,
        "qoq": qoq,
        "badges": badges,
        "appliedCategories": [b["id"] for b in badges if b["applied"]],
        "rulesVersion": RULES_VERSION,
    }


def build_layer2(data_dir: Path, thresholds: Thresholds | None = None) -> dict:
    """Read Layer 1 JSON from data_dir and write a Layer 2 file (caller decides destination)."""
    thresholds = thresholds or load_thresholds()
    meta = read_json(data_dir / "meta.json") or {}
    screener = read_json(data_dir / "screener.json") or {}
    rows_out: list[dict] = []
    for row in screener.get("rows") or []:
        company = read_json(data_dir / "companies" / f"{row['ticker']}.json")
        if not company:
            continue
        rows_out.append(analyze_company(company, thresholds))
    counts = {
        BUCKET_PASSED: 0,
        BUCKET_WATCHLIST: 0,
        BUCKET_DATA_REVIEW: 0,
        BUCKET_TTM_NONPOSITIVE: 0,
    }
    for r in rows_out:
        counts[r["bucket"]] = counts.get(r["bucket"], 0) + 1
    rows_out.sort(key=lambda r: (r["ttmGrowth"] is None, -(r["ttmGrowth"] or 0), r["ticker"]))
    return {
        "schemaVersion": LAYER2_SCHEMA_VERSION,
        "rulesVersion": RULES_VERSION,
        "generatedAt": meta.get("generatedAt"),
        "layer1GeneratedAt": meta.get("generatedAt"),
        "layer1SchemaVersion": meta.get("schemaVersion"),
        "thresholds": {
            "qoqStableSpreadPctPoints": thresholds.stable_spread_pp,
            "qoqRecentJumpPctPoints": thresholds.recent_jump_pp,
        },
        "counts": {
            "passed": counts[BUCKET_PASSED],
            "watchlist": counts[BUCKET_WATCHLIST],
            "dataReview": counts[BUCKET_DATA_REVIEW],
            "ttmNonpositive": counts[BUCKET_TTM_NONPOSITIVE],
            "listings": len(rows_out),
        },
        "rows": rows_out,
    }


def write_layer2(data_dir: Path, thresholds: Thresholds | None = None, dest: Path | None = None) -> dict:
    payload = build_layer2(data_dir, thresholds)
    dest = dest or (data_dir / "layer2.json")
    write_json_atomic(dest, payload)
    return payload


def load_layer2_config_text() -> str:
    path = config.PIPELINE_DIR / "config" / "layer2.json"
    return path.read_text(encoding="utf-8") if path.exists() else json.dumps({"rulesVersion": RULES_VERSION})
