"""HTML fixtures for 8-K Item 2.02 discovery and earnings-table extract tests."""

from __future__ import annotations

from pathlib import Path


def index_htm(*, form: str = "8-K", exhibits: list[tuple[str, str, str]]) -> str:
    rows = [
        "<tr><th>Seq</th><th>Description</th><th>Document</th><th>Type</th><th>Size</th></tr>",
        f'<tr><td>1</td><td>Current report</td><td><a href="d8k.htm">d8k.htm</a></td><td>{form}</td><td>10</td></tr>',
    ]
    for i, (doc_type, desc, name) in enumerate(exhibits, start=2):
        rows.append(
            f'<tr><td>{i}</td><td>{desc}</td><td><a href="{name}">{name}</a></td><td>{doc_type}</td><td>20</td></tr>'
        )
    return "<html><body><table class='tableFile'>" + "".join(rows) + "</table></body></html>"


ITEM_202_BODY = """
<html><body>
<p>UNITED STATES SECURITIES AND EXCHANGE COMMISSION</p>
<p>Item 2.02 Results of Operations and Financial Condition.</p>
<p>On October 21, 2026, the Company issued a press release announcing results for the third quarter.</p>
<p>Item 9.01 Financial Statements and Exhibits.</p>
</body></html>
"""

ITEM_801_BODY = """
<html><body>
<p>Item 8.01 Other Events.</p>
<p>The Company announced a leadership change and furnished an investor presentation.</p>
<p>Item 9.01 Financial Statements and Exhibits.</p>
</body></html>
"""

ITEM_202_NO_TABLES = """
<html><body>
<p>The Company announced that it expects to report quarterly results next week.</p>
<p>No financial statements are included in this exhibit.</p>
</body></html>
"""

INVESTOR_DECK = """
<html><body>
<h1>Investor Presentation</h1>
<p>Q3 2026 earnings webcast slides</p>
<table>
<tr><td>Adjusted EBITDA</td><td>9,000</td></tr>
<tr><td>Adjusted net income</td><td>8,000</td></tr>
</table>
</body></html>
"""


def _is_table(title: str, scale: str, headers: list[list[str]], rows: list[list[str]]) -> str:
    head = "".join("<tr>" + "".join(f"<th>{c}</th>" for c in row) + "</tr>" for row in headers)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>" for row in rows)
    return f"<p>{title}</p><p>{scale}</p><table>{head}{body}</table>"


GAAP_EARNINGS_EXHIBIT = f"""
<html><body>
<h1>Company Reports Third Quarter 2026 Results</h1>
{_is_table(
    "CONDENSED CONSOLIDATED STATEMENTS OF INCOME (GAAP)",
    "(In millions, except per share amounts)",
    [
        [
            "",
            "Three Months Ended September 30,",
            "Three Months Ended September 30,",
            "Nine Months Ended September 30,",
            "Nine Months Ended September 30,",
        ],
        ["", "2026", "2025", "2026", "2025"],
    ],
    [
        ["Revenue", "51,242", "40,589", "140,100", "110,200"],
        ["Cost of revenue", "9,100", "7,400", "26,000", "21,000"],
        ["Gross profit", "42,142", "33,189", "114,100", "89,200"],
        ["Income from operations", "20,500", "17,000", "58,000", "46,000"],
        ["Net income", "18,300", "15,700", "50,100", "41,200"],
        ["Diluted earnings per share", "7.25", "6.03", "19.80", "15.90"],
        ["Adjusted net income", "21,000", "18,000", "60,000", "49,000"],
    ],
)}
{_is_table(
    "Non-GAAP financial measures",
    "(In millions)",
    [["", "Three Months Ended September 30, 2026", "Three Months Ended September 30, 2025"]],
    [
        ["Adjusted EBITDA", "28,000", "24,000"],
        ["Adjusted net income", "21,000", "18,000"],
    ],
)}
{_is_table(
    "CONDENSED CONSOLIDATED BALANCE SHEETS",
    "(In millions)",
    [["", "September 30, 2026", "December 31, 2025"]],
    [
        ["Cash and cash equivalents", "44,400", "38,000"],
        ["Inventory", "1,200", "900"],
        ["Total assets", "280,000", "250,000"],
        ["Total liabilities", "90,000", "80,000"],
        ["Long-term debt", "28,000", "26,000"],
        ["Current portion of long-term debt", "2,000", "1,500"],
    ],
)}
{_is_table(
    "CONDENSED CONSOLIDATED STATEMENTS OF CASH FLOWS",
    "(In millions)",
    [
        ["", "Three Months Ended September 30, 2026", "Nine Months Ended September 30, 2026"],
    ],
    [
        ["Net cash provided by operating activities", "25,100", "70,000"],
        ["Purchases of property and equipment", "(8,400)", "(22,000)"],
    ],
)}
</body></html>
"""

UNITS_SIGNS_EXHIBIT = f"""
<html><body>
<h1>Second Quarter 2026 Results</h1>
{_is_table(
    "Consolidated Statements of Operations",
    "($ in thousands)",
    [["", "Three Months Ended June 30, 2026", "Three Months Ended June 30, 2025"]],
    [
        ["Net sales", "1,234.5", "980.0"],
        ["Operating loss", "(88.0)", "(12.0)"],
        ["Net loss", "(101.5)", "15.0"],
    ],
)}
</body></html>
"""

MISSING_CF_EXHIBIT = f"""
<html><body>
<h1>First Quarter 2026 Results</h1>
{_is_table(
    "Statements of Income",
    "(In millions)",
    [["", "Three Months Ended March 31, 2026"]],
    [
        ["Revenue", "10"],
        ["Net income", "2"],
    ],
)}
</body></html>
"""

YTD_ONLY_EXHIBIT = f"""
<html><body>
<h1>Year-to-date update</h1>
{_is_table(
    "Statements of Income",
    "(In millions)",
    [["", "Nine Months Ended September 30, 2026"]],
    [
        ["Revenue", "140,100"],
        ["Net income", "50,100"],
    ],
)}
</body></html>
"""

AMENDMENT_EXHIBIT = f"""
<html><body>
<h1>Amendment to Third Quarter 2026 Results</h1>
{_is_table(
    "CONDENSED CONSOLIDATED STATEMENTS OF INCOME",
    "(In millions)",
    [["", "Three Months Ended September 30, 2026"]],
    [
        ["Revenue", "51,300"],
        ["Net income", "18,350"],
    ],
)}
</body></html>
"""

META_Q3_2026_EXHIBIT = f"""
<html><body>
<h1>Meta Reports Third Quarter 2026 Results</h1>
{_is_table(
    "CONDENSED CONSOLIDATED STATEMENTS OF INCOME",
    "(In millions, except per share amounts) (Unaudited)",
    [
        [
            "",
            "Three Months Ended September 30,",
            "Three Months Ended September 30,",
            "Nine Months Ended September 30,",
            "Nine Months Ended September 30,",
        ],
        ["", "2026", "2025", "2026", "2025"],
    ],
    [
        ["Revenue", "56,100", "40,589", "155,000", "120,000"],
        ["Cost of revenue", "9,800", "7,375", "28,000", "22,000"],
        ["Income from operations", "25,400", "17,350", "70,000", "50,000"],
        ["Net income", "21,200", "15,688", "58,000", "43,000"],
        ["Diluted earnings per share", "8.40", "6.03", "22.90", "16.50"],
    ],
)}
{_is_table(
    "CONDENSED CONSOLIDATED BALANCE SHEETS",
    "(In millions)",
    [["", "September 30, 2026", "December 31, 2025"]],
    [
        ["Cash and cash equivalents", "48,000", "43,889"],
        ["Total assets", "310,000", "276,054"],
        ["Total liabilities", "95,000", "99,787"],
    ],
)}
{_is_table(
    "CONDENSED CONSOLIDATED STATEMENTS OF CASH FLOWS",
    "(In millions)",
    [["", "Three Months Ended September 30, 2026", "Nine Months Ended September 30, 2026"]],
    [
        ["Net cash provided by operating activities", "29,000", "80,000"],
        ["Purchases of property and equipment", "(15,000)", "(40,000)"],
    ],
)}
</body></html>
"""

META_ACCN = "0001628280-26-066700"
META_CIK = "0001326801"
META_Q3_2026_REAL_EXHIBIT = (Path(__file__).resolve().parent / "meta_q3_2026_ex991.htm").read_text(encoding="utf-8")
META_Q3_2026_EXHIBIT_URL = (
    "https://www.sec.gov/Archives/edgar/data/1326801/000162828026066700/meta-09302026xexhibit991.htm"
)


def earnings_documents(
    accn: str,
    *,
    form: str = "8-K",
    exhibit: str = GAAP_EARNINGS_EXHIBIT,
    extra_exhibits: list[tuple[str, str, str, str]] | None = None,
) -> dict[str, str]:
    exhibits = [("EX-99.1", "Earnings Release", "ex991.htm")]
    files = {
        f"{accn}-index.htm": index_htm(
            form=form,
            exhibits=exhibits + [(t, d, n) for t, d, n, _ in (extra_exhibits or [])],
        ),
        "d8k.htm": ITEM_202_BODY,
        "ex991.htm": exhibit,
    }
    for _type, _desc, name, body in extra_exhibits or []:
        files[name] = body
    return files


def unrelated_documents(accn: str) -> dict[str, str]:
    return {
        f"{accn}-index.htm": index_htm(
            exhibits=[("EX-99.1", "Investor Presentation", "ex991.htm")]
        ),
        "d8k.htm": ITEM_801_BODY,
        "ex991.htm": INVESTOR_DECK,
    }


def item202_presentation_only(accn: str) -> dict[str, str]:
    return {
        f"{accn}-index.htm": index_htm(
            exhibits=[("EX-99.1", "Investor Presentation", "ex991.htm")]
        ),
        "d8k.htm": ITEM_202_BODY,
        "ex991.htm": INVESTOR_DECK,
    }
