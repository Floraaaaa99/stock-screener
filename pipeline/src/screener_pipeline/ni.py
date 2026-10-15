"""Descriptive net-income badges. Never change Layer 2 revenue eligibility."""

from __future__ import annotations

NI_RULES_VERSION = 1

NI_PROF_ALL = "ni_all_profitable"
NI_PROF_ONE_LOSS = "ni_one_loss"
NI_PROF_MULTI_LOSS = "ni_two_or_three_loss"
NI_PROF_ALL_LOSS = "ni_all_loss"
NI_PROF_BREAKEVEN = "ni_contains_breakeven"
NI_PROF_INSUFFICIENT = "ni_insufficient_data"

NI_IMP_FOUR_YOY = "ni_four_yoy_improvements"
NI_IMP_TURNAROUND = "ni_latest_turnaround"
NI_IMP_TO_LOSS = "ni_latest_turned_to_loss"
NI_IMP_SEQ = "ni_four_quarter_sequential"

NI_PROF_LABELS = {
    NI_PROF_ALL: "All four profitable",
    NI_PROF_ONE_LOSS: "One loss quarter",
    NI_PROF_MULTI_LOSS: "Two or three loss quarters",
    NI_PROF_ALL_LOSS: "All four loss-making",
    NI_PROF_BREAKEVEN: "Contains break-even quarter",
    NI_PROF_INSUFFICIENT: "Insufficient NI data",
}

NI_IMP_LABELS = {
    NI_IMP_FOUR_YOY: "Four consecutive YoY improvements",
    NI_IMP_TURNAROUND: "Latest-quarter turnaround",
    NI_IMP_TO_LOSS: "Latest-quarter turned to loss",
    NI_IMP_SEQ: "Four-quarter sequential improvement",
}


def _badge(badge_id: str, labels: dict[str, str], tooltip: str, applied: bool) -> dict:
    return {
        "id": badge_id,
        "label": labels[badge_id],
        "tooltip": tooltip,
        "applied": applied,
        "blockedByThreshold": False,
        "rulesVersion": NI_RULES_VERSION,
    }


def _current(rate: dict | None) -> tuple[bool, float | None, str | None]:
    if not rate:
        return False, None, "missing_quarter"
    value = rate.get("currentValue")
    if value is None:
        return False, None, rate.get("reason") or "missing_quarter"
    if rate.get("currentCheck") != "match":
        return False, value, rate.get("reason") or "unverified"
    return True, float(value), None


def _prior(rate: dict | None) -> tuple[bool, float | None, str | None]:
    if not rate:
        return False, None, "missing_quarter"
    value = rate.get("otherValue")
    if value is None:
        return False, None, rate.get("reason") or "missing_quarter"
    if rate.get("otherCheck") != "match":
        return False, value, rate.get("reason") or "unverified"
    return True, float(value), None


def analyze_net_income(row: dict) -> dict:
    """Classify profitability and improvement from Layer 2 earnings YoY/QoQ. Does not touch bucket."""
    yoy = list(row.get("earningsYoy") or [])
    rev = list(row.get("yoy") or [])
    quarters: list[dict] = []
    for i, rev_q in enumerate(rev):
        ey = next(
            (e for e in yoy if e.get("end") and e.get("end") == rev_q.get("end")),
            yoy[i] if i < len(yoy) else None,
        )
        ok, value, why = _current(ey)
        pok, pval, pwhy = _prior(ey)
        comparable = (ey or {}).get("reason") != "incomparable_concept"
        label = (ey or {}).get("label") or rev_q.get("label") or f"Q{i + 1}"
        prior_ok = bool(pok and comparable)
        quarters.append(
            {
                "label": label,
                "end": rev_q.get("end"),
                "value": value if ok else None,
                "verified": ok,
                "reason": None if ok else why,
                "priorValue": pval if prior_ok else None,
                "priorVerified": prior_ok,
                "priorReason": "incomparable_concept" if not comparable else (None if pok else pwhy),
                "yoyAbs": (value - pval) if ok and prior_ok and value is not None and pval is not None else None,
            }
        )

    complete = len(quarters) == 4 and all(q["verified"] and q["value"] is not None for q in quarters)
    values = [q["value"] for q in quarters] if complete else None
    profitable = sum(1 for v in values if v > 0) if values else None
    losses = sum(1 for v in values if v < 0) if values else None
    zeros = sum(1 for v in values if v == 0) if values else None
    loss_labels = [q["label"] for q in quarters if complete and q["value"] < 0]
    latest_loss = values[-1] < 0 if values else None
    ttm = sum(values) if values else None

    listed = ", ".join(f"{q['label']} {q['value']}" for q in quarters) if complete else ""
    if complete:
        counts_tip = f"{profitable} profitable, {losses} loss, {zeros} break-even. {listed}."
    else:
        have = sum(1 for q in quarters if q["verified"])
        counts_tip = (
            "Need four verified standalone NI quarters in the revenue window; "
            f"do not substitute older quarters. Have {have} of 4."
        )

    profitability: list[dict] = []
    if not complete:
        profitability.append(
            _badge(NI_PROF_INSUFFICIENT, NI_PROF_LABELS, f"{counts_tip} Rules v{NI_RULES_VERSION}.", True)
        )
    else:
        if losses == 0 and zeros == 0:
            primary = NI_PROF_ALL
        elif losses == 1:
            primary = NI_PROF_ONE_LOSS
        elif losses == 4:
            primary = NI_PROF_ALL_LOSS
        elif losses >= 2:
            primary = NI_PROF_MULTI_LOSS
        else:
            primary = None
        if primary:
            extra = f" Latest quarter is {'a loss' if latest_loss else 'not a loss'}."
            if primary != NI_PROF_ALL:
                extra = f" Loss quarters: {', '.join(loss_labels) or 'none'}.{extra}"
            profitability.append(
                _badge(primary, NI_PROF_LABELS, f"{counts_tip}{extra} Rules v{NI_RULES_VERSION}.", True)
            )
        if zeros:
            be = ", ".join(q["label"] for q in quarters if q["value"] == 0)
            profitability.append(
                _badge(
                    NI_PROF_BREAKEVEN,
                    NI_PROF_LABELS,
                    f"{counts_tip} Break-even quarters: {be}. Rules v{NI_RULES_VERSION}.",
                    True,
                )
            )

    improvement: list[dict] = []
    if all(q["verified"] and q["priorVerified"] for q in quarters) and len(quarters) == 4:
        improved = all(q["value"] > q["priorValue"] for q in quarters)
        detail = "; ".join(f"{q['label']} {q['value']} vs {q['priorValue']}" for q in quarters)
        improvement.append(
            _badge(
                NI_IMP_FOUR_YOY,
                NI_IMP_LABELS,
                (
                    f"Each of the latest four NI amounts is greater than the same fiscal quarter last year: {detail}. "
                    f"Improvement is algebraic, including narrower losses. Rules v{NI_RULES_VERSION}."
                    if improved
                    else (
                        f"Unmet. Need each of four NI amounts > same quarter last year. {detail}. "
                        f"Rules v{NI_RULES_VERSION}."
                    )
                ),
                improved,
            )
        )
    else:
        improvement.append(
            _badge(
                NI_IMP_FOUR_YOY,
                NI_IMP_LABELS,
                f"Unavailable. Needs 8 verified comparable NI quarters. Rules v{NI_RULES_VERSION}.",
                False,
            )
        )

    prev = quarters[2] if len(quarters) > 2 else None
    latest = quarters[3] if len(quarters) > 3 else None
    if prev and latest and prev["verified"] and latest["verified"]:
        turn = prev["value"] < 0 < latest["value"]
        to_loss = prev["value"] > 0 > latest["value"]
        pair = f"{prev['label']} {prev['value']} → {latest['label']} {latest['value']}"
        improvement.append(
            _badge(
                NI_IMP_TURNAROUND,
                NI_IMP_LABELS,
                (
                    f"Previous quarter NI < 0 and latest NI > 0: {pair}. Rules v{NI_RULES_VERSION}."
                    if turn
                    else f"Unmet. Need previous NI < 0 and latest NI > 0. Have {pair}. Rules v{NI_RULES_VERSION}."
                ),
                turn,
            )
        )
        improvement.append(
            _badge(
                NI_IMP_TO_LOSS,
                NI_IMP_LABELS,
                (
                    f"Previous quarter NI > 0 and latest NI < 0: {pair}. Rules v{NI_RULES_VERSION}."
                    if to_loss
                    else f"Unmet. Need previous NI > 0 and latest NI < 0. Have {pair}. Rules v{NI_RULES_VERSION}."
                ),
                to_loss,
            )
        )
    else:
        why = f"Unavailable. Latest and previous quarter NI must both be verified. Rules v{NI_RULES_VERSION}."
        improvement.append(_badge(NI_IMP_TURNAROUND, NI_IMP_LABELS, why, False))
        improvement.append(_badge(NI_IMP_TO_LOSS, NI_IMP_LABELS, why, False))

    if complete and values:
        seq = values[0] < values[1] < values[2] < values[3]
        improvement.append(
            _badge(
                NI_IMP_SEQ,
                NI_IMP_LABELS,
                (
                    f"Latest four NI amounts increase strictly oldest→newest: {listed}. Rules v{NI_RULES_VERSION}."
                    if seq
                    else f"Unmet. Need three consecutive increases across {listed}. Rules v{NI_RULES_VERSION}."
                ),
                seq,
            )
        )
    else:
        improvement.append(
            _badge(
                NI_IMP_SEQ,
                NI_IMP_LABELS,
                f"Unavailable. Needs four verified NI quarters. {counts_tip} Rules v{NI_RULES_VERSION}.",
                False,
            )
        )

    return {
        "concept": row.get("earningsConcept"),
        "quarters": quarters,
        "ttm": ttm,
        "ttmReason": None if complete else "insufficient_ni_window",
        "profitableCount": profitable,
        "lossCount": losses,
        "breakEvenCount": zeros,
        "latestIsLoss": latest_loss,
        "lossQuarters": loss_labels,
        "profitability": profitability,
        "improvement": improvement,
        "appliedProfitability": [b["id"] for b in profitability if b["applied"]],
        "appliedImprovement": [b["id"] for b in improvement if b["applied"]],
        "rulesVersion": NI_RULES_VERSION,
    }
