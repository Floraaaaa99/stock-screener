# Stage 2: resumable persistence for the full-universe refresh

**Status:** SEC-only pipeline is implemented. The live GitHub Pages site remains the last validated sample until a complete full-universe run passes completeness and filing-validation gates. There is no weekly schedule yet.

## Where the ~125,000 SEC request figure came from

Stage 1 measured, for 20 domestic issuers (plus 2 foreign filers who need no statements):

- 22 Company Facts API calls (one JSON blob per CIK)
- 240 filings that had to be opened
- 2 files per filing (`FilingSummary.xml` plus one income-statement `R*.htm`) = 480 statement files
- 1 ticker-map download

That is **12 filings per domestic issuer**, and **2 HTTP requests per filing**.

Scaled to the current NASDAQ Trader universe of **5,593** eligible listings, using Stage 1's foreign-filer share (2/22) as a rough prior (~5,085 domestic issuers):

| Step | Requests | Notes |
|---|---|---|
| Ticker map | 1 | `company_tickers_exchange.json` |
| Company Facts API | ≈5,593 | one GET per CIK; avoided by `companyfacts.zip` |
| Submissions API | ≈5,593 | one GET per CIK for SIC; avoided by `submissions.zip` |
| Statement files | ≈5,085 × 12 × 2 ≈ **122,000** | first run, nothing cached |
| **Total without bulk** | **≈128,000** | the “125,000” headline |

At the pipeline cap of 8 requests/second that is **≈4.4 hours** of SEC HTTP, plus parsing and retries — too close to GitHub Actions' 6-hour limit, and it would re-download 12 GB of Company Facts JSON.

## Runtime with the nightly bulk zips

Approved bulk files:

- `https://www.sec.gov/Archives/edgar/daily-index/xbrl/companyfacts.zip` (~1.41 GB)
- `https://www.sec.gov/Archives/edgar/daily-index/bulkdata/submissions.zip` (~1.57 GB, SIC codes)

| Step | First full run | Later weekly run |
|---|---|---|
| `companyfacts.zip` | 1 request, a few minutes | 1 request if stale (>20 h) |
| `submissions.zip` | 1 request | 1 request if stale |
| Ticker map | 1 | 1 if stale |
| Statement files | still ≈122,000 if the statement cache is empty | only **new** accessions (typically hundreds; 1–2k in an earnings week) |
| HTTP time at 8 rps | **≈4.2 hours** of statements | **≈0.2–1.5 hours** |
| GitHub job | 5-hour budget, 5.5-hour timeout; exit 3 saves state | usually one job |

The bulk zips do **not** shrink the first-run statement fetch. That cost is paid once and then stored in compact state (parsed revenue rows per accession, not the raw HTML).

`screener estimate` prints these numbers from code.

## What is stored

A rolling GitHub Release named `pipeline-state` holds:

- `state-<run_id>.tar.gz` — dated, never the only copy
- `state.tar.gz` — pointer to the latest verified archive, updated only after a checksum round-trip
- matching `.sha256` sidecars

Inside the archive (see `screener_pipeline/state.py`):

- `manifest.json` — `version`, `createdAt`, SHA-256 of every member
- `facts/*.json` — compact revenue facts per CIK
- `statements/*.json` — parsed income-statement revenue rows per accession
- `sic/*.json` — compact SEC SIC records per CIK

Integrity and recovery:

1. Pack locally and write `state.tar.gz.sha256`.
2. Unpack to a temp dir and verify every file hash (`screener unpack-state`).
3. Upload the dated asset first.
4. Download that dated asset and confirm SHA-256.
5. Only then `--clobber` the `state.tar.gz` pointer.
6. If step 5 fails, the dated asset remains and the previous pointer is unchanged.

`actions/cache` still holds the zips and NASDAQ files to speed reruns. It is not the source of truth.

## Publishing gates

A refresh is **complete** only when `run.status == complete`. Incomplete runs write staging data under `pipeline/.cache/state/` and **do not** swap `web/public/data/`.

`screener gate` also fails when:

- the dataset mode is `partial` (`--limit`)
- a full run's row count ≠ NASDAQ Trader eligible listings
- the quarter-mismatch ratio exceeds **10%** of checked quarters
- growth coverage falls more than **5 percentage points** vs the last complete baseline of the same mode
- `--publish` is set on anything other than a complete full-universe dataset

`--write-live` overwrites `web/public/data/` only when the dataset is a sample, or when the publish gate passes for a full run. Pages deploy (`deploy.yml`) accepts `dataset.mode=sample`, or `full` with `gate.ok`.

Yahoo coverage is not a gate. Yahoo is not a data source.

## How to run

```bash
export SEC_USER_AGENT="stock-screener Your Name you@example.com"
screener -v build --universe full --time-budget-hours 5
# exit 0 = complete (held back from Pages unless --write-live); exit 3 = incomplete, re-run to resume
screener pack-state --dest /tmp/state.tar.gz
screener gate --meta pipeline/.cache/state/dataset-full/meta.json
screener gate --meta pipeline/.cache/state/dataset-full/meta.json --publish
```

Manual Actions workflow: **Refresh full universe**. Re-run it to resume. Do not add `schedule:` until two consecutive complete manual runs have passed the publish gate.
