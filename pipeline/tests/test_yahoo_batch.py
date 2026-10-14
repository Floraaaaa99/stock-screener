from __future__ import annotations

from screener_pipeline.yahoo import batch_row_error, implied_market_cap, summarize_batch_comparison


def test_implied_market_cap_and_missing():
    assert implied_market_cap(10, 100) == 1000
    assert implied_market_cap(None, 100) is None
    assert implied_market_cap(10, 0) is None


def test_batch_row_error():
    assert batch_row_error(100, 101) == 0.01
    assert batch_row_error(None, 100) is None
    assert batch_row_error(0, 10) is None


def test_summarize_does_not_adopt_small_or_inaccurate_samples():
    close = [{"relError": 0.001} for _ in range(12)]
    adopted = summarize_batch_comparison(close)
    assert adopted["adopt"] is True

    small = [{"relError": 0.001} for _ in range(5)]
    assert summarize_batch_comparison(small)["adopt"] is False

    noisy = [{"relError": 0.20} for _ in range(12)]
    out = summarize_batch_comparison(noisy)
    assert out["adopt"] is False
    assert "not accurate" in out["reason"]
