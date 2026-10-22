from datetime import date

from helpers import calendar_year, fact, quarters_from, timeline_values

from screener_pipeline.quarters import (
    MissingQuarter,
    Quarter,
    annual_check,
    build_timeline,
    dedupe_periods,
    derive_quarters,
)


def test_reported_quarters_and_q4_from_annual_minus_nine_months():
    facts = calendar_year(2024, 100, 110, 120, 130)
    qs = quarters_from(facts)
    q4 = qs[date(2024, 12, 31)]
    assert q4.val == 130
    assert q4.method == "derived"
    assert q4.formula == "FY − 9M YTD"
    assert (q4.fiscal_year, q4.fiscal_quarter) == (2024, 4)
    assert [s.sign for s in q4.sources] == [1, -1]
    assert qs[date(2024, 3, 31)].method == "reported"


def test_q2_q3_derived_from_year_to_date_when_only_ytd_is_reported():
    facts = calendar_year(2024, 100, 110, 120, 130, ytd_only=True)
    qs = quarters_from(facts)
    assert qs[date(2024, 6, 30)].val == 110
    assert qs[date(2024, 6, 30)].formula == "6M YTD − 3M"
    assert qs[date(2024, 9, 30)].val == 120
    assert qs[date(2024, 9, 30)].formula == "9M YTD − 6M YTD"
    assert qs[date(2024, 12, 31)].val == 130


def test_q4_from_annual_minus_three_quarters_when_no_nine_month_fact():
    facts = [
        fact("2024-01-01", "2024-03-31", 100, "q1", 2024, "Q1"),
        fact("2024-04-01", "2024-06-30", 110, "q2", 2024, "Q2"),
        fact("2024-07-01", "2024-09-30", 120, "q3", 2024, "Q3"),
        fact("2024-01-01", "2024-12-31", 460, "k", 2024, "FY", form="10-K", filed="2025-02-01"),
    ]
    q4 = quarters_from(facts)[date(2024, 12, 31)]
    assert q4.val == 130
    assert q4.formula == "FY − (Q1 + Q2 + Q3)"
    assert sum(s.sign * s.val for s in q4.sources) == 130


def test_q1_from_six_months_minus_q2_when_q1_filing_is_missing():
    facts = [
        fact("2026-04-01", "2026-06-30", 300, "q2", 2026, "Q2"),
        fact("2026-01-01", "2026-06-30", 550, "q2", 2026, "Q2"),
        fact("2025-10-01", "2025-12-31", 240, "k", 2025, "FY", form="10-K"),
    ]
    qs = quarters_from(facts)
    q1 = qs[date(2026, 3, 31)]
    assert q1.val == 250
    assert q1.formula == "6M YTD − Q2"
    assert q1.label_inferred
    assert (q1.fiscal_year, q1.fiscal_quarter) == (2026, 1)


def test_reported_value_wins_over_derivation_and_mismatch_is_flagged():
    m = 1_000_000
    facts = calendar_year(2024, 100 * m, 110 * m, 120 * m, 130 * m, reported_q4=True)
    facts.append(fact("2024-10-01", "2024-12-31", 131 * m, "late", 2025, "FY", form="10-K", filed="2026-02-15"))
    qs = quarters_from(facts)
    q4 = qs[date(2024, 12, 31)]
    assert q4.method == "reported"
    assert q4.val == 131 * m
    assert "derivation_mismatch" in q4.flags
    assert [a.val for a in q4.alternates] == [130 * m]


def test_restatement_latest_filing_wins_and_is_marked():
    facts = [
        fact("2024-01-01", "2024-03-31", 100_000, "orig", 2024, "Q1", filed="2024-05-01"),
        fact("2024-01-01", "2024-03-31", 90_000, "restate", 2025, "Q1", filed="2025-05-01"),
    ]
    p = dedupe_periods(facts)[(date(2024, 1, 1), date(2024, 3, 31))]
    assert p.val == 90_000
    assert p.restated
    assert p.accn == "restate"
    assert p.original_val == 100_000


def test_unchanged_comparative_cites_the_original_filing():
    facts = [
        fact("2024-01-01", "2024-03-31", 100_123, "orig", 2024, "Q1", filed="2024-05-01"),
        fact("2024-01-01", "2024-03-31", 100_123, "comparative", 2025, "Q1", filed="2025-05-01"),
    ]
    p = dedupe_periods(facts)[(date(2024, 1, 1), date(2024, 3, 31))]
    assert p.accn == "orig"
    assert not p.restated


def test_coarser_rounding_in_later_filing_keeps_precise_value():
    facts = [
        fact("2025-04-01", "2025-06-30", 166_496_000, "orig", 2025, "Q2", filed="2025-08-01"),
        fact("2025-01-01", "2025-06-30", 305_788_000, "orig", 2025, "Q2", filed="2025-08-01"),
        fact("2025-04-01", "2025-06-30", 167_000_000, "millions", 2026, "Q2", filed="2026-08-01"),
        fact("2025-01-01", "2025-06-30", 306_000_000, "millions", 2026, "Q2", filed="2026-08-01"),
        fact("2026-04-01", "2026-06-30", 214_000_000, "millions", 2026, "Q2", filed="2026-08-01"),
    ]
    periods = dedupe_periods(facts)
    p = periods[(date(2025, 4, 1), date(2025, 6, 30))]
    assert p.val == 166_496_000
    assert not p.restated


def test_round_number_does_not_hide_a_real_restatement():
    facts = [
        fact("2024-01-01", "2024-03-31", 2_000_345_000, "orig", 2024, "Q1", filed="2024-05-01"),
        fact("2024-01-01", "2024-03-31", 1_500_000_000, "restate", 2025, "Q1", filed="2025-05-01"),
        fact("2025-01-01", "2025-03-31", 1_612_345_000, "restate", 2025, "Q1", filed="2025-05-01"),
    ]
    p = dedupe_periods(facts)[(date(2024, 1, 1), date(2024, 3, 31))]
    assert p.val == 1_500_000_000
    assert p.restated


def test_fiscal_labels_come_from_filing_where_quarter_is_current_period():
    facts = calendar_year(2024, 100, 110, 120, 130)
    # The FY2025 Q1 10-Q repeats Q1 2024 as a comparative and Company Facts tags it fy=2025, fp=Q1.
    facts.append(fact("2024-01-01", "2024-03-31", 100, "A2025-1", 2025, "Q1", filed="2025-05-01"))
    facts.append(fact("2025-01-01", "2025-03-31", 105, "A2025-1", 2025, "Q1", filed="2025-05-01"))
    qs = quarters_from(facts)
    assert (qs[date(2024, 3, 31)].fiscal_year, qs[date(2024, 3, 31)].fiscal_quarter) == (2024, 1)
    assert (qs[date(2025, 3, 31)].fiscal_year, qs[date(2025, 3, 31)].fiscal_quarter) == (2025, 1)


def test_non_calendar_fiscal_year_ending_june():
    facts = [
        fact("2024-07-01", "2024-09-30", 10, "f1", 2025, "Q1"),
        fact("2024-10-01", "2024-12-31", 11, "f2", 2025, "Q2"),
        fact("2024-07-01", "2024-12-31", 21, "f2", 2025, "Q2"),
        fact("2025-01-01", "2025-03-31", 12, "f3", 2025, "Q3"),
        fact("2024-07-01", "2025-03-31", 33, "f3", 2025, "Q3"),
        fact("2024-07-01", "2025-06-30", 46, "fk", 2025, "FY", form="10-K", filed="2025-08-20"),
    ]
    qs = quarters_from(facts)
    q4 = qs[date(2025, 6, 30)]
    assert q4.val == 13
    assert (q4.fiscal_year, q4.fiscal_quarter) == (2025, 4)
    assert (qs[date(2024, 9, 30)].fiscal_year, qs[date(2024, 9, 30)].fiscal_quarter) == (2025, 1)


def test_52_53_week_fiscal_year():
    facts = [
        fact("2023-12-31", "2024-03-30", 10, "w1", 2024, "Q1"),
        fact("2024-03-31", "2024-06-29", 11, "w2", 2024, "Q2"),
        fact("2023-12-31", "2024-06-29", 21, "w2", 2024, "Q2"),
        fact("2024-06-30", "2024-09-28", 12, "w3", 2024, "Q3"),
        fact("2023-12-31", "2024-09-28", 33, "w3", 2024, "Q3"),
        fact("2023-12-31", "2024-12-28", 47, "wk", 2024, "FY", form="10-K", filed="2025-02-20"),
        fact("2024-12-29", "2025-03-29", 15, "w5", 2025, "Q1"),
    ]
    qs = quarters_from(facts)
    assert qs[date(2024, 12, 28)].val == 14
    slots = build_timeline(qs)
    assert [s.val for s in slots] == [15, 14, 12, 11, 10]


def test_gap_becomes_missing_slot_and_trailing_missing_is_trimmed():
    facts = [
        fact("2025-07-01", "2025-09-30", 30, "a3", 2025, "Q3"),
        fact("2025-01-01", "2025-03-31", 10, "a1", 2025, "Q1"),
    ]
    slots = build_timeline(quarters_from(facts))
    assert isinstance(slots[0], Quarter) and slots[0].val == 30
    assert isinstance(slots[1], MissingQuarter)
    assert slots[1].end == date(2025, 6, 30)
    assert (slots[1].fiscal_year, slots[1].fiscal_quarter) == (2025, 2)
    assert isinstance(slots[2], Quarter) and slots[2].val == 10
    assert len(slots) == 3


def test_timeline_is_limited_to_twelve_newest_first():
    facts = []
    for y in range(2021, 2025):
        facts += calendar_year(y, 1 + y, 2 + y, 3 + y, 4 + y, prefix=str(y))
    values = timeline_values(facts)
    assert len(values) == 12
    assert values[0] == 4 + 2024
    assert values[-1] == 1 + 2022


def test_negative_derived_quarter_is_flagged_not_hidden():
    facts = calendar_year(2023, 10, 10, 18, -2)
    q4 = quarters_from(facts)[date(2023, 12, 31)]
    assert q4.val == -2
    assert "negative_value" in q4.flags


def test_annual_check_flags_quarters_not_summing_to_annual():
    m = 1_000_000
    facts = calendar_year(2024, 100 * m, 110 * m, 120 * m, 130 * m, reported_q4=True)
    facts = [f for f in facts if not (f.form == "10-K" and f.days > 300)]
    facts.append(fact("2024-01-01", "2024-12-31", 999 * m, "A2024-K", 2024, "FY", form="10-K", filed="2025-02-15"))
    periods = dedupe_periods(facts)
    qs = derive_quarters(periods, "Revenues")
    assert annual_check(qs, periods) == [date(2024, 12, 31)]


def test_facts_from_other_forms_are_ignored():
    from helpers import companyfacts, raw

    from screener_pipeline.sec.facts import extract_revenue_facts

    cf = companyfacts(
        {
            "Revenues": [
                raw("2024-01-01", "2024-03-31", 100, "x", 2024, "Q1"),
                raw("2024-01-01", "2024-03-31", 999, "s1", 2024, "Q1", form="S-1"),
                raw("2024-01-01", "2024-03-31", 888, "8k", 2024, "Q1", form="8-K"),
            ]
        }
    )
    rf = extract_revenue_facts(cf)
    assert sorted(f.val for f in rf.by_concept["Revenues"]) == [100, 888]


def test_later_ten_q_wins_same_period_as_eight_k():
    facts = [
        fact("2026-07-01", "2026-09-30", 888, "8k", 2026, "Q3", form="8-K", filed="2026-10-21"),
        fact("2026-07-01", "2026-09-30", 100, "10q", 2026, "Q3", form="10-Q", filed="2026-10-30"),
    ]
    period = dedupe_periods(facts)[(date(2026, 7, 1), date(2026, 9, 30))]
    assert period.val == 100
    assert period.form == "10-Q"
    assert period.accn == "10q"


def test_ten_q_supersedes_nearby_eight_k_rounding():
    facts = [
        fact("2026-07-01", "2026-09-30", 51_242_000_000, "8k", 2026, "Q3", form="8-K", filed="2026-10-21"),
        fact("2026-07-01", "2026-09-30", 51_240_000_000, "10q", 2026, "Q3", form="10-Q", filed="2026-10-30"),
    ]
    period = dedupe_periods(facts)[(date(2026, 7, 1), date(2026, 9, 30))]
    assert period.val == 51_240_000_000
    assert period.form == "10-Q"
