from test_layer2 import company, eight_quarters

from screener_pipeline.layer2 import BUCKET_PASSED, Thresholds, analyze_company
from screener_pipeline.ni import (
    NI_IMP_FOUR_YOY,
    NI_IMP_SEQ,
    NI_IMP_TO_LOSS,
    NI_IMP_TURNAROUND,
    NI_PROF_ALL,
    NI_PROF_ALL_LOSS,
    NI_PROF_BREAKEVEN,
    NI_PROF_INSUFFICIENT,
    NI_PROF_ONE_LOSS,
    analyze_net_income,
)


def rate(end, label, current, prior, fy=2026, fq=2, check="match", other_check="match"):
    return {
        "fiscalYear": fy,
        "fiscalQuarter": fq,
        "end": end,
        "label": label,
        "rate": None,
        "reason": None,
        "kind": "yoy",
        "currentValue": current,
        "otherValue": prior,
        "absoluteChange": None if current is None or prior is None else current - prior,
        "currentUrl": "https://ex",
        "otherUrl": "https://ex",
        "currentForm": "10-Q",
        "otherForm": "10-Q",
        "currentCheck": check,
        "otherCheck": other_check,
    }


def l2_row(values, priors):
    yoy = [
        rate("2025-09-30", "FY2026 Q1", values[0], priors[0], fq=1),
        rate("2025-12-31", "FY2026 Q2", values[1], priors[1], fq=2),
        rate("2026-03-31", "FY2026 Q3", values[2], priors[2], fq=3),
        rate("2026-06-30", "FY2026 Q4", values[3], priors[3], fq=4),
    ]
    return {"yoy": yoy, "earningsYoy": yoy, "earningsQoq": yoy, "earningsConcept": "NetIncomeLoss"}


def applied(ni, key="profitability"):
    return [b["id"] for b in ni[key] if b["applied"]]


def test_all_profitable_ttm_sum():
    ni = analyze_net_income(l2_row([10, 20, 30, 40], [5, 6, 7, 8]))
    assert ni["ttm"] == 100
    assert applied(ni) == [NI_PROF_ALL]


def test_one_historical_loss_vs_latest_loss():
    hist = analyze_net_income(l2_row([10, -2, 30, 40], [5, 6, 7, 8]))
    assert applied(hist) == [NI_PROF_ONE_LOSS]
    assert hist["lossQuarters"] == ["FY2026 Q2"]
    assert hist["latestIsLoss"] is False
    latest = analyze_net_income(l2_row([10, 20, 30, -4], [5, 6, 7, 8]))
    assert latest["lossQuarters"] == ["FY2026 Q4"]
    assert latest["latestIsLoss"] is True


def test_break_even_additional_badge():
    ni = analyze_net_income(l2_row([10, 0, 30, 40], [5, 6, 7, 8]))
    assert ni["breakEvenCount"] == 1
    assert ni["lossCount"] == 0
    assert applied(ni) == [NI_PROF_BREAKEVEN]


def test_unverified_is_not_zero():
    row = l2_row([10, 20, 30, 40], [5, 6, 7, 8])
    row["earningsYoy"][3]["currentCheck"] = "unavailable"
    ni = analyze_net_income(row)
    assert ni["ttm"] is None
    assert applied(ni) == [NI_PROF_INSUFFICIENT]


def test_narrowing_losses_are_improvement():
    ni = analyze_net_income(l2_row([-8, -6, -4, -2], [-20, -18, -16, -14]))
    assert NI_IMP_FOUR_YOY in applied(ni, "improvement")
    assert NI_IMP_SEQ in applied(ni, "improvement")
    assert applied(ni) == [NI_PROF_ALL_LOSS]


def test_turnaround_independent_of_yoy():
    ni = analyze_net_income(l2_row([5, 6, -3, 4], [9, 9, 9, 9]))
    assert NI_IMP_TURNAROUND in applied(ni, "improvement")
    assert NI_IMP_FOUR_YOY not in applied(ni, "improvement")
    assert NI_IMP_TO_LOSS not in applied(ni, "improvement")


def test_turned_to_loss():
    ni = analyze_net_income(l2_row([5, 6, 7, -1], [1, 1, 1, 1]))
    assert NI_IMP_TO_LOSS in applied(ni, "improvement")


def test_unavailable_rule_does_not_block_others():
    row = l2_row([5, 6, -3, 4], [1, 1, 1, 1])
    row["earningsYoy"][0]["otherValue"] = None
    row["earningsYoy"][0]["otherCheck"] = None
    ni = analyze_net_income(row)
    four = next(b for b in ni["improvement"] if b["id"] == NI_IMP_FOUR_YOY)
    assert four["applied"] is False
    assert "Unavailable" in four["tooltip"]
    assert NI_IMP_TURNAROUND in applied(ni, "improvement")


def test_profitable_but_declining():
    ni = analyze_net_income(l2_row([40, 30, 20, 10], [50, 40, 30, 20]))
    assert applied(ni) == [NI_PROF_ALL]
    assert NI_IMP_FOUR_YOY not in applied(ni, "improvement")
    assert NI_IMP_SEQ not in applied(ni, "improvement")
    assert ni["ttm"] == 100


def test_empty_window_is_insufficient_not_improved():
    ni = analyze_net_income({"yoy": [], "earningsYoy": []})
    assert applied(ni) == [NI_PROF_INSUFFICIENT]
    four = next(b for b in ni["improvement"] if b["id"] == NI_IMP_FOUR_YOY)
    assert four["applied"] is False
    assert "Unavailable" in four["tooltip"]


def test_analyze_company_still_revenue_passed():
    c = company([12, 11, 11, 11, 10, 10, 10, 10], ttm_growth=20.0)
    c["earnings"] = {
        "concept": "NetIncomeLoss",
        "quarters": eight_quarters([-5, -4, -3, -2, -1, -1, -1, -1], concept="NetIncomeLoss"),
    }
    row = analyze_company(c, Thresholds(None, None))
    assert row["bucket"] == BUCKET_PASSED
    assert row["ni"]["ttm"] == -5 + -4 + -3 + -2
    assert NI_PROF_ALL_LOSS in row["ni"]["appliedProfitability"]


def test_ni_recomputes_when_filings_change_without_touching_bucket():
    c = company([12, 11, 11, 11, 10, 10, 10, 10], ttm_growth=20.0)
    c["earnings"] = {
        "concept": "NetIncomeLoss",
        "quarters": eight_quarters([10, 10, 10, 10, 1, 1, 1, 1], concept="NetIncomeLoss"),
    }
    first = analyze_company(c, Thresholds(None, None))
    assert first["bucket"] == BUCKET_PASSED
    assert NI_PROF_ALL in first["ni"]["appliedProfitability"]
    c["earnings"]["quarters"] = eight_quarters([-1, 10, 10, 10, 1, 1, 1, 1], concept="NetIncomeLoss")
    second = analyze_company(c, Thresholds(None, None))
    assert second["bucket"] == BUCKET_PASSED
    assert second["ni"]["latestIsLoss"] is True
    assert NI_PROF_ONE_LOSS in second["ni"]["appliedProfitability"]
