# Layer 3 identity, regressions, and ratio flags

Follow-up on the full-universe staging report. Production JSON was not published. PR #19 stays a draft.

| | |
|---|---|
| Date | 2026-10-20 |
| Staging | `/tmp/layer3-full-v4/staging` regenerated after the fixes (199 s, exit 0) |
| Unique issuers | **5,543 files = 5,543 payload CIKs = 5,543 index rows** |
| Production | **5,542 files, git-clean** |
| Publish | Dry-run now **passes** with the explicit ZSTK remap. Production was **not** published. Do not merge. |

## 1. CIK identity

Issuer identity is the `issuers.json` CIK (filename and `payload.cik`). Company Facts `cik` is never used as identity. Zero / missing / `0000000000` facts CIKs are ignored.

| Issuer | File | Payload CIK | Status |
|---|---|---|---|
| ZSTK | `0001790169.json` | `0001790169` | extracted. Zip has no `cik` field (`entityName` ZeroStack). |
| JHI | `0000759828.json` | `0000759828` | insufficient_facts. Zip has no `cik` field. |

Filename / payload mismatches: **0**. Duplicate payload CIKs: **0**. Zero CIKs in staging: **0**.

`validate_layer3_publish` now rejects:

- zero / invalid payload CIK
- filename ≠ payload CIK
- duplicate payload CIKs
- extracted → `pending_analysis`
- unexpected live-file deletions, including ticker remaps

Against current production, the general checks still fire. The one confirmed remap — production `0000000000.json` (ZSTK only) → staging `0001790169.json` — is now classified by `APPROVED_CIK_MIGRATIONS` instead of treated as an error. Other remaps, other zero-CIK occupants, duplicates, filename mismatches, extracted→pending, and unexpected deletes remain hard errors.

See `docs/validation/layer3-cik-migration.md` for the dry-run add/replace/remove list. Production JSON was not modified.

## 2. v3 → v4 overlapping metrics (23 issuers)

Compared OCF / CapEx / FCF / opinc / interest / D&A / EBITDA / cash / debt. Extracted → pending remains **0**.

| Category | Count | Issuers |
|---|---:|---|
| New SEC filing (newer `dataAsOf` / accn) | 20 | ACN, FAST, CMC, SOTK, TRV, LOOP, MRSH, AAME, EDUC, WINA, BMRA, RMCF, FNGR, NTRP, PLUN, ETS, ILLU, CMTL, CHRN, BREZ |
| Same quarter, values moved (amendment / restatement) | 2 | ROLR, GPRO |
| CAD stocks newly visible after currency-lock fix | 1 | CP (gained cash/debt; OCF still `no_concept`) |
| Previously lost, now restored | 1 dropped | **CGC** no longer differs |

### CHRN — new filing + gap, not a carry-forward

10-Q filed 2026-10-14, period ended 2026-08-31 (spine moved off 2026-03-31). Latest quarter is present; the prior slot (2026-05-31) is `missing_quarter`, so TTM is `gap_in_quarters`. Cash/debt now align to August. Stale March TTM was **not** copied forward.

### CMTL — new 10-K + unaligned stocks

10-K filed 2026-10-14, FY ended 2026-07-31. OCF/FCF/cash updated from the new filing. Interest newest tag is still 2026-04-30 → `ttm_window_not_aligned`. ST/LT debt not within ±10 days of 2026-07-31 → `stock_not_as_of_latest_quarter`. Expected alignment drop, not an extractor wipe.

### CGC — fixed (currency lock)

v4 `FLOW_CONCEPTS` includes `NetIncomeLoss`. CGC NI is tagged CAD+USD, so `_pick_unit` preferred USD and the global bag locked to USD. CAD-only OCF/CapEx/opinc then looked like `no_concept`.

Fix: Layer 3 picks issuer currency from OCF / revenue / cash first. CGC is CAD again. OCF TTM **−78,480,000**, identical to v3. Not a stale copy — re-extracted from the current zip.

### Unresolved

- **CHRN** TTM stays null until the missing May quarter is tagged. Correct.
- **CMTL** debt/interest stay null until the 10-K tags instants on 2026-07-31.
- **CP** cash/debt now extract in CAD; OCF still `no_concept` (no usable CAD/USD operating series in the zip).
- 20 issuers with a new quarter will keep differing from the 2026-10-16 v3 snapshot until production is rebuilt from this zip.

## 3. Ratio integrity

### 39 GP / COGS / Revenue conflicts

Raw GP and COGS are still kept (`identity=concept_scope_mismatch`, not overwritten). Derived ratios that mix those series are **suppressed** (status `missing`, computed number in `unreliableTtm` / `unreliableValue`, `qualityFlags: ["incompatible_inputs"]`):

| Metric | Suppressed |
|---|---:|
| Gross margin | 39 |
| DPO | 39 |
| CCC | 39 |
| DIO | 31 (8 already `not_applicable`) |

Issuer flag `concept_scope_mismatch` on all 39. Example: FLS gross margin is missing with `unreliableTtm` stored; GP TTM 1,570,088,000 remains.

Operating / net / FCF margins are unchanged (they do not use GP/COGS).

### Extreme DSO / DIO / DPO

Raw values are preserved. `qualityFlags: ["extreme_ratio"]` when outside inspect-only bands (DSO 0–400, DIO 0–500, DPO 0–400, CCC −400–700, current ratio 0–80). No clamping.

| Example | Value | Why |
|---|---|---|
| NEON DPO | 3,635 days | GP+COGS=Rev holds. COGS TTM only $24k vs average AP $239k. Flagged, not nulled. |
| AENT DSO | 14,085 days | Revenue TTM $2.67M vs average AR $103M. COGS missing, so DIO/DPO already missing. Flagged. |

Counts on this staging run: DPO 91, DIO 48, CCC 35, DSO 15, current ratio 13.

## 4. Coverage after the fixes

Percents of **5,543** issuer files.

| Status | Count | % |
|---|---:|---:|
| Extracted | 4,318 | 77.9% |
| Insufficient facts | 1,173 | 21.2% |
| Pending analysis (absent from zip) | 52 | 0.9% |
| Model not_applicable | 1,222 | 22.0% |

Gross margin extracted is now **1,930** (the 39 conflicts no longer count as clean extracted). FCF TTM = OCF − CapEx failures: **0**. `statement_verified`: **0**. Derived provenance gaps: **0**.

## 5. Tests and CI

- Local pipeline: **194 passed**.
- New cases: canonical CIK wins over facts CIK 0; approved ZSTK remap is classified; unapproved remaps and a non-ZSTK zero-CIK file still block; `--publish-dry-run` writes nothing; conflict suppresses derived margins; extreme DSO flagged not clamped; CAD OCF survives a USD+CAD NI tag.

CIK migration dry-run is in `docs/validation/layer3-cik-migration.md`. Production was not published. Still waiting for approval before publish or merge.
