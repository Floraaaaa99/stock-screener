from __future__ import annotations

from pathlib import Path

import pytest

from screener_pipeline.build import IncompleteRun, build, read_sample
from screener_pipeline.universe.nasdaq_trader import Listing


def _listing(symbol: str) -> Listing:
    return Listing(
        symbol=symbol,
        raw_symbol=symbol,
        name=f"{symbol} Inc.",
        exchange="NASDAQ",
        exchange_code="Q",
        security_type="common",
        nasdaq_tier="Global Select",
        financial_status="N",
    )


def stub_offline_sources(monkeypatch) -> None:
    """CI has no NASDAQ/SEC cache; these tests only care that live output is not replaced."""
    tickers, _ = read_sample("biotech20")
    listings = [_listing(t) for t in tickers]
    monkeypatch.setattr(
        "screener_pipeline.build.load_universe",
        lambda offline=False: (listings, [], {"nasdaqlisted": "1014202614:01", "otherlisted": "1014202614:01"}),
    )
    monkeypatch.setattr("screener_pipeline.build.SecClient.ticker_map", lambda self: {})


def test_time_budget_does_not_replace_live_dataset(tmp_path: Path, monkeypatch):
    stub_offline_sources(monkeypatch)
    live = tmp_path / "data"
    live.mkdir()
    (live / "keep.txt").write_text("stage1")
    with pytest.raises(IncompleteRun, match="Time budget reached"):
        build(
            "sample:biotech20",
            offline=True,
            verify_quarters=False,
            output_dir=live,
            state_dir=tmp_path / "state",
            time_budget_s=0,
            use_bulk=False,
        )
    assert (live / "keep.txt").read_text() == "stage1"
    assert (tmp_path / "state" / "progress.json").exists()


def test_partial_full_run_does_not_replace_default_output(tmp_path: Path, monkeypatch):
    """--universe full --limit N must not overwrite web/public/data even if OUTPUT_DIR points there."""
    import screener_pipeline.config as cfg
    from screener_pipeline.build import build as build_fn

    stub_offline_sources(monkeypatch)
    live = tmp_path / "web-data"
    live.mkdir()
    (live / "keep.txt").write_text("stage1")
    monkeypatch.setattr(cfg, "OUTPUT_DIR", live)
    meta = build_fn(
        "sample:biotech20",
        offline=True,
        verify_quarters=False,
        output_dir=live,
        state_dir=tmp_path / "state",
        limit=2,
        use_bulk=False,
    )
    assert meta["dataset"]["mode"] == "partial"
    assert (live / "keep.txt").read_text() == "stage1"
    staging = tmp_path / "state" / "dataset-partial"
    assert (staging / "meta.json").exists()
    assert (staging / "screener.json").exists()
    rows = (staging / "screener.json").read_text()
    assert "marketCap" not in rows
    assert "sector" not in rows
