# Yahoo Finance is not used

Checked 14 October 2026 against Yahoo's Terms of Service. This is not legal advice.

The screener originally fetched sector, industry, market cap and price from Yahoo Finance via yfinance. Yahoo's terms forbid redistributing that data as a public dataset. Those fields — and yfinance itself — have been **removed** from the pipeline, the published JSON (including the validation sample), and the website.

Replacement:

- **Industry** is SEC SIC (`sic` / `sicDescription` from EDGAR submissions), labeled SEC SIC, not Yahoo Sector/Industry.
- **Stock price and market cap** are not shown.
- **Revenue and TTM growth** continue to come from SEC EDGAR Company Facts and filing income statements.
- The `pipeline-state` GitHub Release contains only SEC-derived files (compact revenue facts, parsed statements, SIC records).

NASDAQ Trader symbol directories and SEC EDGAR data are used under their own public terms.
