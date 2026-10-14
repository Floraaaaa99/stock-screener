from datetime import date, timedelta

import pytest

from screener_pipeline.quarters import MissingQuarter, Quarter
from screener_pipeline.ttm import compute_ttm


def slots(values):
    out = []
    end = date(2026, 6, 30)
    for v in values:
        start = end - timedelta(days=90)
        if v is None:
            out.append(MissingQuarter(start, end))
        else:
            out.append(Quarter(start, end, float(v), "reported", "3M reported", [], "Revenues"))
        end = start - timedelta(days=1)
    return out


def test_growth_from_eight_consecutive_quarters():
    r = compute_ttm(slots([40, 30, 20, 10, 25, 20, 15, 10, 1, 1, 1, 1]))
    assert r.current == 100
    assert r.previous == 70
    assert r.growth_pct == pytest.approx((100 / 70 - 1) * 100)
    assert r.reason is None


def test_negative_growth():
    r = compute_ttm(slots([10, 10, 10, 10, 20, 20, 20, 20]))
    assert r.growth_pct == pytest.approx(-50.0)


def test_gap_in_current_ttm_gives_na_not_zero():
    r = compute_ttm(slots([40, None, 20, 10, 25, 20, 15, 10]))
    assert r.current is None and r.previous is None and r.growth_pct is None
    assert r.reason == "gap_in_quarters"


def test_gap_in_previous_ttm_keeps_current_but_no_growth():
    r = compute_ttm(slots([40, 30, 20, 10, 25, None, 15, 10]))
    assert r.current == 100
    assert r.previous is None
    assert r.growth_pct is None
    assert r.reason == "gap_in_quarters"


def test_fewer_than_eight_quarters():
    r = compute_ttm(slots([40, 30, 20, 10, 25]))
    assert r.current == 100
    assert r.growth_pct is None
    assert r.reason == "insufficient_quarters"
    assert compute_ttm(slots([1, 2])).reason == "insufficient_quarters"


@pytest.mark.parametrize("previous", [[0, 0, 0, 0], [5, -10, 2, 1]])
def test_previous_ttm_not_positive_gives_na(previous):
    r = compute_ttm(slots([10, 10, 10, 10, *previous]))
    assert r.current == 40
    assert r.growth_pct is None
    assert r.reason == "previous_ttm_not_positive"


def test_blocking_reason_suppresses_all_values():
    r = compute_ttm(slots([10] * 8), "ambiguous_concept")
    assert (r.current, r.previous, r.growth_pct, r.reason) == (None, None, None, "ambiguous_concept")
