from __future__ import annotations

from datetime import date
from pathlib import Path

from screener_pipeline.layer2 import (
    BUCKET_DATA_REVIEW,
    BUCKET_PASSED,
    BUCKET_TTM_NONPOSITIVE,
    BUCKET_WATCHLIST,
    CAT_ACCEL,
    CAT_DECLINE,
    CAT_FOUR_POS,
    CAT_JUMP,
    CAT_OTHER,
    CAT_STABLE,
    CAT_UNABLE,
    CAT_VOL,
    REASON_FILING_NO_REVENUE,
    REASON_FILING_UNPARSED,
    REASON_QUARTER_NOT_IN_WINDOW,
    RULES_VERSION,
    Thresholds,
    analyze_company,
    assess_freshness,
    build_layer2,
    classify_qoq_badges,
    pct_change,
)


def q(fy, fq, end, value, *, check="match", concept="Revenues", missing=False):
    if missing:
        return {
            "fiscalYear": fy,
            "fiscalQuarter": fq,
            "start": None,
            "end": end,
            "missing": True,
            "value": None,
            "concept": concept,
            "check": None,
            "url": None,
            "form": None,
        }
    return {
        "fiscalYear": fy,
        "fiscalQuarter": fq,
        "start": end,
        "end": end,
        "missing": False,
        "value": value,
        "concept": concept,
        "form": "10-Q",
        "url": f"https://example.test/{end}",
        "check": {"status": check, "url": f"https://example.test/{end}"},
    }


def eight_quarters(values: list[float], *, fy0=2026, check="match", concept="Revenues"):
    """Newest-first 8 quarters. values[0] is latest. Default calendar-like FY/Q labels, but FY can start in July."""
    out = []
    fy, fq = fy0, 2
    for v in values:
        out.append(q(fy, fq, f"{fy}-{fq * 3:02d}-28", v, check=check, concept=concept))
        fq -= 1
        if fq == 0:
            fq = 4
            fy -= 1
    return out


def company(values, *, ttm_growth, name="Test Co", ticker="TST", **kw):
    checks = kw.pop("check", "match")
    concept = kw.pop("concept", "Revenues")
    qs = eight_quarters(values, check=checks, concept=concept)
    for k, patch in kw.items():
        if k.startswith("q") and k[1:].isdigit():
            qs[int(k[1:])] = patch
    return {
        "schemaVersion": 2,
        "ticker": ticker,
        "name": name,
        "exchange": "NASDAQ",
        "securityType": "common",
        "sic": {"code": "2834", "majorGroup": "Chemicals", "label": "2834 — Pharma"},
        "ttm": {"current": 1, "previous": 1, "growthPct": ttm_growth, "reason": None, "currency": "USD"},
        "revenue": {"currency": "USD", "concept": "Revenues", "quarters": qs},
    }


def applied(row):
    return {b["id"] for b in row["badges"] if b["applied"]}


def test_rules_version_is_set():
    assert RULES_VERSION == 4


def test_stale_official_filing_is_not_passed_or_watchlist():
    values = [104, 106, 108, 110, 100, 100, 100, 100]
    parsed = company(values, ttm_growth=7.0, q0=q(2025, 1, "2025-03-31", 104))
    parsed["revenue"]["edgarSupplement"] = {
        "status": "unresolved",
        "newerFilings": [{"accn": "a", "form": "10-Q", "filed": "2026-08-13", "reportDate": "2026-06-30"}],
        "unresolved": [{"accn": "a", "reason": "income_statement_unavailable"}],
        "applied": [],
    }
    row = analyze_company(parsed, Thresholds(None, None))
    assert row["bucket"] == BUCKET_DATA_REVIEW
    assert REASON_FILING_UNPARSED in row["dataReviewReasons"]

    no_rev = company(values, ttm_growth=7.0, q0=q(2020, 4, "2020-12-31", 104))
    no_rev["revenue"]["edgarSupplement"] = {
        "status": "current",
        "newerFilings": [{"accn": "b", "form": "10-Q", "filed": "2026-07-31", "reportDate": "2026-06-30"}],
        "unresolved": [{"accn": "b", "reason": "no_official_revenue_column"}],
        "applied": [],
    }
    row = analyze_company(no_rev, Thresholds(None, None))
    assert row["bucket"] == BUCKET_DATA_REVIEW
    assert REASON_FILING_NO_REVENUE in row["dataReviewReasons"]

    applied_missing = company(values, ttm_growth=7.0, q0=q(2026, 1, "2026-03-31", 104))
    applied_missing["revenue"]["edgarSupplement"] = {
        "status": "applied",
        "newerFilings": [{"accn": "c", "form": "10-Q", "filed": "2026-07-29", "reportDate": "2026-07-03"}],
        "unresolved": [],
        "applied": [{"accn": "c", "end": "2026-07-03", "months": 3, "value": 1.0}],
    }
    row = analyze_company(applied_missing, Thresholds(None, None))
    assert row["bucket"] == BUCKET_DATA_REVIEW
    assert REASON_QUARTER_NOT_IN_WINDOW in row["dataReviewReasons"]


def test_four_positive_yoy_passes_even_if_decelerating():
    # Newest-first values: latest YoY is 104/100, oldest of the four is 110/100 → decelerating, all > 0.
    values = [104, 106, 108, 110, 100, 100, 100, 100]
    row = analyze_company(company(values, ttm_growth=7.0), Thresholds(None, None))
    rates = [e["rate"] for e in row["yoy"]]
    assert row["bucket"] == BUCKET_PASSED
    assert all(r > 0 for r in rates)
    assert rates[0] > rates[-1]


def test_negative_or_zero_yoy_is_watchlist():
    # One YoY exactly 0: 100/100
    values = [110, 100, 106, 104, 100, 100, 100, 100]
    row = analyze_company(company(values, ttm_growth=5.0), Thresholds(None, None))
    assert row["bucket"] == BUCKET_WATCHLIST
    assert any(e["rate"] == 0 for e in row["yoy"])

    values = [110, 90, 106, 104, 100, 100, 100, 100]
    row = analyze_company(company(values, ttm_growth=4.0), Thresholds(None, None))
    assert row["bucket"] == BUCKET_WATCHLIST
    assert any(e["rate"] < 0 for e in row["yoy"])


def test_missing_unverified_incomparable_is_data_review():
    base = [110, 108, 106, 104, 100, 100, 100, 100]
    missing = company(base, ttm_growth=8.0, q1=q(2026, 1, "2026-03-28", None, missing=True))
    assert analyze_company(missing, Thresholds(None, None))["bucket"] == BUCKET_DATA_REVIEW

    unverified = company(base, ttm_growth=8.0)
    unverified["revenue"]["quarters"][0]["check"] = {"status": "mismatch"}
    assert analyze_company(unverified, Thresholds(None, None))["bucket"] == BUCKET_DATA_REVIEW

    layer1_blocked = company(base, ttm_growth=None)
    layer1_blocked["ttm"]["reason"] = "unverified_quarters"
    layer1_blocked["revenue"]["quarters"][0]["check"] = {"status": "unavailable"}
    blocked_row = analyze_company(layer1_blocked, Thresholds(None, None))
    assert blocked_row["bucket"] == BUCKET_DATA_REVIEW
    assert blocked_row["bucket"] not in {BUCKET_PASSED, BUCKET_WATCHLIST}

    other = company(base, ttm_growth=8.0)
    other["revenue"]["quarters"][4]["concept"] = "SalesRevenueNet"
    assert analyze_company(other, Thresholds(None, None))["bucket"] == BUCKET_DATA_REVIEW

    none_ttm = company(base, ttm_growth=None)
    none_ttm["ttm"]["reason"] = "foreign_filer"
    none_ttm["revenue"]["quarters"] = []
    assert analyze_company(none_ttm, Thresholds(None, None))["bucket"] == BUCKET_DATA_REVIEW


def test_nonpositive_denominator_is_na_never_zero():
    rate, reason = pct_change(50.0, 0.0)
    assert rate is None and reason == "nonpositive_denominator"
    rate, reason = pct_change(50.0, -10.0)
    assert rate is None and reason == "nonpositive_denominator"

    values = [110, 108, 106, 104, 100, 0, 100, 100]
    row = analyze_company(company(values, ttm_growth=5.0), Thresholds(None, None))
    assert row["bucket"] == BUCKET_DATA_REVIEW
    assert any(e["reason"] == "nonpositive_denominator" for e in row["yoy"])
    assert all(e["rate"] != 0 or e["reason"] is None for e in row["yoy"])


def test_valid_nonpositive_ttm_is_not_data_review():
    values = [90, 90, 90, 90, 100, 100, 100, 100]
    row = analyze_company(company(values, ttm_growth=-10.0), Thresholds(None, None))
    assert row["bucket"] == BUCKET_TTM_NONPOSITIVE
    assert row["bucket"] != BUCKET_DATA_REVIEW


def test_qoq_decline_does_not_remove_yoy_pass():
    # YoY all positive; latest QoQ negative: 90 vs previous 110
    values = [90, 110, 100, 95, 80, 80, 80, 80]
    row = analyze_company(company(values, ttm_growth=20.0), Thresholds(None, None))
    assert row["bucket"] == BUCKET_PASSED
    assert CAT_DECLINE in applied(row)
    assert row["qoq"][-1]["rate"] < 0


def test_overlapping_category_badges():
    # Alternating signs ending negative: +10, -10, +10, -20 → vol + decline
    rates = [10.0, -10.0, 10.0, -20.0]
    badges = classify_qoq_badges(rates, Thresholds(5.0, 50.0))
    ids = {b["id"] for b in badges if b["applied"]}
    assert CAT_VOL in ids
    assert CAT_DECLINE in ids

    # All positive strictly increasing: accel. With large spread, not stable. With jump threshold 0.5 may also jump.
    rates = [1.0, 2.0, 3.0, 20.0]
    badges = classify_qoq_badges(rates, Thresholds(100.0, 10.0))
    ids = {b["id"] for b in badges if b["applied"]}
    assert CAT_ACCEL in ids
    assert CAT_FOUR_POS in ids
    assert CAT_STABLE in ids
    assert CAT_JUMP in ids


def test_threshold_boundaries_and_unconfigured():
    rates = [5.0, 5.0, 5.0, 8.0]
    none = classify_qoq_badges(rates, Thresholds(None, None))
    blocked = {b["id"]: b for b in none if b["blockedByThreshold"]}
    assert CAT_STABLE in blocked and not blocked[CAT_STABLE]["applied"]
    assert CAT_JUMP in blocked and not blocked[CAT_JUMP]["applied"]
    assert "Threshold not configured" in blocked[CAT_STABLE]["tooltip"]
    assert "Threshold not configured" in blocked[CAT_JUMP]["tooltip"]

    # spread 3.0: max-min = 3.0 → inclusive pass; 2.999 fail
    at = classify_qoq_badges(rates, Thresholds(3.0, None))
    assert any(b["id"] == CAT_STABLE and b["applied"] for b in at)
    below = classify_qoq_badges(rates, Thresholds(2.999, None))
    assert not any(b["id"] == CAT_STABLE and b["applied"] for b in below)

    # jump: 8 - max(5,5,5) = 3. Inclusive at 3, fail at 3.0001
    jump_ok = classify_qoq_badges(rates, Thresholds(None, 3.0))
    assert any(b["id"] == CAT_JUMP and b["applied"] for b in jump_ok)
    jump_no = classify_qoq_badges(rates, Thresholds(None, 3.0001))
    assert not any(b["id"] == CAT_JUMP and b["applied"] for b in jump_no)


def test_latest_decline_does_not_need_earlier_qoq():
    badges = classify_qoq_badges([None, None, None, -1.0], Thresholds(None, None))
    ids = {b["id"] for b in badges if b["applied"]}
    assert CAT_DECLINE in ids
    assert CAT_UNABLE not in ids


def test_other_flat_and_unable():
    unconfigured = classify_qoq_badges([1.0, 1.0, 1.0, 1.0], Thresholds(None, None))
    assert not any(b["id"] == CAT_OTHER and b["applied"] for b in unconfigured)
    assert not any(b["id"] == CAT_UNABLE and b["applied"] for b in unconfigured)

    incomplete = classify_qoq_badges([None, None, 1.0, 1.0], Thresholds(None, None))
    assert any(b["id"] == CAT_UNABLE and b["applied"] for b in incomplete)
    assert not any(b["id"] == CAT_OTHER and b["applied"] for b in incomplete)

    four = classify_qoq_badges([1.0, 1.0, 1.0, 1.0], Thresholds(None, None))
    assert any(b["id"] == CAT_FOUR_POS and b["applied"] for b in four)

    # Thresholds evaluated; not all positive, not a decline, one sign change, no jump.
    other = classify_qoq_badges([5.0, 5.0, 5.0, 0.0], Thresholds(0.5, 10.0))
    assert any(b["id"] == CAT_OTHER and b["applied"] for b in other)
    assert not any(b["id"] == CAT_FOUR_POS and b["applied"] for b in other)


def test_non_calendar_fiscal_year_labels():
    """FY ending 30 June: Q1 is Jul–Sep. Labels come from Layer 1, not calendar months."""
    qs = [
        q(2026, 4, "2026-06-30", 40),
        q(2026, 3, "2026-03-31", 30),
        q(2026, 2, "2025-12-31", 20),
        q(2026, 1, "2025-09-30", 10),
        q(2025, 4, "2025-06-30", 8),
        q(2025, 3, "2025-03-31", 6),
        q(2025, 2, "2024-12-31", 4),
        q(2025, 1, "2024-09-30", 2),
    ]
    c = company([1] * 8, ttm_growth=50.0)
    c["revenue"]["quarters"] = qs
    row = analyze_company(c, Thresholds(None, None))
    assert row["bucket"] == BUCKET_PASSED
    assert row["yoy"][0]["label"] == "FY2026 Q1"
    assert row["yoy"][0]["end"] == "2025-09-30"
    assert row["yoy"][-1]["label"] == "FY2026 Q4"
    assert row["qoq"][0]["label"] == "FY2026 Q1"
    assert row["qoq"][-1]["label"] == "FY2026 Q4"
    # YoY uses same fiscal quarter prior year
    assert row["yoy"][-1]["otherValue"] == 8  # FY2025 Q4


def test_sample_dataset_buckets_from_layer1_json():
    """Layer 2 on the frozen validation sample must not re-fetch revenue."""
    data_dir = Path(__file__).resolve().parent / "fixtures" / "sample-data"
    payload = build_layer2(data_dir, Thresholds(None, None))
    by = {r["ticker"]: r for r in payload["rows"]}
    assert payload["counts"] == {
        "passed": 11,
        "watchlist": 3,
        "dataReview": 3,
        "ttmNonpositive": 5,
        "listings": 22,
    }
    assert by["INCY"]["bucket"] == BUCKET_PASSED
    assert any(e["rate"] is not None and e["rate"] < 0 for e in by["INCY"]["qoq"])
    assert by["BEAM"]["bucket"] == BUCKET_WATCHLIST
    assert by["RARE"]["bucket"] == BUCKET_WATCHLIST
    assert by["NTLA"]["bucket"] == BUCKET_WATCHLIST
    assert by["ARWR"]["bucket"] == BUCKET_DATA_REVIEW
    assert by["ARGX"]["bucket"] == BUCKET_DATA_REVIEW
    assert by["BNTX"]["bucket"] == BUCKET_DATA_REVIEW
    assert by["IONS"]["bucket"] == BUCKET_TTM_NONPOSITIVE
    assert all(b["blockedByThreshold"] for b in by["INSM"]["badges"] if b["id"] in {CAT_STABLE, CAT_JUMP})
    assert CAT_OTHER not in applied(by["INSM"])
    assert CAT_OTHER not in applied(by["KRYS"])
    assert CAT_FOUR_POS in applied(by["KRYS"])
    assert CAT_FOUR_POS in applied(by["INSM"])
    assert CAT_FOUR_POS not in applied(by["INCY"])
    assert by["INCY"]["freshness"]["status"] == "current"
    assert by["INCY"]["yoy"][-1]["end"] == "2026-06-30"
    assert by["KRYS"]["freshness"]["status"] == "current"
    assert CAT_OTHER not in applied(by["ARGX"])
    assert CAT_UNABLE in applied(by["ARGX"])


def test_committed_pages_payload_is_full_universe_with_gate():
    """Pages deploy reads committed web/public/data; full mode requires gate.ok."""
    import json

    data_dir = Path(__file__).resolve().parents[2] / "web" / "public" / "data"
    meta = json.loads((data_dir / "meta.json").read_text())
    layer2 = json.loads((data_dir / "layer2.json").read_text())
    assert meta["dataset"]["mode"] == "full"
    assert meta["gate"]["ok"] is True
    assert meta["coverage"]["listings"] == 5593
    assert layer2["counts"] == {
        "passed": 1445,
        "watchlist": 693,
        "dataReview": 2631,
        "ttmNonpositive": 824,
        "listings": 5593,
    }
    assert layer2["rulesVersion"] == RULES_VERSION
    by = {r["ticker"]: r for r in layer2["rows"]}
    assert by["INCY"]["bucket"] == BUCKET_PASSED
    assert by["INCY"]["freshness"]["status"] == "current"
    assert by["AMH"]["bucket"] == BUCKET_DATA_REVIEW
    assert REASON_FILING_NO_REVENUE in by["AMH"]["dataReviewReasons"]
    assert by["GYRO"]["bucket"] == BUCKET_DATA_REVIEW
    assert REASON_FILING_UNPARSED in by["GYRO"]["dataReviewReasons"]
    assert by["KO"]["bucket"] == BUCKET_DATA_REVIEW
    assert REASON_QUARTER_NOT_IN_WINDOW in by["KO"]["dataReviewReasons"]
    stale_pw = [
        r["ticker"]
        for r in layer2["rows"]
        if r["bucket"] in {BUCKET_PASSED, BUCKET_WATCHLIST}
        and any(str(x).startswith("official_") for x in r["dataReviewReasons"])
    ]
    assert stale_pw == []


def test_freshness_distinguishes_verified_window_from_expected_next():
    window = [
        q(2026, 1, "2026-03-31", 100),
        q(2025, 4, "2025-12-31", 90),
        q(2025, 3, "2025-09-30", 80),
        q(2025, 2, "2025-06-30", 70),
        q(2025, 1, "2025-03-31", 60),
        q(2024, 4, "2024-12-31", 50),
        q(2024, 3, "2024-09-30", 40),
        q(2024, 2, "2024-06-30", 30),
    ]
    lagging = assess_freshness(window, date(2026, 10, 14))
    assert lagging["status"] == "verified_lagging"
    assert lagging["window"] == "verified_historical"
    assert lagging["latestVerified"]["label"] == "FY2026 Q1"
    assert lagging["expectedNext"]["label"] == "FY2026 Q2"
    assert lagging["expectedNext"]["end"] == "2026-06-30"
    assert lagging["expectedNext"]["form"] == "10-Q"
    assert "verified historical" in lagging["message"]

    current = assess_freshness(
        [q(2026, 2, "2026-06-30", 100)] + window[1:],
        date(2026, 10, 14),
    )
    assert current["status"] == "current"
    assert current["latestVerified"]["label"] == "FY2026 Q2"


def test_unrounded_decisions_not_display_rounding():
    # 0.0000001% is still > 0 → Passed, not Watchlist
    values = [100.0000001, 100.0000001, 100.0000001, 100.0000001, 100, 100, 100, 100]
    row = analyze_company(company(values, ttm_growth=0.0000001), Thresholds(None, None))
    assert row["bucket"] == BUCKET_PASSED
    assert all(e["rate"] > 0 for e in row["yoy"])


def test_earnings_detail_does_not_change_bucket():
    c = company([12, 11, 11, 11, 10, 10, 10, 10], ttm_growth=20.0)
    c["earnings"] = {
        "concept": "NetIncomeLoss",
        "quarters": eight_quarters([-5, -4, -3, -2, -1, -1, -1, -1], concept="NetIncomeLoss"),
    }
    row = analyze_company(c, Thresholds(None, None))
    assert row["bucket"] == BUCKET_PASSED
    assert row["earningsConcept"] == "NetIncomeLoss"
    assert len(row["earningsYoy"]) == 4
    assert all(e["reason"] == "nonpositive_denominator" for e in row["earningsYoy"])
    assert all(e["rate"] is None for e in row["earningsYoy"])
