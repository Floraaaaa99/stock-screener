# Layer 3 CIK identity migration (dry-run)

Prepared on PR #19. Production JSON was **not** published. PR #19 stays a draft. `refresh.yml` stays dispatch-only.

| | |
|---|---|
| Date | 2026-10-20 |
| Live | `web/public/data/layer3` — **5,542** v3 files, git-clean after the dry-run |
| Staging | `/tmp/layer3-full-v4/staging` — **5,543** v4 files |
| Rollback copy | `/tmp/layer3-rollback-v3-pre-cik-migration` (5,542 files; name+size fingerprint `8d77cb1275f942b4`) |
| Publish | **Dry-run only.** Gate result: `ok=true`, `published=false` |

## 1. What production `0000000000.json` is

One issuer. Not shared.

| Field | Value |
|---|---|
| File | `web/public/data/layer3/cik/0000000000.json` |
| `cik` | `0000000000` |
| Tickers | `["ZSTK"]` |
| Display ticker | `ZSTK` |
| Name | ZeroStack Corp. |
| Exchange | NASDAQ |
| SIC | 6199 — Finance Services (`modelApplicability: not_applicable`) |
| Status | extracted (v3), company_facts_only |
| OCF TTM | −5,601,000 |
| Cash | $2,640,000 as of 2026-06-30 |
| Filing URLs | `/edgar/data/0/…` (the unusable facts CIK) |

No other production Layer 3 file has payload CIK `0000000000`, ticker ZSTK, or ticker JHI.

## 2. ZSTK and JHI references

| Location | ZSTK | JHI |
|---|---|---|
| `issuers.json` | `0001790169` (only ticker on that CIK) | `0000759828` (only ticker on that CIK) |
| `companies/*.json` | `cik: 0001790169` | `cik: 0000759828` |
| `screener.json` | present (ZeroStack Corp., SIC 6199) | present (John Hancock Investors Trust, SIC 0000) |
| Production Layer 3 file | `0000000000.json` only | **none** |
| Staging Layer 3 file | `0001790169.json` extracted v4 | `0000759828.json` insufficient_facts v4 |
| `layer3.json` index | 881-byte index; no embedded rows | same |
| Layer 2 | ticker-keyed row; no CIK | ticker-keyed row; no CIK |

`issuers.json` has no ticker mapped to `0000000000`. JHI is a **new add**, not a second occupant of the zero file.

Seven other tickers have an empty `issuers.json` CIK (`ASBH`, `FRBA`, `HIFS`, `NBN`, `RCBC`, `SSBI`, `TOWN`). They have no Layer 3 issuer files and are outside this allowlist.

## 3. Browser-saved Layer 3 list

Membership is `localStorage` key `stock-screener.layer3.membership.v1`. Identity is `issuerIdFor(ticker, cik)`:

- CIK known → `cik:{10-digit}`
- else → `ticker:{TICKER}`

`cikByTicker` comes from `issuers.json`. Adding ZSTK today already stores `cik:0001790169` and fetches `layer3/cik/0001790169.json`, which **does not exist in production yet** (404). Adding JHI already stores `cik:0000759828` (also no production file).

A list saved from the production issuer payload (`cik: 0000000000`) would be `cik:0000000000`. Deleting `0000000000.json` without a client remap would 404 that entry. `metricsForEntry` can fall back to ticker on the index, but the index has no rows and metrics are lazy-loaded by CIK file.

This PR:

- rejects zero CIKs in web `normalizeCik` (same as the pipeline)
- rewrites a saved `cik:0000000000` + ZSTK entry to `cik:0001790169` on load and persists it
- does **not** rewrite any other ticker that happens to carry a zero CIK

## 4. Explicit migration (general checks stay on)

`APPROVED_CIK_MIGRATIONS` is one row:

`0000000000.json` + ticker **ZSTK** + explicit zero payload CIK → `0001790169.json` / `0001790169` + ticker **ZSTK**.

`plan_layer3_publish` / `validate_layer3_publish` still reject:

- staging zero / invalid CIK, filename ≠ payload, duplicate payload CIKs
- live identity errors that are **not** this allowlisted file
- unapproved remaps (example: HEI moving files)
- a zero file occupied by any ticker other than ZSTK (example: JHI in `0000000000.json`)
- extracted → `pending_analysis`
- unexpected live deletions

`--publish-dry-run` is incompatible with `--publish`. `publish_layer3` still refuses live dest without `--write-live` and still writes `layer3.rollback-*` only if a real publish is later approved.

## 5. Dry-run publish plan

Command (read-only):

```bash
screener layer3 --output web/public/data/layer3.json \
  --staging-dir /tmp/layer3-full-v4/staging --publish-dry-run
```

Exit 0. `published: false`. Production files unchanged.

| Action | Count | Files |
|---|---:|---|
| Add | 2 | `0000759828.json` (JHI, insufficient_facts); `0001790169.json` (ZSTK, extracted) |
| Remove | 1 | `0000000000.json` (approved ZSTK remap) |
| Replace | 5,541 | every current production issuer file except `0000000000.json` |
| Approved migrations | 1 | ZSTK `0000000000` → `0001790169` |
| Errors | 0 | — |

Live 5,542 − 1 + 2 = staging 5,543.

The full 5,541 replacement names are in `/tmp/layer3-publish-plan.json` (not committed). Rollback bytes match production (`8d77cb1275f942b4`).

## 6. Publish on PR #19 (2026-10-20)

Approved and executed on `cursor/layer3-data-model-be5a` only. `publish_layer3(..., write_live=True)` with the ZSTK allowlist. Staging and production fingerprints still matched the dry-run immediately before the write.

| Check | Result |
|---|---|
| Issuer files | **5,543** |
| Unique payload CIKs / filename matches | **5,543 / 0 mismatches** |
| Index | schema **3**, extract **4**, `counts.issuers` **5543**, rows **0** |
| Extraction | extracted 4,318 · insufficient_facts 1,173 · pending_analysis 52 |
| `0000000000.json` | **removed** |
| ZSTK | `0001790169.json` extracted; OCF TTM −5,601,000 |
| JHI | `0000759828.json` insufficient_facts |
| HEI / MSFT / NVDA | extracted v4; OCF and cash unchanged vs v3; HEI GP derived $2,091,317,000 |

Published tree size: **320.15 MB** issuer files + **3,114 B** index.

Recoverable v3 backup (committed, not `/tmp` only):

- Archive: `docs/validation/layer3-v3-pre-publish.tar.gz` (4.93 MB, sha256 `b5d1775c65c03cfd7559ec067c3b51fed83a0ded5b39ef3842247b6a94df7c1a`)
- Manifest: `docs/validation/layer3-v3-pre-publish.manifest.json`
- Local exploded copy (gitignored): `/workspace/backups/layer3-v3-pre-publish` (5,542 files)

Restore:

```bash
tar -C web/public/data -xzf docs/validation/layer3-v3-pre-publish.tar.gz
```

This branch was **not** merged to `main`, `refresh.yml` was **not** enabled, and GitHub Pages was **not** deployed.
