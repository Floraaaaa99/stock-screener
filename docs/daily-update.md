# Daily incremental financial-data update

Scheduled GitHub Actions job that refreshes the committed JSON dataset from new SEC 10-Q / 10-K filings. It does **not** download `companyfacts.zip`, expand the NASDAQ Trader universe, or replace a live payload that fails validation.

## What runs

| Workflow | Trigger | Writes live JSON | Deploys Pages |
|---|---|---|---|
| `daily-update.yml` | 11:59 PM America/Los_Angeles, plus **Run workflow** | Yes, after the gate passes (`--write-live`) | Yes, in the same workflow |
| `refresh.yml` | Manual only | No | No |
| `deploy.yml` | Push to `main`, optional sample refresh | Sample refresh only | Yes, unless the commit message contains `[skip pages]` |

`GITHUB_TOKEN` commits do not start other workflows. The daily job therefore builds `web/dist` and calls `deploy-pages` itself. The commit message includes `[skip pages]` so a later PAT push would not double-deploy.

GitHub cron is UTC. The workflow lists both `59 6 * * *` (PDT) and `59 7 * * *` (PST) and skips unless `TZ=America/Los_Angeles` hour is `23`.

## Update steps

1. Read the last `lookbackDays` (default 10) of EDGAR `master.idx` daily indexes.
2. Keep 10-Q, 10-Q/A, 10-QT, 10-QT/A, 10-K, 10-K/A, 10-KT, 10-KT/A. Skip weekends/holidays (404).
3. Drop accessions already listed in `web/public/data/daily-update.json` (pruned after 40 days).
4. Map remaining CIKs onto the **current** dataset (`issuers.json` + `companies/*.json`). Unknown CIKs are recorded as `out_of_universe`; they are not added. Universe expansion stays on `refresh.yml`.
5. Download Company Facts **only** for affected CIKs. Recalculate Revenue, Net Income, Gross Profit, OCF, CapEx, FCF, and TTM using the existing quarter / verification / fiscal-label code (`rebuild_company`, `write_layer3`).
6. Copy the live tree to a staging directory, write changed company and issuer files with `write_json_if_changed` (identical JSON is left untouched; missing values stay `null`, never `0`).
7. Rebuild Layer 1 aggregates, Layer 2, and incremental Layer 3. Extra Layer 3 issuer files are never deleted. Browser Layer 3 membership (`localStorage`) is not remapped.
8. Run `evaluate_gate` against the previous `meta.json`. On failure, delete staging and keep the previous dataset; those accessions are not marked processed.
9. On success, copy only changed files back (never delete extras), bump `meta.generatedAt` (the site “Data updated” / “Screener updated” stamp), and deploy Pages.

A day with no in-universe filings is still a successful heartbeat: `meta.generatedAt` and `daily-update.json` update so the website shows the latest successful run.

## Commands

```bash
export SEC_USER_AGENT="stock-screener Your Name you@example.com"
screener -v daily-update --dry-run --lookback-days 10
screener -v daily-update --write-live --lookback-days 10
```

Without `--write-live`, `web/public/data` is not replaced (same hold-back as `screener build`).

## What is not in this job

- Full-universe NASDAQ Trader refresh (`refresh.yml`)
- Bulk `companyfacts.zip` / `submissions.zip`
- Layer 3 scoring
- Replacing missing financials with zero
- Deleting unused Layer 3 issuer JSON (preserves curated CIK identity)
