# U.S. Stock Screener

A public, static stock screener for U.S.-listed common stocks and ADRs (NASDAQ, NYSE, NYSE American). For each
listing it shows sector, industry, market cap, price, and trailing-twelve-month (TTM) revenue growth computed from the
latest standalone fiscal quarters reported to the SEC.

- **Website:** React + Vite + TypeScript in [`web/`](web), hosted on GitHub Pages. No login, no backend.
- **Data pipeline:** Python in [`pipeline/`](pipeline), which writes static JSON to `web/public/data/`.
- **Refresh:** GitHub Actions ([`.github/workflows/deploy.yml`](.github/workflows/deploy.yml)). Refreshes run manually for now and become weekly once the full pipeline is stable.

All data sources are free: the [NASDAQ Trader symbol directory](https://www.nasdaqtrader.com/trader.aspx?id=symboldirdefs),
Yahoo Finance via [yfinance](https://github.com/ranaroussi/yfinance), and
[SEC EDGAR XBRL Company Facts](https://www.sec.gov/edgar/sec-api-documentation). No paid APIs or databases are used.

## Status

| Stage | Scope | Status |
|---|---|---|
| 1 | 20 Biotechnology companies plus 2 foreign-filer ADRs, validated against SEC filings | Done. See [`docs/validation/biotech20.md`](docs/validation/biotech20.md) |
| 2 | Full NASDAQ / NYSE / NYSE American universe (≈5,600 listings) | Not started. Persistence plan in [`docs/stage2-persistence.md`](docs/stage2-persistence.md) |
| 3 | Scheduled refreshes on GitHub Pages | Manual deploy and refresh workflows exist; the weekly schedule comes after Stage 2 |

While the site runs on the validation sample, a banner says so and shows how many of the eligible listings are
included. The pipeline refuses `--universe full` until Stage 2, so a smaller universe is never published as if it were
the full one.

## How the numbers are calculated

See [`docs/methodology.md`](docs/methodology.md). In short:

- **Current TTM** is the sum of the latest 4 standalone fiscal quarters. **Previous TTM** is the sum of the 4 quarters before those.
- **TTM Revenue Growth YoY** = (Current TTM ÷ Previous TTM − 1) × 100. It is computed only when all 8 quarters are present, consecutive and comparable (same verified revenue concept), and Previous TTM is positive.
- Quarters that are not reported directly are derived from year-to-date figures, for example Q4 = FY − 9M. Every quarter records how it was obtained and which filings it came from.
- Missing values are shown as **N/A** with a reason, never as zero. Yahoo's `revenueGrowth` field is never used.

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
screener build --universe sample:biotech20 --offline --skip-yahoo

# Universe statistics from NASDAQ Trader
screener universe

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
| `SEC_USER_AGENT` | Environment variable locally; **repository variable** in Actions (Settings → Secrets and variables → Actions → Variables) | Required by SEC EDGAR's fair-access policy. Format: `app-name Your Name email@example.com`. The pipeline exits if it is not set. |
| `VITE_BASE` | Build environment | Base path for the site. Defaults to `/stock-screener/`. The deploy workflow sets it from GitHub Pages. |
| `pipeline/config/concept_overrides.json` | Repository | Pins a company's revenue concept when the automatic selection is ambiguous. Each entry must cite the filing it was validated against. |

## Deployment (GitHub Pages)

One-time setup:

1. Under Settings → Pages → Build and deployment, set **Source** to **GitHub Actions**.
2. Under Settings → Secrets and variables → Actions → **Variables**, add `SEC_USER_AGENT`. This is only needed for data refreshes.

Workflows:

- **CI** (`ci.yml`) runs on pull requests and pushes to `main`: pipeline lint and tests, then web typecheck, tests and build.
- **Deploy to GitHub Pages** (`deploy.yml`) runs on pushes to `main` and deploys the committed dataset. A manual run with **refresh_data** checked rebuilds the dataset from the live sources first, deploys it, and uploads it as a `dataset` workflow artifact together with a validation report. Nothing is committed or force-pushed. To keep refreshed data across later pushes, review the artifact and commit it.

## Repository layout

```
pipeline/
  src/screener_pipeline/
    universe/     NASDAQ Trader parsing, security-type and exchange filtering
    sec/          Company Facts extraction, EDGAR client, income-statement parsing
    quarters.py   Standalone-quarter derivation (YTD subtraction, restatements, fiscal labels)
    concepts.py   Revenue-concept selection and verification
    ttm.py        Current/Previous TTM and growth
    revenue.py    Per-company analysis and per-quarter filing checks
    yahoo.py      Cached, rate-limited Yahoo Finance profile and market data
    build.py      Dataset build and atomic write
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
