from __future__ import annotations

from screener_pipeline.sec.sic import industry_label, major_group_name, normalize_sic, sic_from_submissions


def test_normalize_and_labels():
    assert normalize_sic(2834) == "2834"
    assert normalize_sic("734") == "0734"
    assert normalize_sic(None) is None
    assert major_group_name("2834") == "Chemicals and Allied Products"
    assert industry_label("2834", "Pharmaceutical Preparations") == "Pharmaceutical Preparations — 2834"


def test_sic_from_submissions():
    info = sic_from_submissions({"sic": "2836", "sicDescription": "Biological Products"})
    assert info.code == "2836"
    assert info.major_group == "Chemicals and Allied Products"
    assert info.label == "Biological Products — 2836"
    empty = sic_from_submissions({})
    assert empty.code is None
