"""Derived Layer 3 series: TTM YoY, margins, FCF/EBITDA quarters, working-capital ratios.

Derived numbers keep formula and inputs. ``calculationMethod`` is ``derived``;
``verification`` is never ``statement_verified``. Missing denominators stay null.
"""

from __future__ import annotations

from datetime import date

from .layer3_concepts import STOCK_ALIGN_DAYS
from .quarters import values_agree

DERIVED_NOTE = (
    "Derived from Company Facts inputs. The calculation is not a filing face line "
    "and the inputs were not statement-checked."
)

# Inspect-only bands. Values outside the range keep their raw number and get a flag.
RATIO_QUALITY_BANDS = {
    "dso": (0.0, 400.0),
    "dio": (0.0, 500.0),
    "dpo": (0.0, 400.0),
    "cashConversionCycle": (-400.0, 700.0),
    "currentRatio": (0.0, 80.0),
}


def suppress_incompatible_derived(
    metric: dict,
    *,
    reason: str = "concept_scope_mismatch",
) -> dict:
    """Hide a derived ratio built from incompatible GP/COGS/Revenue. Keep the math."""
    if not isinstance(metric, dict):
        return metric
    if metric.get("status") == "not_applicable":
        return metric
    out = dict(metric)
    if out.get("ttm") is not None:
        out["unreliableTtm"] = out["ttm"]
        out["ttm"] = None
    if out.get("value") is not None:
        out["unreliableValue"] = out["value"]
        out["value"] = None
    if out.get("previousTtm") is not None:
        out["unreliablePreviousTtm"] = out["previousTtm"]
        out["previousTtm"] = None
    out["status"] = "missing"
    out["reason"] = reason
    flags = list(out.get("qualityFlags") or [])
    if "incompatible_inputs" not in flags:
        flags.append("incompatible_inputs")
    out["qualityFlags"] = flags
    out["qualityNote"] = (
        "Derived ratio suppressed because Gross Profit, Cost of Revenue, and "
        "Revenue do not share a compatible concept scope. Raw GP/COGS/Revenue "
        "series are unchanged."
    )
    return out


def flag_extreme_ratio(metric: dict, key: str) -> dict:
    """Mark an unusually large ratio. Never clamp or replace the computed value."""
    bounds = RATIO_QUALITY_BANDS.get(key)
    if not bounds or not isinstance(metric, dict):
        return metric
    val = metric.get("value")
    if val is None:
        val = metric.get("ttm")
    if not isinstance(val, (int, float)):
        return metric
    lo, hi = bounds
    if lo <= val <= hi:
        return metric
    flags = list(metric.get("qualityFlags") or [])
    if "extreme_ratio" not in flags:
        flags.append("extreme_ratio")
    metric["qualityFlags"] = flags
    metric["qualityNote"] = (
        f"{key} {val} is outside the usual range [{lo}, {hi}]. "
        "The computed value is preserved; it is not clamped."
    )
    return metric


def ttm_yoy(current: float | None, previous: float | None) -> tuple[float | None, str | None]:
    """Percent change vs the prior non-overlapping TTM. Prior ≤ 0 is not a ratio."""
    if current is None or previous is None:
        return None, "insufficient_ttm"
    if previous == 0:
        return None, "previous_ttm_zero"
    if previous < 0:
        return None, "previous_ttm_not_positive"
    return (current / previous - 1.0) * 100.0, None


def apply_ttm_yoy(metric: dict) -> dict:
    yoy, reason = ttm_yoy(metric.get("ttm"), metric.get("previousTtm"))
    metric["ttmYoy"] = yoy
    metric["ttmYoyReason"] = None if yoy is not None else reason
    return metric


def _quarter_by_end(quarters: list[dict] | None) -> dict[str, dict]:
    return {q["end"]: q for q in (quarters or []) if q.get("end")}


def _pair_op(
    left: dict,
    right: dict,
    *,
    formula: str,
    op,
    missing_left: str,
    missing_right: str,
) -> dict:
    lq = left.get("quarters") or []
    rq = right.get("quarters") or []
    by_r = _quarter_by_end(rq)
    quarters: list[dict] = []
    for q in lq[:8]:
        end = q.get("end")
        other = by_r.get(end) if end else None
        row = {
            "fiscalYear": q.get("fiscalYear"),
            "fiscalQuarter": q.get("fiscalQuarter"),
            "start": q.get("start"),
            "end": end,
            "value": None,
            "method": "derived",
            "formula": formula,
            "calculationMethod": "derived",
            "verification": "not_checked",
        }
        if q.get("value") is None:
            row["reason"] = missing_left
        elif other is None or other.get("value") is None:
            row["reason"] = missing_right
        else:
            row["value"] = op(q["value"], other["value"])
            row["inputs"] = {"left": q["value"], "right": other["value"]}
        quarters.append(row)

    current = previous = None
    reason = None
    if left.get("ttm") is None:
        reason = missing_left
    elif right.get("ttm") is None:
        reason = missing_right
    else:
        current = op(left["ttm"], right["ttm"])
        if left.get("previousTtm") is not None and right.get("previousTtm") is not None:
            previous = op(left["previousTtm"], right["previousTtm"])
        else:
            reason = left.get("reason") or right.get("reason") or "insufficient_quarters"

    yoy, yoy_reason = ttm_yoy(current, previous)
    return {
        "status": "extracted" if current is not None else "missing",
        "reason": None if current is not None else reason,
        "ttm": current,
        "previousTtm": previous,
        "ttmYoy": yoy,
        "ttmYoyReason": None if yoy is not None else yoy_reason,
        "quarters": quarters,
        "formula": formula,
        "calculationMethod": "derived",
        "verification": "not_checked",
        "verificationNote": DERIVED_NOTE,
        "inputs": {
            "leftConcept": left.get("concept"),
            "rightConcept": right.get("concept"),
        },
    }


def subtract_flows(left: dict, right: dict, formula: str, *, missing_left: str, missing_right: str) -> dict:
    return _pair_op(
        left, right, formula=formula, op=lambda a, b: a - b,
        missing_left=missing_left, missing_right=missing_right,
    )


def add_flows(left: dict, right: dict, formula: str, *, missing_left: str, missing_right: str) -> dict:
    return _pair_op(
        left, right, formula=formula, op=lambda a, b: a + b,
        missing_left=missing_left, missing_right=missing_right,
    )


def ratio_value(
    numer: float | None,
    denom: float | None,
    *,
    require_positive_den: bool = True,
) -> tuple[float | None, str | None]:
    if numer is None:
        return None, "missing_numerator"
    if denom is None:
        return None, "missing_denominator"
    if denom == 0:
        return None, "denominator_zero"
    if require_positive_den and denom < 0:
        return None, "denominator_not_positive"
    return numer / denom, None


def margin_metric(numer: dict, denom: dict, formula: str) -> dict:
    """TTM and 8-quarter ratios. Quarters align on matching end dates only."""
    ttm, ttm_reason = ratio_value(numer.get("ttm"), denom.get("ttm"))
    prior, _ = ratio_value(numer.get("previousTtm"), denom.get("previousTtm"))
    by_d = _quarter_by_end(denom.get("quarters"))
    quarters: list[dict] = []
    for q in (numer.get("quarters") or [])[:8]:
        end = q.get("end")
        other = by_d.get(end) if end else None
        row = {
            "fiscalYear": q.get("fiscalYear"),
            "fiscalQuarter": q.get("fiscalQuarter"),
            "start": q.get("start"),
            "end": end,
            "value": None,
            "method": "derived",
            "formula": formula,
            "calculationMethod": "derived",
            "verification": "not_checked",
        }
        if q.get("value") is None:
            row["reason"] = "missing_numerator"
        elif other is None or other.get("value") is None:
            row["reason"] = "missing_denominator"
        else:
            val, reason = ratio_value(q["value"], other["value"])
            row["value"] = val
            row["reason"] = reason
        quarters.append(row)
    yoy, yoy_reason = ttm_yoy(ttm, prior)
    return {
        "status": "extracted" if ttm is not None else "missing",
        "reason": ttm_reason,
        "ttm": ttm,
        "previousTtm": prior,
        "ttmYoy": yoy,
        "ttmYoyReason": None if yoy is not None else yoy_reason,
        "quarters": quarters,
        "formula": formula,
        "unit": "ratio",
        "calculationMethod": "derived",
        "verification": "not_checked",
        "verificationNote": DERIVED_NOTE,
        "inputs": {"numeratorConcept": numer.get("concept"), "denominatorConcept": denom.get("concept")},
    }


def cash_conversion_metric(ocf: dict, ni: dict) -> dict:
    return margin_metric(ocf, ni, "OCF / Net Income")


def history_on_end(
    history: list[dict] | None,
    end: str | None,
    *,
    align_days: int = STOCK_ALIGN_DAYS,
) -> dict | None:
    """Nearest snapshot within ``align_days`` of the fiscal-slot end.

    Instant dates on 52/53-week calendars (e.g. NVDA 2026-07-26 vs a 07-31 slot)
    must still match. Exact string equality is not required.
    """
    if not end:
        return None
    try:
        target = date.fromisoformat(end)
    except ValueError:
        return None
    best: dict | None = None
    best_delta: int | None = None
    for row in history or []:
        if row.get("value") is None or not row.get("end"):
            continue
        try:
            actual = date.fromisoformat(row["end"])
        except ValueError:
            continue
        delta = abs((actual - target).days)
        if delta <= align_days and (best_delta is None or delta < best_delta):
            best = row
            best_delta = delta
    return best


def stock_yoy(history: list[dict] | None) -> dict:
    """Latest snapshot vs the snapshot four fiscal quarters earlier (same slot offset)."""
    hist = history or []
    latest = next((h for h in hist if h.get("value") is not None), None)
    prior = None
    if latest is not None:
        latest_idx = hist.index(latest)
        prior_idx = latest_idx + 4
        if prior_idx < len(hist):
            prior = hist[prior_idx] if hist[prior_idx].get("value") is not None else None
    if latest is None or prior is None:
        return {
            "status": "missing",
            "reason": "insufficient_stock_history",
            "value": None,
            "calculationMethod": "derived",
            "verification": "not_checked",
        }
    if prior["value"] == 0:
        return {
            "status": "missing",
            "reason": "prior_balance_zero",
            "value": None,
            "end": latest.get("end"),
            "priorEnd": prior.get("end"),
            "calculationMethod": "derived",
            "verification": "not_checked",
        }
    if prior["value"] < 0:
        return {
            "status": "missing",
            "reason": "prior_balance_not_positive",
            "value": None,
            "end": latest.get("end"),
            "priorEnd": prior.get("end"),
            "calculationMethod": "derived",
            "verification": "not_checked",
        }
    return {
        "status": "extracted",
        "reason": None,
        "value": (latest["value"] / prior["value"] - 1.0) * 100.0,
        "unit": "percent",
        "end": latest.get("end"),
        "priorEnd": prior.get("end"),
        "formula": "(latest − year_ago) / year_ago × 100",
        "calculationMethod": "derived",
        "verification": "not_checked",
        "verificationNote": DERIVED_NOTE,
        "inputs": {"latest": latest["value"], "yearAgo": prior["value"]},
    }


def ttm_window(flow: dict) -> tuple[date | None, date | None, int | None]:
    filled = [
        q
        for q in (flow.get("quarters") or [])[:4]
        if q.get("start") and q.get("end") and q.get("value") is not None
    ]
    if len(filled) < 4:
        qs = (flow.get("quarters") or [])[:4]
        if len(qs) == 4 and all(q.get("start") and q.get("end") for q in qs) and flow.get("ttm") is not None:
            filled = qs
        else:
            return None, None, None
    start = date.fromisoformat(filled[-1]["start"])
    end = date.fromisoformat(filled[0]["end"])
    return start, end, (end - start).days + 1


def average_balance(
    history: list[dict] | None,
    begin_end: str | None,
    close_end: str | None,
) -> tuple[float | None, str | None, dict]:
    begin = history_on_end(history, begin_end)
    close = history_on_end(history, close_end)
    inputs = {
        "beginEnd": begin_end,
        "closeEnd": close_end,
        "begin": None if begin is None else begin.get("value"),
        "close": None if close is None else close.get("value"),
    }
    if begin is None or close is None:
        return None, "insufficient_stock_history", inputs
    return (begin["value"] + close["value"]) / 2.0, None, inputs


def days_outstanding(
    *,
    average: float | None,
    flow_ttm: float | None,
    days: int | None,
    formula: str,
    avg_reason: str | None,
    flow_reason: str,
) -> dict:
    if average is None:
        return {
            "status": "missing",
            "reason": avg_reason or "insufficient_stock_history",
            "value": None,
            "calculationMethod": "derived",
            "verification": "not_checked",
            "formula": formula,
        }
    if flow_ttm is None:
        return {
            "status": "missing",
            "reason": flow_reason,
            "value": None,
            "calculationMethod": "derived",
            "verification": "not_checked",
            "formula": formula,
        }
    if flow_ttm == 0:
        return {
            "status": "missing",
            "reason": "denominator_zero",
            "value": None,
            "calculationMethod": "derived",
            "verification": "not_checked",
            "formula": formula,
        }
    if flow_ttm < 0:
        return {
            "status": "missing",
            "reason": "denominator_not_positive",
            "value": None,
            "calculationMethod": "derived",
            "verification": "not_checked",
            "formula": formula,
        }
    if days is None or days <= 0:
        return {
            "status": "missing",
            "reason": "ttm_window_unknown",
            "value": None,
            "calculationMethod": "derived",
            "verification": "not_checked",
            "formula": formula,
        }
    return {
        "status": "extracted",
        "reason": None,
        "value": average / flow_ttm * days,
        "daysInWindow": days,
        "averageBalance": average,
        "flowTtm": flow_ttm,
        "formula": formula,
        "method": "ttm_average_balance / ttm_flow × days_in_window",
        "calculationMethod": "derived",
        "verification": "not_checked",
        "verificationNote": DERIVED_NOTE,
    }


def operating_working_capital(ar: dict, inventory: dict, ap: dict) -> dict:
    """OWC = AR + Inventory − AP. Inventory not_applicable is omitted, not treated as 0."""
    ar_v, inv_v, ap_v = ar.get("value"), inventory.get("value"), ap.get("value")
    inv_status = inventory.get("status")
    if ar_v is None:
        return {
            "status": "missing",
            "reason": "missing_accounts_receivable",
            "value": None,
            "calculationMethod": "derived",
            "verification": "not_checked",
        }
    if ap_v is None:
        return {
            "status": "missing",
            "reason": "missing_accounts_payable",
            "value": None,
            "calculationMethod": "derived",
            "verification": "not_checked",
        }
    if inv_status == "not_applicable":
        return {
            "status": "extracted",
            "reason": None,
            "value": ar_v - ap_v,
            "formula": "AR − AP (inventory not applicable)",
            "end": ar.get("end") or ap.get("end"),
            "calculationMethod": "derived",
            "verification": "not_checked",
            "verificationNote": DERIVED_NOTE,
            "inputs": {"accountsReceivable": ar_v, "accountsPayable": ap_v},
        }
    if inv_v is None:
        return {
            "status": "missing",
            "reason": "missing_inventory",
            "value": None,
            "calculationMethod": "derived",
            "verification": "not_checked",
        }
    return {
        "status": "extracted",
        "reason": None,
        "value": ar_v + inv_v - ap_v,
        "formula": "AR + Inventory − AP",
        "end": ar.get("end") or inventory.get("end") or ap.get("end"),
        "calculationMethod": "derived",
        "verification": "not_checked",
        "verificationNote": DERIVED_NOTE,
        "inputs": {"accountsReceivable": ar_v, "inventory": inv_v, "accountsPayable": ap_v},
    }


def current_ratio_metric(assets: dict, liabilities: dict) -> dict:
    val, reason = ratio_value(assets.get("value"), liabilities.get("value"))
    return {
        "status": "extracted" if val is not None else "missing",
        "reason": reason,
        "value": val,
        "end": assets.get("end") or liabilities.get("end"),
        "formula": "Current Assets / Current Liabilities",
        "calculationMethod": "derived",
        "verification": "not_checked",
        "verificationNote": DERIVED_NOTE if val is not None else None,
        "inputs": {
            "currentAssets": assets.get("value"),
            "currentLiabilities": liabilities.get("value"),
        },
    }


def cash_conversion_cycle(dso: dict, dio: dict, dpo: dict) -> dict:
    """CCC = DSO + DIO − DPO. DIO not_applicable is omitted (not zero-filled)."""
    if dso.get("value") is None:
        return {
            "status": "missing",
            "reason": "missing_dso",
            "value": None,
            "formula": "DSO + DIO − DPO",
            "calculationMethod": "derived",
            "verification": "not_checked",
        }
    if dpo.get("value") is None:
        return {
            "status": "missing",
            "reason": "missing_dpo",
            "value": None,
            "formula": "DSO + DIO − DPO",
            "calculationMethod": "derived",
            "verification": "not_checked",
        }
    if dio.get("status") == "not_applicable":
        return {
            "status": "extracted",
            "reason": None,
            "value": dso["value"] - dpo["value"],
            "formula": "DSO − DPO (DIO not applicable)",
            "calculationMethod": "derived",
            "verification": "not_checked",
            "verificationNote": DERIVED_NOTE,
            "inputs": {"dso": dso["value"], "dpo": dpo["value"]},
        }
    if dio.get("value") is None:
        return {
            "status": "missing",
            "reason": "missing_dio",
            "value": None,
            "formula": "DSO + DIO − DPO",
            "calculationMethod": "derived",
            "verification": "not_checked",
        }
    return {
        "status": "extracted",
        "reason": None,
        "value": dso["value"] + dio["value"] - dpo["value"],
        "formula": "DSO + DIO − DPO",
        "calculationMethod": "derived",
        "verification": "not_checked",
        "verificationNote": DERIVED_NOTE,
        "inputs": {"dso": dso["value"], "dio": dio["value"], "dpo": dpo["value"]},
    }


def identity_holds(gross: float | None, cogs: float | None, revenue: float | None) -> bool:
    if gross is None or cogs is None or revenue is None:
        return False
    return values_agree(gross + cogs, revenue)


CASH_CF_IDENTITY_NOTE = (
    "OCF + investing CF + financing CF is compared to the cash-flow statement change in cash. "
    "F3 Cash (CashAndCashEquivalentsAtCarryingValue) is not used: it may exclude restricted cash "
    "and is a balance-sheet stock, not the CF change line."
)


def _newest_valued_end(metric: dict | None) -> date | None:
    if not isinstance(metric, dict):
        return None
    for q in metric.get("quarters") or []:
        if q.get("value") is not None and q.get("end"):
            try:
                return date.fromisoformat(str(q["end"]))
            except ValueError:
                return None
    return None


def cash_flow_identity(
    *,
    ocf: dict,
    investing: dict,
    financing: dict,
    fx: dict,
    cash_change: dict,
    includes_fx: bool | None,
    cash_family: str | None,
    f3_cash_concept: str | None,
    align_days: int,
) -> dict:
    """Reconcile CF section totals to the CF-statement cash change.

    Unavailable (not identity_mismatch) when FX is required but missing, when the
    cash-change tag is absent, or when F3 cash would be the only reconciling stock.
    """
    base = {
        "status": "missing",
        "reason": None,
        "ttm": None,
        "previousTtm": None,
        "reportedChangeTtm": None,
        "difference": None,
        "identity": None,
        "formula": "OCF + Investing CF + Financing CF",
        "calculationMethod": "derived",
        "verification": "not_checked",
        "verificationNote": CASH_CF_IDENTITY_NOTE,
        "usedF3Cash": False,
        "f3CashConcept": f3_cash_concept,
        "cashFamily": cash_family,
        "concept": cash_change.get("concept") if isinstance(cash_change, dict) else None,
        "cashChangeConcept": cash_change.get("concept") if isinstance(cash_change, dict) else None,
        "fxIncluded": False,
        "quarters": [],
    }
    if cash_change.get("ttm") is None or not cash_change.get("concept"):
        base["reason"] = "missing_cf_cash_change"
        return apply_ttm_yoy(base)
    if cash_family is None or includes_fx is None:
        base["reason"] = "cash_definition_not_comparable"
        return apply_ttm_yoy(base)
    if ocf.get("ttm") is None:
        base["reason"] = "missing_ocf"
        return apply_ttm_yoy(base)
    if investing.get("ttm") is None:
        base["reason"] = "missing_investing_cf"
        return apply_ttm_yoy(base)
    if financing.get("ttm") is None:
        base["reason"] = "missing_financing_cf"
        return apply_ttm_yoy(base)

    ends = [
        _newest_valued_end(ocf),
        _newest_valued_end(investing),
        _newest_valued_end(financing),
        _newest_valued_end(cash_change),
    ]
    if any(e is None for e in ends):
        base["reason"] = "ttm_window_not_aligned"
        return apply_ttm_yoy(base)
    anchor = ends[0]
    if any(abs((e - anchor).days) > align_days for e in ends):
        base["reason"] = "ttm_window_not_aligned"
        return apply_ttm_yoy(base)

    reconstructed = float(ocf["ttm"]) + float(investing["ttm"]) + float(financing["ttm"])
    formula = "OCF + Investing CF + Financing CF"
    fx_used = False
    if includes_fx:
        if fx.get("ttm") is None:
            base["reason"] = "fx_effect_not_disclosed"
            return apply_ttm_yoy(base)
        fx_end = _newest_valued_end(fx)
        if fx_end is None or abs((fx_end - anchor).days) > align_days:
            base["reason"] = "fx_effect_not_disclosed"
            return apply_ttm_yoy(base)
        reconstructed += float(fx["ttm"])
        formula = "OCF + Investing CF + Financing CF + FX on cash"
        fx_used = True

    reported = float(cash_change["ttm"])
    holds = values_agree(reconstructed, reported)
    previous = None
    if (
        ocf.get("previousTtm") is not None
        and investing.get("previousTtm") is not None
        and financing.get("previousTtm") is not None
        and cash_change.get("previousTtm") is not None
        and (not fx_used or fx.get("previousTtm") is not None)
    ):
        previous = float(ocf["previousTtm"]) + float(investing["previousTtm"]) + float(financing["previousTtm"])
        if fx_used:
            previous += float(fx["previousTtm"])

    out = apply_ttm_yoy({
        **base,
        "status": "extracted",
        "reason": None if holds else "identity_mismatch",
        "ttm": reconstructed,
        "previousTtm": previous,
        "reportedChangeTtm": reported,
        "difference": reconstructed - reported,
        "identity": "holds" if holds else "mismatch",
        "formula": formula,
        "verification": "derived" if holds else "not_checked",
        "fxIncluded": fx_used,
        "inputs": {
            "ocf": ocf.get("ttm"),
            "investingCf": investing.get("ttm"),
            "financingCf": financing.get("ttm"),
            "fxOnCash": fx.get("ttm") if fx_used else None,
            "reportedChange": reported,
        },
    })
    if not holds:
        flags = list(out.get("qualityFlags") or [])
        if "cash_flow_identity_mismatch" not in flags:
            flags.append("cash_flow_identity_mismatch")
        out["qualityFlags"] = flags
        out["qualityNote"] = (
            "Comparable CF-statement totals and cash-change line disagree. "
            "Values are preserved; F3 cash was not substituted."
        )
    return out
