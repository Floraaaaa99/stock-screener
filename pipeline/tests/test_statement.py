from datetime import date

from helpers import FIXTURES

from screener_pipeline.sec.statement import (
    income_statement_candidates,
    is_net_income_label,
    is_total_revenue_label,
    parse_statement_html,
)

R_PAGE = """
<html><body><table class="report">
<tr>
<th class="tl" colspan="2" rowspan="2"><div><strong>Consolidated Statements of Operations - USD ($)<br> $ in Thousands
</strong></div></th>
<th class="th" colspan="4">3 Months Ended</th>
<th class="th" colspan="2">9 Months Ended</th>
</tr>
<tr>
<th class="th" colspan="2"><div>Sep. 30, 2024</div></th>
<th class="th" colspan="2"><div>Sep. 30, 2023</div></th>
<th class="th"><div>Sep. 30, 2024</div></th>
<th class="th"><div>Sept. 30, 2023</div></th>
</tr>
<tr class="re">
<td class="pl"><a onclick="Show.showAR( this, 'defref_us-gaap_Revenues', window );">Total revenues</a></td>
<td class="th"><sup></sup></td>
<td class="nump">$ 1,234<span></span></td>
<td class="fn">[1]</td>
<td class="nump">1,000<span></span></td>
<td class="fn"></td>
<td class="nump">3,500</td>
<td class="nump">2,900</td>
</tr>
<tr class="ro">
<td class="pl"><a onclick="Show.showAR( this, 'defref_us-gaap_OperatingIncomeLoss', window );">
Loss from operations</a></td>
<td class="th"></td>
<td class="num">(50)</td><td class="fn"></td>
<td class="num">$ (40)</td><td class="fn"></td>
<td class="num">(120)</td>
<td class="num">(90)</td>
</tr>
</table></body></html>
"""


def test_parse_statement_with_footnote_columns_and_scale():
    st = parse_statement_html(R_PAGE)
    assert st.scale == 1000
    rev = st.rows[0]
    assert rev.concept == "us-gaap:Revenues"
    assert st.value(rev, 3, date(2024, 9, 30)) == 1_234_000
    assert st.value(rev, 3, date(2023, 9, 30)) == 1_000_000
    assert st.value(rev, 9, date(2024, 9, 30)) == 3_500_000
    assert st.value(rev, 9, date(2023, 9, 30)) == 2_900_000
    assert st.value(st.rows[1], 3, date(2023, 9, 30)) == -40_000
    assert st.value(rev, 12, date(2024, 9, 30)) is None


def test_real_sarepta_statement():
    html = (FIXTURES / "statements" / "SRPT-0001193125-26-335003-R4.htm").read_text()
    st = parse_statement_html(html)
    rows = {r.concept: r for r in st.rows}
    total = rows["us-gaap:Revenues"]
    assert is_total_revenue_label(total.label)
    assert st.value(total, 3, date(2026, 6, 30)) == 401_251_000


def test_income_statement_candidates_ranking():
    xml = """<FilingSummary><MyReports>
    <Report><HtmlFileName>R2.htm</HtmlFileName><ShortName>Balance Sheets</ShortName>
      <MenuCategory>Statements</MenuCategory><Position>2</Position></Report>
    <Report><HtmlFileName>R4.htm</HtmlFileName><ShortName>Statements of Comprehensive Loss</ShortName>
      <MenuCategory>Statements</MenuCategory><Position>4</Position></Report>
    <Report><HtmlFileName>R3.htm</HtmlFileName><ShortName>Statements of Operations and Comprehensive Loss</ShortName>
      <MenuCategory>Statements</MenuCategory><Position>3</Position></Report>
    <Report><HtmlFileName>R5.htm</HtmlFileName><ShortName>Statements of Stockholders' Equity</ShortName>
      <MenuCategory>Statements</MenuCategory><Position>5</Position></Report>
    <Report><HtmlFileName>R9.htm</HtmlFileName><ShortName>Revenue (Details)</ShortName>
      <MenuCategory>Details</MenuCategory><Position>9</Position></Report>
    </MyReports></FilingSummary>"""
    assert [c[0] for c in income_statement_candidates(xml)] == ["R3.htm", "R4.htm"]


def test_real_filing_summary_finds_income_statement():
    xml = (FIXTURES / "statements" / "SRPT-0001193125-26-335003-FilingSummary.xml").read_text()
    assert income_statement_candidates(xml)[0][0] == "R4.htm"


def test_total_revenue_labels():
    for label in ["Total revenues", "Revenues", "Net sales", "Total net revenue", "Revenue, net", "Total revenue"]:
        assert is_total_revenue_label(label), label
    for label in ["Product revenue, net", "Collaboration revenue", "Cost of sales", "Royalty revenues"]:
        assert not is_total_revenue_label(label), label


def test_net_income_labels():
    for label in [
        "Net income",
        "Net loss",
        "Net earnings",
        "Net income (loss)",
        "Net income attributable to the Company",
        "Profit (loss)",
    ]:
        assert is_net_income_label(label), label
    for label in [
        "Net income per share",
        "Income from operations",
        "Operating income",
        "Comprehensive income",
        "Net income from continuing operations",
    ]:
        assert not is_net_income_label(label), label
