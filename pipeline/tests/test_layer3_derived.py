from screener_pipeline.layer3_derived import history_on_end


def test_history_on_end_matches_within_ten_days():
    history = [
        {"end": "2026-07-26", "value": 22},
        {"end": "2026-04-26", "value": 18},
        {"end": "2025-07-27", "value": 11},
    ]
    hit = history_on_end(history, "2026-07-31")
    assert hit is not None
    assert hit["value"] == 22
    assert history_on_end(history, "2025-07-31")["value"] == 11
    assert history_on_end(history, "2026-04-30")["value"] == 18


def test_history_on_end_skips_missing_and_out_of_window():
    history = [
        {"end": "2026-07-26", "value": None},
        {"end": "2026-07-10", "value": 9},
        {"end": None, "value": 4},
    ]
    assert history_on_end(history, "2026-07-31") is None
    assert history_on_end(history, None) is None
    nearest = history_on_end(
        [{"end": "2026-07-26", "value": 1}, {"end": "2026-07-29", "value": 2}],
        "2026-07-31",
    )
    assert nearest["value"] == 2
