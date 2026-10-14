from screener_pipeline.universe.nasdaq_trader import build_universe, clean_name, parse_other_listed
from screener_pipeline.universe.symbols import canonical_symbol, sec_symbol_variants

NASDAQ = """Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares
VRTX|Vertex Pharmaceuticals Incorporated - Common Stock|Q|N|N|100|N|N
BNTX|BioNTech SE - American Depositary Shares|Q|N|N|100|N|N
QQQ|Invesco QQQ Trust, Series 1|G|N|N|100|Y|N
ZXZZT|NASDAQ TEST STOCK|G|Y|N|100|N|N
ABCDW|Abcd Acquisition Corp. - Warrants|S|N|N|100|N|N
ABCDU|Abcd Acquisition Corp. - Units|S|N|N|100|N|N
ABCDR|Abcd Acquisition Corp. - Rights|S|N|N|100|N|N
ABCD|Abcd Acquisition Corp. - Class A Ordinary Shares|S|N|N|100|N|N
BRKRP|Bruker Corporation - 6.375% Mandatory Convertible Preferred Stock, Series A|Q|N|N|40|N|N
WAFDP|WaFd, Inc. - Depositary Shares|Q|N|N|100|N|N
TMUSZ|T-Mobile US, Inc. - 5.500% Senior Notes due March 2070|Q|N|N|100|N|N
NOVTU|Novanta Inc. - Tangible Equity Units|Q|N|N|100|N|N
PSNYW|Polestar Automotive Holding UK Limited - Class C-1 ADS (ADW)|G|N|N|100|N|N
GOOG|Alphabet Inc. - Class C Capital Stock|Q|N|N|40|N|N
GOOGL|Alphabet Inc. - Class A Common Stock|Q|N|N|100|N|N
File Creation Time: 1014202614:01|||||||
"""

OTHER = """ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot Size|Test Issue|NASDAQ Symbol
BRK.B|Berkshire Hathaway Inc. New Common Stock|N|BRK.B|N|40|N|BRK.B
ABR$D|Arbor Realty Trust 6.375% Series D Cumulative Redeemable Preferred Stock|N|ABRpD|N|100|N|ABR-D
AAC.U|Ares Acquisition Corporation III Units, each consisting of one Class A ordinary share|N|AAC.U|N|100|N|AAC=
AAC.W|Ares Acquisition Corporation III Redeemable warrants|N|AAC.WS|N|100|N|AAC+
ABEV|Ambev S.A. American Depositary Shares (Each representing 1 Common Share)|N|ABEV|N|100|N|ABEV
SPY|SPDR S&P 500 ETF Trust|P|SPY|Y|100|N|SPY
XYZ|Some Arca Listed Common Stock|P|XYZ|N|100|N|XYZ
IMO|Imperial Oil Limited Common Stock|A|IMO|N|100|N|IMO
EPD|Enterprise Products Partners L.P. Common Units|N|EPD|N|100|N|EPD
JFR|Nuveen Floating Rate Income Fund Common Stock|N|JFR|N|100|N|JFR
GJO|Synthetic Fixed-Income Securities, Inc. on behalf of STRATS(SM) Trust|N|GJO|N|100|N|GJO
CELG.R|Bristol-Myers Squibb Company Celgene Contingent Value Rights|N|CELG.R|N|100|N|CELG.R
ZZZTX|TXSE Test Stk 5 Common Stock|F|ZZZTX|N|40|Y|ZZZTX
File Creation Time: 1014202614:01||||||
"""


def universe():
    listings, exclusions, times = build_universe(NASDAQ, OTHER)
    return {x.symbol: x for x in listings}, {e.symbol: e.reason for e in exclusions}, times


def test_included_common_stocks_and_adrs():
    inc, _, _ = universe()
    assert set(inc) == {"VRTX", "BNTX", "ABCD", "GOOG", "GOOGL", "BRK-B", "ABEV", "IMO", "EPD"}
    assert inc["BNTX"].security_type == "adr"
    assert inc["ABEV"].security_type == "adr"
    assert inc["VRTX"].security_type == "common"
    assert inc["IMO"].exchange == "NYSE American"
    assert inc["BRK-B"].exchange == "NYSE"
    assert inc["VRTX"].exchange == "NASDAQ"
    assert inc["VRTX"].nasdaq_tier == "Global Select"


def test_exclusion_reasons():
    _, exc, _ = universe()
    assert exc["QQQ"] == "etf"
    assert exc["ZXZZT"] == "test_issue"
    assert exc["ABCDW"] == "warrant"
    assert exc["ABCDU"] == "unit"
    assert exc["ABCDR"] == "right"
    assert exc["BRKRP"] == "preferred"
    assert exc["WAFDP"] == "preferred"
    assert exc["TMUSZ"] == "debt"
    assert exc["NOVTU"] == "unit"
    assert exc["PSNYW"] == "warrant"
    assert exc["ABR$D"] == "preferred"
    assert exc["AAC-U"] == "unit"
    assert exc["AAC-W"] == "warrant"
    assert exc["SPY"] == "exchange_out_of_scope"
    assert exc["XYZ"] == "exchange_out_of_scope"
    assert exc["JFR"] == "fund"
    assert exc["GJO"] == "structured_product"
    assert exc["CELG-R"] == "right"
    assert exc["ZZZTX"] == "test_issue"


def test_file_creation_times_are_kept():
    _, _, times = universe()
    assert times == {"nasdaqlisted": "1014202614:01", "otherlisted": "1014202614:01"}


def test_duplicate_symbol_across_files_is_recorded():
    other = OTHER.replace("IMO|Imperial Oil Limited Common Stock|A|", "VRTX|Duplicate Listing Common Stock|A|")
    listings, exclusions, _ = build_universe(NASDAQ, other)
    assert [x.name for x in listings if x.symbol == "VRTX"] == ["Vertex Pharmaceuticals Incorporated"]
    assert any(e.symbol == "VRTX" and e.reason == "duplicate" for e in exclusions)


def test_symbol_normalization():
    assert canonical_symbol("BRK.B") == "BRK-B"
    assert canonical_symbol(" brk/a ") == "BRK-A"
    assert sec_symbol_variants("BRK-B") == ["BRK-B", "BRK.B", "BRKB"]


def test_clean_name():
    assert clean_name("Vertex Pharmaceuticals Incorporated - Common Stock") == "Vertex Pharmaceuticals Incorporated"
    assert clean_name("Berkshire Hathaway Inc. New Common Stock") == "Berkshire Hathaway Inc."
    assert clean_name("BioNTech SE - American Depositary Shares") == "BioNTech SE"
    assert clean_name("Alphabet Inc. - Class C Capital Stock") == "Alphabet Inc."


def test_other_listed_skips_footer():
    listings, _, created = parse_other_listed(OTHER)
    assert created == "1014202614:01"
    assert all(not x.symbol.startswith("FILE") for x in listings)
