# Yahoo Finance terms and the public dataset

Checked 14 October 2026 against Yahoo's Terms of Service and Yahoo Finance's data-provider notice. This is not legal advice.

## What the terms say

Yahoo's Terms of Service ([US](https://legal.yahoo.com/us/en/yahoo/terms/otos/index.html)):

- **Automated collection is forbidden** without express prior permission (robots, scrapers, data-mining or extraction tools).
- **You may not use Yahoo content** to create a database, archive, data feed, widget or other aggregated source that competes with or substitutes for Yahoo or its data providers.
- **Unless you have explicit written permission**, you must not reproduce, distribute, transmit, broadcast, **publicly perform**, or exploit Yahoo's services or content (including APIs) for commercial purposes.
- Access or reuse of the services for a commercial purpose is not allowed unless Yahoo expressly says otherwise.

Yahoo Finance's [exchanges and data providers notice](https://help.yahoo.com/kb/exchanges-data-providers-yahoo-finance-sln2310.html):

> You must not redistribute information displayed on or provided by Yahoo Finance.

Upstream vendors named there (including LSEG / Refinitiv) separately forbid copying, republication and redistribution.

yfinance is unofficial. Its own disclaimer says it is for research and education and that Yahoo's terms govern the downloaded data.

## What that means for this project

Sector, industry, market cap and price on the Stage 1 sample were fetched from Yahoo via yfinance. Publishing those same fields for the **full U.S. universe** on GitHub Pages would be public display and redistribution of Yahoo (and exchange) data.

Until you have written permission from Yahoo and the relevant exchanges, or you replace those fields with a licensed or public-domain source:

1. The live GitHub Pages site **stays on the Stage 1 Biotechnology sample**.
2. A full-universe run **does not replace** `web/public/data/` (the Pages payload).
3. The `pipeline-state` GitHub Release **contains only SEC-derived files** (compact revenue facts and parsed statements). Yahoo's cache stays in the runner's `actions/cache` / local `pipeline/.cache/yahoo/` and is never packed into the release.
4. `screener gate --publish` **fails** for a full-universe dataset, with reason `yahoo_terms_block_public_full_dataset`.
5. There is **no weekly schedule** until two complete full manual runs have passed the non-publish validation gates *and* this Yahoo question is decided.

NASDAQ Trader symbol directories and SEC EDGAR Company Facts / filings are used under their own public terms and are the data that may be published.

## Options when you want the full site public

- Obtain written permission from Yahoo (and LSEG / the exchanges as required), or
- Drop Yahoo fields from the public JSON (sector, industry, market cap and price become N/A; TTM from SEC remains), or
- Replace those four fields with another source that allows public display.

Do not treat "the Stage 1 sample already shows Yahoo data" as permission to scale that to ~5,600 listings.
