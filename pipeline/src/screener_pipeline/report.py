"""Markdown validation report comparing pipeline quarters with the filings' income statements."""

from __future__ import annotations

from pathlib import Path

from .cache import read_json, write_text_atomic


def _m(v: float | None) -> str:
    return "N/A" if v is None else f"{v / 1e6:,.1f}"


def _pct(v: float | None) -> str:
    return "N/A" if v is None else f"{v:+.1f}%"


def write_validation_report(data_dir: Path, out_path: str | Path) -> None:
    meta = read_json(data_dir / "meta.json")
    rows = read_json(data_dir / "screener.json")["rows"]
    lines: list[str] = []
    ds = meta["dataset"]
    lines += [
        f"# Validation report: {ds['name']}",
        "",
        f"Generated {meta['generatedAt']} from live NASDAQ Trader, Yahoo Finance and SEC EDGAR data.",
        "",
        "Every quarter shown on the site is checked against the income statements of the filings its value",
        "comes from (EDGAR's rendered statement pages, `R*.htm`, independent of the Company Facts API).",
        "Reported quarters are compared with the statement's 3-month column. Derived quarters are recomputed",
        "from the statement columns of their sources (for example Q4 = 10-K annual column − 10-Q nine-month",
        "column). \"Statement value\" is that recomputed figure. Values are in millions of the reporting currency.",
        "",
        "## Coverage",
        "",
        "| Metric | Value |",
        "|---|---|",
    ]
    for k, v in meta["coverage"].items():
        lines.append(f"| {k} | {v} |")
    lines += [
        "",
        "## Summary",
        "",
        "| Ticker | Concept | Concept status | Latest statement | Quarter checks "
        "| Current TTM | Previous TTM | Growth | N/A reason |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    details: list[str] = []
    for r in rows:
        c = read_json(data_dir / "companies" / f"{r['ticker']}.json")
        rev = c.get("revenue") or {}
        qs = rev.get("quarters", [])
        checked = [q for q in qs if not q.get("missing")]
        matches = sum(1 for q in checked if (q.get("check") or {}).get("status") == "match")
        sc = (rev.get("statementCheck") or {}).get("status", "n/a")
        lines.append(
            f"| {r['ticker']} | {rev.get('concept') or '—'} | {rev.get('conceptStatus') or rev.get('status') or '—'} "
            f"| {sc} | {matches}/{len(checked)} | {_m(c['ttm']['current'])} | {_m(c['ttm']['previous'])} "
            f"| {_pct(c['ttm']['growthPct'])} | {c['ttm']['reason'] or ''} |"
        )
        details += ["", f"### {r['ticker']} — {c['name']}", ""]
        if rev.get("conceptNote"):
            details += [rev["conceptNote"], ""]
        if rev.get("flags"):
            details += ["Flags: " + ", ".join(f"`{f}`" for f in rev["flags"]), ""]
        if not qs:
            details.append(f"No quarterly data ({c['ttm']['reason']}).")
            continue
        details += [
            "| Fiscal | Period | Pipeline | Method | Filing | Statement line | Statement value | Check |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for q in qs:
            fq = f"FY{q['fiscalYear']} Q{q['fiscalQuarter']}" if q.get("fiscalYear") else "?"
            if q.get("missing"):
                details.append(f"| {fq} | {q['start']} – {q['end']} | N/A | missing | | | | |")
                continue
            ck = q.get("check") or {}
            stmt_val = ck.get("expected_value", ck.get("statement_value"))
            details.append(
                f"| {fq} | {q['start']} – {q['end']} | {_m(q['value'])} | {q['formula']} "
                f"| [{q['form']} {q['filed']}]({q['url']}) | {ck.get('statement_label', '')} | {_m(stmt_val)} "
                f"| {ck.get('status', 'not checked')} |"
            )
    lines += ["", "## Quarter detail", *details, ""]
    write_text_atomic(Path(out_path), "\n".join(lines))
