# Daily incremental financial-data update

Scheduled GitHub Actions job that refreshes the committed JSON dataset from new SEC filings. It does **not** download `companyfacts.zip`, expand the NASDAQ Trader universe, or replace a live payload that fails validation.

## What runs

| Workflow | Trigger | Writes live JSON | Deploys Pages |
|---|---|---|---|
| `daily-update.yml` | 6:00 PM America/Los_Angeles, plus **Run workflow** | Yes, after the gate passes and financial JSON changed | Yes, only when financial JSON changed |
| `refresh.yml` | Manual only | No | No |
| `deploy.yml` | Push to `main`, optional sample refresh | Sample refresh only | Yes, unless the commit message contains `[skip pages]` |

`GITHUB_TOKEN` commits do not start other workflows (`ci.yml` or `deploy.yml`). The daily job therefore builds `web/dist` and calls `deploy-pages` itself when financial JSON changed. The commit message includes `[skip pages]` so a later PAT push would not double-deploy.

The schedule uses GitHub Actions timezone-aware cron (`0 18 * * *` with `timezone: America/Los_Angeles`). DST is handled by the platform; there is no dual UTC cron or hour-check job. Manual **Run workflow** and `--dry-run` stay available. The update job has no approval environment.

## Discovery sources

Latest Filings and the daily index are complementary. Neither is used alone.

### Primary: SEC Latest Filings (`getcurrent` Atom)

[Latest Filings](https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent) lists filings for the **current official filing date** only (including after-hours submissions from the previous filing day). It is a rolling same-day feed, not a historical archive. Paginating `start` / `dateb` retrieves more of *today’s* list; it does not reconstruct missed days.

The job requests 8-K, 8-K/A, 10-Q, 10-Q/A, 10-K, and 10-K/A, uses acceptance timestamps from the Atom `updated` field, and pages until a page is empty. `browse-edgar` caps `count` at 40.

### Secondary: EDGAR `master.idx`

[Daily indexes](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data) under `/Archives/edgar/daily-index` are the complete record for a calendar day (1994Q3–present). They update nightly starting about 10:00 p.m. ET — after the 6:00 PM Pacific run — so today’s index is often still a 404 at job time.

The job:

- Reads the last 10 days, plus any extra days implied by `lastSuccessfulSyncAt` minus a 48-hour overlap, plus previously `unreconciledDates`.
- Re-fetches the last **3 business days** every run. A CIK header alone does not make an index permanently complete; header-only or truncated files are not cached.
- Skips Saturday and Sunday `master.idx` requests; SEC does not publish weekend daily indexes.
- Never writes a permanent `.404` cache. A weekday 404 in the 3-business-day window stays unreconciled and is retried. Older weekday 404s are treated as checked-empty (holiday). A weekday 403 is retried with bounded backoff and stays unreconciled if it remains inaccessible.
- Matches filings to the current screener universe by CIK. Unknown CIKs are `out_of_universe`.

`as_of` is the calendar date in `America/Los_Angeles`, not the GitHub runner’s UTC date. The 6:00 PM Pacific job therefore still belongs to the Pacific filing day (01:00–02:00 UTC the next morning).

## Incremental window

`web/public/data/daily-update.json` stores:

| Field | Meaning |
|---|---|
| `lastSuccessfulSyncAt` | Last time discovery + processing finished completely. Quiet nights advance this without changing financial JSON. |
| `lastFinancialUpdateAt` | Last time company / Layer 2 / Layer 3 JSON actually changed. |
| `unreconciledDates` | Index dates that are not yet safely checked. |
| `processedAccessions` | Deduped by accession number (kept 40 days). Status is `applied`, `recorded_8k`, or `out_of_universe`. |

Each run covers every filing since the previous successful sync, overlapping at least 48 hours so delayed SEC publication is retried. If Actions misses a day or the job fails, the next run extends `since` back to that checkpoint. The checkpoint does **not** advance when Latest Filings or Company Facts HTTP fails, the gate fails, or an in-universe 10-Q/10-K could not be applied.

## What happens when filings are found

| Form | Action |
|---|---|
| 10-Q, 10-Q/A, 10-K, 10-K/A (and 10-QT / 10-KT variants from the daily index) | Download Company Facts **only if** compact state does not already contain that accession. Recalculate Revenue, Net Income, Gross Profit, OCF, CapEx, FCF, and TTM with the existing extract / fiscal-quarter / verification code. Rebuild affected Layer 1, Layer 2, and Layer 3 files. |
| 8-K, 8-K/A | Record the accession (`recorded_8k`). Do **not** treat an 8-K earnings announcement as completed quarterly financials. No Company Facts download, no metric rebuild. |

Rules that stay the same: missing values stay `null` (never `0`); `write_json_if_changed` skips identical JSON; extra Layer 3 issuer files are never deleted; browser Layer 3 membership is not remapped; a failed gate or HTTP error leaves the previous live dataset in place.

`meta.generatedAt` (the site **Data updated** / **Screener updated** stamp) is bumped only when financial JSON changed. **SEC checked** is `lastSuccessfulSyncAt`. Because quiet nights do not deploy Pages, the live **SEC checked** time is the last check that shipped with a financial publish; the committed `daily-update.json` checkpoint still advances every successful night.

## Update steps

1. Load `lastSuccessfulSyncAt` and `unreconciledDates`. The index window is `min(lookback, lastSuccessfulSyncAt − 48h)` through `as_of`.
2. Page Latest Filings for the current official filing date. Read `master.idx` for the recovery window.
3. Deduplicate by accession. Drop accessions already in `daily-update.json`.
4. Map remaining CIKs onto the **current** dataset (`issuers.json` + `companies/*.json`).
5. For in-universe periodic filings, fetch Company Facts only when needed and rebuild through staging.
6. Run `evaluate_gate` against the previous `meta.json`. On failure, delete staging and keep the previous dataset; those accessions are not marked processed.
7. On a financial change: copy only changed files back, bump `generatedAt`, pack compact state, commit `[skip pages]`, and deploy Pages from this workflow.
8. On a quiet / 8-K-only / out-of-universe night: write `daily-update.json` (checkpoint + recorded accessions), skip aggregates, skip state pack, skip Pages.

## Commands

```bash
export SEC_USER_AGENT="stock-screener Your Name you@example.com"
screener -v daily-update --dry-run --lookback-days 10
screener -v daily-update --write-live --lookback-days 10
```

Without `--write-live`, `web/public/data` is not replaced (same hold-back as `screener build`).

## GitHub Actions minutes (private repo)

GitHub Free includes **2,000 Actions minutes / month** for private repositories. This job is designed to stay well under that if it stays incremental.

| Night | What runs | Typical minutes |
|---|---|---|
| No new in-universe 10-Q/10-K | Latest Filings pages + cached `master.idx` + optional `daily-update.json` commit. No npm, no Pages, no state pack. | 2–4 |
| A few companies changed | Company Facts for those CIKs, rebuild, gate, pack state, `npm ci` + test + build + Pages | 8–20 |
| Busy earnings day (dozens of CIKs) | Same path; Downloads stay per-CIK | 15–40 |

**Monthly estimate:** about **160–400 minutes** (for example 22 quiet nights × 3 min + 8 busy nights × 15 min). A stress month of 20 busy nights is still ~400–500 minutes.

**Risk of exceeding 2,000 minutes:** low while the job stays incremental and Pages is skipped on no-op nights. The allowance is at risk if `refresh.yml` (multi-hour full-universe rebuilds) is run often in the same month, if the daily job is changed to rebuild every company, or if Pages starts deploying on quiet nights (`npm ci` + Vite build is the expensive part). Overlapping runs are blocked by `concurrency: group: pages` with `cancel-in-progress: false`.

The `github-pages` environment is used only for the deploy job. If that environment has required reviewers, turn them off so a financial night does not sit in an approval queue.

## What is not in this job

- Full-universe NASDAQ Trader refresh (`refresh.yml`)
- Bulk `companyfacts.zip` / `submissions.zip`
- Layer 3 scoring
- Treating 8-K press releases as completed 10-Q/10-K financials
- Replacing missing financials with zero
- Deleting unused Layer 3 issuer JSON (preserves curated CIK identity)
- External databases, paid APIs, or servers
