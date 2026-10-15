from __future__ import annotations

from screener_pipeline.sec.statement import statement_from_compact, statement_to_compact
from screener_pipeline.sec.store import StatementStore


def test_statement_compact_roundtrip_keeps_revenue_rows(tmp_path):
    from helpers import FIXTURES

    from screener_pipeline.sec.statement import parse_statement_html

    html = (FIXTURES / "statements" / "SRPT-0001193125-26-335003-R4.htm").read_text()
    st = parse_statement_html(html)
    compact = statement_to_compact(st, "https://example.test/R4.htm")
    assert compact["rows"]
    from screener_pipeline.sec.statement import is_net_income_label

    def kept(r: dict) -> bool:
        c, lab = r["concept"].lower(), r["label"].lower()
        return (
            any(tok in c for tok in ("revenue", "sales", "netincome", "profitloss", "incomeloss"))
            or "revenue" in lab
            or "sales" in lab
            or is_net_income_label(r["label"])
        )

    assert all(kept(r) for r in compact["rows"])
    restored, url = statement_from_compact(compact)
    assert url.endswith("R4.htm")
    assert restored.scale == st.scale
    assert len(restored.columns) == len(st.columns)


def test_statement_store_missing_and_hit(tmp_path):
    store = StatementStore(tmp_path)
    assert store.get("0001") is None
    store.put("0001", None)
    assert store.get("0001") is False
    from datetime import date

    from screener_pipeline.sec.statement import Statement, StatementColumn, StatementRow

    st = Statement("t", 1.0, [StatementColumn(3, date(2024, 3, 31))],
                   [StatementRow("us-gaap:Revenues", "Revenues", [100.0])])
    store.put("0002", (st, "http://x"))
    got = store.get("0002")
    assert got is not None and got is not False
    rst, url = got
    assert url == "http://x"
    assert rst.rows[0].values == [100.0]
