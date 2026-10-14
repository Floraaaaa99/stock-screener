from __future__ import annotations

from pathlib import Path

import pytest

from screener_pipeline.build import IncompleteRun, build


def test_time_budget_does_not_replace_live_dataset(tmp_path: Path):
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
