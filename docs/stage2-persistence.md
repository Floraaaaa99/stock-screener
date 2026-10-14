# Stage 2 proposal: resumable persistence for the full-universe refresh

**Status:** proposal, for approval before the full-universe build. Stage 1 publishes only the committed validation
sample. Refreshed data goes to Pages deployment artifacts and is not committed.

## Constraints

- No force-pushed or orphan data branch, and no database. Everything stays within free GitHub limits for a public repository:
  - Actions minutes are free on standard runners, but each job is limited to 6 hours.
  - `actions/cache` holds 10 GB per repository and evicts entries unused for 7 days.
  - Release assets can be up to 2 GB per file.
  - A Pages site can be up to 1 GB.
- SEC fair-access rules apply: a declared User-Agent and at most 10 requests per second. The pipeline uses 8.
- Yahoo rate-limits aggressively, and GitHub-hosted runner IPs are shared.
- A partial universe must never be published as if it were the full one.

## Measured sizes (Stage 1, 22 companies) and full-universe projection (≈5,600 listings)

| Item | Stage 1 | Per company | Full universe (projected) |
|---|---|---|---|
| Raw Company Facts JSON | 49 MB | ≈2.2 MB | ≈12 GB raw, ≈0.9 GB gzipped |
| Rendered statements (`FilingSummary.xml` + `R*.htm`) | 33 MB, 480 files | ≈1.5 MB, ≈22 requests | ≈8 GB, ≈120k requests |
| Published dataset (`web/public/data`) | 460 KB | ≈20 KB | ≈110 MB, of which `screener.json` is ≈3 MB (≈0.5 MB gzipped) |

Raw downloads do not fit in `actions/cache`. A first full run that fetched everything one company at a time would need
about 125k SEC requests, roughly 4.5 hours at 8 requests per second, which is too close to the 6-hour job limit.

## Proposal

### 1. Persist compact derived state, not raw downloads

The state needed to resume or to run incrementally is small:

- Extracted revenue facts per CIK, only the 5 candidate concepts: a few KB each.
- Statement verification results per accession number. Filings are immutable, so a result never needs to be recomputed: about 1 KB per filing.
- The Yahoo field cache with per-field timestamps (already implemented).
- A run manifest: universe file dates, the companies processed so far, and the last completed checkpoint.
- The last published dataset, used as the comparison baseline.

Projected size is about 50–100 MB compressed.

### 2. Store it as a GitHub Release asset

- Keep one rolling release, `pipeline-state`, with the asset `state.tar.gz`, updated with `gh release upload --clobber` using the workflow's `GITHUB_TOKEN` (`contents: write`). This creates **no commits and rewrites no history**. Failed runs never overwrite the last good state.
- Also attach each published dataset as a dated asset, `dataset-YYYY-MM-DD.tar.gz`, keeping the last 8. This gives history and one-step rollback: redeploy an older asset.
- Everything stored is derived from public data. Secrets are never written to state; the SEC User-Agent stays a repository variable.
- Fallback if releases are not wanted: the last successful run's workflow artifact. Retention is at most 90 days, and finding the artifact needs an API lookup, so this option is less robust.

`actions/cache` is used only to speed things up, for example by keeping recent raw downloads within a run series. It is
never the source of truth, because entries can be evicted at any time.

### 3. Use the SEC bulk archive for Company Facts

Download the nightly `companyfacts.zip` from `https://www.sec.gov/Archives/edgar/daily-index/xbrl/` once per run. It is
a single file of over 1 GB. The pipeline then streams out only the CIKs and revenue concepts it needs. This replaces
about 5,600 API calls with one download and keeps raw JSON off disk.

### 4. Verify incrementally

Statement checks run only for accession numbers that are not already in the state. The first full run is the expensive one:

- It is split into checkpointed chunks of 250 companies.
- If the job reaches its time budget (5 hours), it saves state and finishes with status `incomplete`.
- The workflow then dispatches itself to continue. `workflow_dispatch` events created with `GITHUB_TOKEN` are allowed to start new runs. A manual re-run also works.

After that, weekly runs only fetch new filings: typically a few hundred companies, and around 1–2k companies in peak earnings weeks.

### 5. Gate publishing

A refresh deploys only when all of these hold:

- Every eligible NASDAQ Trader listing has a row, with an explicit N/A reason where data is missing.
- Coverage metrics do not fall sharply against the baseline. Initial thresholds: growth coverage may not drop by more than 5 points, and Yahoo profile coverage by no more than 10 points.
- Unit tests pass.

If any check fails, the previous deployment stays live and the run fails with a validation report attached.
`meta.json` always states the dataset mode (`sample` or `full`) and its counts.

### 6. Yahoo at full scale

- Sector and industry are cached for 30 days, so after the first run only about 1/30 of profiles are refreshed per day of age.
- Market cap and price need weekly refreshes for about 5,600 tickers. At about 1.2 seconds per `.info` call that is about 2 hours, with checkpointing and early stop on persistent 429s. Tickers that fail keep their last values and show their `as_of` date.
- **Option to evaluate:** batched price downloads, with one request per about 100 tickers, could replace most `.info` calls. Market cap would then be price × cached shares outstanding. This is adopted only if a validation run shows it matches Yahoo's `marketCap` closely.

### 7. Schedule

After two consecutive clean full manual runs, add `schedule: cron` (weekly, Saturday) to `deploy.yml`.

## Decisions requested

1. Approve the `pipeline-state` release asset as the persistent store. The alternative is workflow artifacts only.
2. Approve the SEC bulk `companyfacts.zip` download.
3. Approve the coverage-regression thresholds above, or provide your own.
4. Decide whether to evaluate batched Yahoo price downloads.
