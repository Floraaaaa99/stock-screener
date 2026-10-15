# U.S. Stock Screener

A public, static stock screener for U.S.-listed common stocks and ADRs (NASDAQ, NYSE, NYSE American). For each
listing it shows **SEC SIC** industry, trailing-twelve-month (TTM) revenue, and TTM revenue growth computed from the
latest standalone fiscal quarters reported to the SEC. Sequential growth (Layer 2) then classifies companies with
positive TTM growth using four quarterly YoY rates, and shows descriptive QoQ rates and category badges. Stock price
and market cap are not included.

- **Website:** React + Vite + TypeScript in [`web/`](web), hosted on GitHub Pages. No login, no backend.
- **Data pipeline:** Python in [`pipeline/`](pipeline), which writes static JSON to `web/public/data/`.
- **Refresh:** GitHub Actions ([`.github/workflows/deploy.yml`](.github/workflows/deploy.yml) for the sample site,
  [`.github/workflows/refresh.yml`](.github/workflows/refresh.yml) for the full universe). Refreshes run manually for
  now and become weekly once two complete full runs have passed validation.

All data sources are free: the [NASDAQ Trader symbol directory](https://www.nasdaqtrader.com/trader.aspx?id=symboldirdefs)
and [SEC EDGAR](https://www.sec.gov/edgar/sec-api-documentation) (official 10-Q/10-K filings, Company Facts as an
index, submissions SIC, and filing income statements). When Company Facts lag a filing already on EDGAR, the
pipeline uses that filing's reported revenue. No paid APIs, databases, estimates, or Yahoo Finance data are used.

## Status

| Stage | Scope | Status |
|---|---|---|
| 1 | 20 Biotechnology companies plus 2 foreign-filer ADRs, validated against SEC filings | Done as an SEC-only sample. See [`docs/validation/biotech20.md`](docs/validation/biotech20.md) |
| 2 | Full NASDAQ / NYSE / NYSE American universe (≈5,600 listings) | Resumable SEC-only pipeline and publish gates. Live Pages stays on the sample until a complete full run passes completeness and filing-validation checks. See [`docs/stage2-persistence.md`](docs/stage2-persistence.md) |
| 3 | Scheduled refreshes on GitHub Pages | Not enabled. Weekly cron is added only after two complete full manual runs |

While the site runs on the validation sample, a banner says so and shows how many of the eligible listings are
included. `--universe full` writes a complete dataset to a staging directory; it does not replace the live Pages payload
unless `--write-live` is set **and** the publish gate passes. A `--limit` run is marked `partial` and cannot pass the
publish gate.

## How the numbers are calculated

See [`docs/methodology.md`](docs/methodology.md). In short:

- **Current TTM** is the sum of the latest 4 standalone fiscal quarters. **Previous TTM** is the sum of the 4 quarters before those.
- **TTM Revenue Growth YoY** = (Current TTM ÷ Previous TTM − 1) × 100. It is computed only when all 8 quarters are present, consecutive, comparable, and each matches its filing. Mismatched or unverified TTM-window quarters make Current TTM, Previous TTM, and growth N/A; the company stays listed with the reason. The 10% mismatch gate is a publish brake for the whole file, not a way those values enter TTM.
- Quarters that are not reported directly are derived from year-to-date figures, for example Q4 = FY − 9M. Every quarter records how it was obtained and which filings it came from.
- **Industry** is the company's SEC SIC code and description (plus the two-digit SIC major group). These are labeled **SEC SIC**, not commercial sector/industry names.
- Revenue amounts are labeled with the SEC reporting currency, including USD. Amounts in different currencies are not converted and are not ranked as one series.
- Missing values are shown as **N/A** with a reason, never as zero. Companies without usable SEC revenue stay in the table.
- The table defaults to TTM growth descending, with N/A last. Current and Previous TTM revenue are also sortable.
- **Sequential growth (Layer 2)** uses the same eight-quarter window. Passed requires TTM growth > 0% and four strictly positive quarterly YoY rates. Watchlist is valid data with at least one YoY ≤ 0%. Valid TTM growth ≤ 0% is listed separately and is not Data Review. QoQ is descriptive. Stable-spread and recent-jump badge thresholds stay unset until configured (`pipeline/config/layer2.json`).

## Local development

Requirements: Python 3.11+ and Node.js 20.19+ or 22.12+.

```bash
# Pipeline
python3 -m venv .venv && source .venv/bin/activate
pip install -e "pipeline[dev]"
cd pipeline && pytest -q && ruff check . && cd ..

# SEC requires a descriptive User-Agent with contact details
export SEC_USER_AGENT="stock-screener Your Name you@example.com"

# Build the validation sample (writes web/public/data/) and a validation report
screener -v build --universe sample:biotech20 --report docs/validation/biotech20.md

# Rebuild from cached downloads only
screener build --universe sample:biotech20 --offline

# Universe statistics from NASDAQ Trader
screener universe

# Request / runtime estimate (bulk zip vs per-CIK API)
screener estimate

# Full universe (does not replace web/public/data until --write-live and the gate pass)
screener -v build --universe full --time-budget-hours 5 --report docs/validation/full.md

# Resume after a time-budget stop (exit code 3); statements already fetched are reused
screener -v build --universe full --time-budget-hours 5

# Pack / verify compact SEC state (facts, statements, SIC)
screener pack-state --dest /tmp/state.tar.gz
screener unpack-state --archive /tmp/state.tar.gz --dest /tmp/state --sha256-file /tmp/state.tar.gz.sha256
screener gate --meta pipeline/.cache/state/dataset-full/meta.json
screener gate --meta pipeline/.cache/state/dataset-full/meta.json --publish

# Compare a built dataset with EDGAR 10-Q/10-K submissions (does not write live Pages)
screener freshness --data-dir pipeline/.cache/state/dataset-full --refresh-lagging

# Layer 2 from an existing Layer 1 dataset (does not fetch SEC data)
screener layer2 --data-dir web/public/data

# Write the live Pages payload only after the publish gate passes
screener -v build --universe full --write-live

# Website
cd web
npm ci
npm run dev        # http://localhost:5173/stock-screener/
npm test           # unit tests
npm run build      # production build in web/dist
```

Downloads are cached in `pipeline/.cache/`, which is git-ignored. `SCREENER_CACHE_DIR` and `SCREENER_OUTPUT_DIR`
override the cache and output locations.

### Configuration

| Setting | Where | Purpose |
|---|---|---|
| `SEC_USER_AGENT` | Environment variable locally; **repository secret** in Actions (Settings → Secrets and variables → Actions → Secrets) | Required by SEC EDGAR's fair-access policy. Format: `app-name Your Name email@example.com`. The pipeline exits if it is not set. It is stored as a secret so your contact details are masked in logs, and the pipeline never prints it or writes it to the dataset. |
| `VITE_BASE` | Build environment | Base path for the site. Defaults to `/stock-screener/`. The deploy workflow sets it from GitHub Pages. |
| `pipeline/config/concept_overrides.json` | Repository | Pins a company's revenue concept when the automatic selection is ambiguous. Each entry must cite the filing it was validated against. |

## Deployment (GitHub Pages)

One-time setup:

1. Under Settings → Pages → Build and deployment, set **Source** to **GitHub Actions**.
2. Under Settings → Secrets and variables → Actions → **Secrets**, choose **New repository secret** and add `SEC_USER_AGENT`, for example `stock-screener Your Name you@example.com`. This is only needed for data refreshes. If a `SEC_USER_AGENT` repository *variable* was created earlier, delete it, because variables are shown in plain text.

Workflows:

- **CI** (`ci.yml`) runs on pull requests and pushes to `main`: pipeline lint and tests, then web typecheck, tests and build.
- **Deploy to GitHub Pages** (`deploy.yml`) runs on pushes to `main` and deploys the committed **sample**. A full-universe `meta.json` is accepted only when `gate.ok` is true. Manual sample refresh still exists; nothing is committed or force-pushed.
- **Refresh full universe** (`refresh.yml`) is manual only. It restores compact SEC state from the `pipeline-state` release, builds with a 5-hour budget, packs and checksums a new state archive, and uploads artifacts. It never deploys Pages. Re-run the same workflow to resume after exit code 3. Weekly cron is not configured.

## Repository layout

```
pipeline/
  src/screener_pipeline/
    universe/     NASDAQ Trader parsing, security-type and exchange filtering
    sec/          Company Facts, SIC from submissions, EDGAR client, income-statement parsing
    quarters.py   Standalone-quarter derivation (YTD subtraction, restatements, fiscal labels)
    concepts.py   Revenue-concept selection and verification
    ttm.py        Current/Previous TTM and growth
    layer2.py     Sequential YoY/QoQ rates and QoQ category badges
    revenue.py    Per-company analysis and per-quarter filing checks
    gate.py       Completeness and filing-validation publish gates
    build.py      Dataset build and atomic write
  config/layer2.json  QoQ badge thresholds (null until configured)
  samples/        Validation samples (ticker lists)
  tests/          Unit tests and real-company regression tests (SEC fixtures)
web/
  src/            React app (components, lib/ for filtering, sorting and formatting)
  public/data/    Generated dataset served with the site
docs/             Methodology, validation reports, Stage 2 plan
```

## Disclaimer

For personal research only. This is not investment advice. Data may be delayed, incomplete or wrong. Check figures
against the linked SEC filings.
