# Layer 3 v4 full-universe staging report

Staging-only rebuild of every issuer in `issuers.json`. Production `web/public/data/layer3/cik/*.json` was not written, deleted, or published.

| | |
|---|---|
| Date | 2026-10-20 |
| Branch / PR | `cursor/layer3-data-model-be5a` / draft PR #19 |
| Source | SEC `companyfacts.zip` via `download_companyfacts_zip` → `pipeline/.cache/sec/bulk/companyfacts.zip` |
| Zip | 1,410,727,880 bytes · 20,477 members · fetched 2026-10-20 21:45 UTC |
| Command | `screener layer3 --data-dir web/public/data --output /tmp/layer3-full-v4/layer3.json --facts-zip … --mode full --staging-dir /tmp/layer3-full-v4/staging` |
| Flags omitted | `--publish` · `--write-live` |
| Runtime | **199 seconds** · exit 0 · `cli.err` empty |
| Staging tree | `/tmp/layer3-full-v4/staging` (317 MB; issuer JSON 320,0 MB / 57.7 KB avg) |
| Production | **5,542 files unchanged** · git clean · HEI/MSFT/NVDA SHA-256 prefixes `bbc5b0387f2e778f` / `73965d43fa3c35c7` / `ee7997f28b740338` |
| Validator | `python -m scripts.layer3_validate_staging` → `/tmp/layer3-full-v4/validation.json` |

**Not done (waiting for approval):** publish staging over production · merge PR #19 · enable `refresh.yml`.

## Headline

The rebuild completed safely. All 5,543 `issuers.json` CIKs were written to a sidecar. No previously extracted issuer became `pending_analysis`. Overlapping v3 TTM / cash / debt values match on 4,293 of 4,316 compared issuers (23 numerical differences, mostly a newer Company Facts snapshot). HEI / MSFT / NVDA continuity from the sidecar sample still holds on this full run.

Do **not** publish yet. Two files write the `issuers.json` CIK as the filename but overwrite `payload.cik` from Company Facts (`0000000000`). Publishing would delete production `0000000000.json` (ZSTK) and add `0001790169.json` / `0000759828.json`. `validate_layer3_publish` keys by payload CIK and therefore returned no errors — that check is not sufficient for this remap.

## Coverage

Universe = **5,543 issuer files** (one per `issuers.json` CIK). Percents use that denominator unless noted.

The staging index reports 5,542 issuers because `_scan_issuer_dir` keys by `payload.cik`, and JHI + ZSTK both carry `cik=0000000000`. File-level counts below are the ground truth.

### Extraction / model / scoring

| Status | Count | % of 5,543 |
|---|---:|---:|
| `extracted` | 4,318 | 77.90% |
| `insufficient_facts` | 1,173 | 21.16% |
| `pending_analysis` | 52 | 0.94% |
| Model applicable | 4,321 | 77.95% |
| Model `not_applicable` (financial SIC 60–64 / 67) | 1,222 | 22.05% |
| Scoring `not_implemented` | 5,543 | 100% |
| Verification `company_facts_only` | 4,318 | 77.90% |
| Verification `not_checked` | 1,225 | 22.10% |
| `statement_verified` anywhere | **0** | 0% |
| Inputs `ready` (index) | 2,687 | — |
| Inputs `pending_data_verification` (index) | 2,803 | — |

v3 production index (for comparison): extracted 4,316 · pending 54 · insufficient 1,173. Net: +2 extracted, −2 pending, insufficient unchanged. No extracted → pending.

### Metric coverage

| Metric | Extracted | Missing | Not applicable | Extracted % |
|---|---:|---:|---:|---:|
| Revenue | 3,125 | 2,418 | 0 | 56.4% |
| Net income | 3,927 | 1,616 | 0 | 70.8% |
| Gross profit | 2,025 | 3,518 | 0 | 36.5% |
| COGS / cost of revenue | 2,033 | 3,510 | 0 | 36.7% |
| OCF | 3,916 | 1,627 | 0 | 70.6% |
| CapEx | 2,886 | 2,657 | 0 | 52.1% |
| FCF | 2,858 | 2,685 | 0 | 51.6% |
| Cash | 4,077 | 1,466 | 0 | 73.6% |
| Total debt | 2,091 | 3,452 | 0 | 37.7% |
| Accounts receivable | 2,711 | 2,832 | 0 | 48.9% |
| Inventory | 1,911 | 707 | **2,925** | 34.5% (52.8% N/A) |
| Accounts payable | 2,868 | 2,675 | 0 | 51.7% |
| Current assets | 3,576 | 1,967 | 0 | 64.5% |
| Current liabilities | 3,558 | 1,985 | 0 | 64.2% |

Inventory `not_applicable` is the only coverage-key N/A. That is “no us-gaap inventory tag,” not a forced software rule. Banks / REITs / funds in the 1,222 model-N/A set can still have extracted cash-flow or income tags; those are kept and labeled `modelApplicability: not_applicable`.

### Reported vs derived

Among the 14 coverage keys above, valued observations are **36,026 extracted** and **5,536 derived**.

| Metric | Reported (`extracted`) | Derived | Derived from |
|---|---:|---:|---|
| Revenue | 3,125 | 0 | tagged series |
| Net income | 3,927 | 0 | tagged series |
| Gross profit | 1,548 | **477** | `revenue_minus_cost_of_revenue` when GP tag is missing/stale |
| COGS | 1,923 | **110** | `revenue_minus_gross_profit` when COGS tag is missing/stale |
| OCF / CapEx / Cash / AR / Inv / AP / CA / CL | all reported | 0 | tagged series |
| FCF | 0 | 2,858 | OCF − CapEx |
| Total debt | 0 | 2,091 | ST + LT (or a single total-debt concept) |

Every derived valued metric in the provenance check (`fcf`, `ebitda`, margins, WC ratios, net debt, DSO/DIO/DPO/CCC) has `formula` or `derivedFrom`. Count of derived-without-provenance: **0**.

HEI on this full run matches the sidecar: GP $2,091,317,000 derived, COGS $3,085,439,000 extracted, identity exact, gross margin 40.40%.

### Missing reasons

`unknown` = 52 on every metric — the `pending_analysis` issuers, all **absent from the zip** (closed-end funds, royalty trusts). That is a source-coverage gap, not an extractor crash.

| Metric | Dominant reasons (excluding the 52 pending) |
|---|---|
| Revenue | `no_concept` 1,825 · `ttm_window_not_aligned` 261 · `gap_in_quarters` 249 · `insufficient_quarters` 31 |
| Net income | `no_concept` 1,159 · `gap_in_quarters` 220 · `insufficient_quarters` 165 · `ttm_window_not_aligned` 20 |
| Gross profit | `no_concept` 3,146 · `ttm_window_not_aligned` 221 · `gap_in_quarters` 88 · `insufficient_quarters` 11 |
| COGS | `no_concept` 2,912 · `ttm_window_not_aligned` 412 · `gap_in_quarters` 119 · `insufficient_quarters` 15 |
| OCF | `no_concept` 1,167 · `insufficient_quarters` 243 · `gap_in_quarters` 165 |
| CapEx | `no_concept` 1,756 · `ttm_window_not_aligned` 592 · `gap_in_quarters` 193 · `insufficient_quarters` 64 |
| FCF | `missing_ocf` 1,575 · `missing_capex` 1,058 (downstream of the two above) |
| Cash | `no_concept` 1,181 · `stock_not_as_of_latest_quarter` 233 |
| Total debt | `no_concept` 2,278 · `stock_not_as_of_latest_quarter` 757 · `missing_short_term_debt` 189 · `missing_long_term_debt` 176 |
| AR | `no_concept` 2,379 · `stock_not_as_of_latest_quarter` 401 |
| Inventory (missing, not N/A) | `no_concept` 374 · `stock_not_as_of_latest_quarter` 281 |
| AP | `no_concept` 2,316 · `stock_not_as_of_latest_quarter` 307 |
| Current assets | `no_concept` 1,873 · `stock_not_as_of_latest_quarter` 42 |
| Current liabilities | `no_concept` 1,876 · `stock_not_as_of_latest_quarter` 57 |

**Legitimately not applicable vs genuine gaps**

- Inventory `not_applicable` (2,925) and financial-SIC `modelApplicability` (1,222) are expected. Do not treat them as extract failures.
- `no_concept` on GP/COGS is common (banks, insurers, many funds, some miners/REITs). Missing stays `null`.
- `no_concept` on revenue/OCF/cash for foreign issuers (AEM, CNI, CP) is a Company Facts IFRS/us-gaap coverage limit, not a zero.
- `ttm_window_not_aligned` / `gap_in_quarters` are real data-quality limits: the tag exists but four non-overlapping quarters do not line up.
- `stock_not_as_of_latest_quarter` means the instant is more than ±10 days from the flow spine. Not back-filled.

Examples: AEM (Agnico Eagle) missing revenue/NI/OCF/cash `no_concept`; BRID / CALM revenue `gap_in_quarters`; MATX / HWM / LNG COGS `ttm_window_not_aligned`; AIR / ACU total debt `missing_short_term_debt`; BDL cash `stock_not_as_of_latest_quarter`.

## Data integrity

### Extraction continuity (v3 → v4)

| Transition | Count | Notes |
|---|---:|---|
| extracted → extracted | 4,316 | all live extracted issuers stayed extracted |
| extracted → pending_analysis | **0** | publish safety condition holds |
| insufficient_facts → insufficient_facts | 1,170 | |
| pending_analysis → pending_analysis | 52 | still missing from zip |
| pending_analysis → insufficient_facts | 2 | GUT, FRTT — facts present, nothing usable |
| insufficient_facts → extracted | 2 | BREZ (cash now present), OSG |
| absent → insufficient_facts | 1 | JHI (`0000759828`) — not in the v3 file set |

### Overlapping v3 vs v4 numbers

Compared OCF / CapEx / FCF / operating income / interest / D&A / EBITDA TTM and cash / ST / LT / total / net debt.

- Issuers with **any** unexpected difference: **23** (0.53% of 4,316 overlapping extracted issuers).
- FCF TTM = OCF − CapEx wherever all three exist: **0** failures.
- `dataAsOf` vs first OCF quarter-end: **0** mismatches.
- Cash end vs OCF end > ±10 days: **0**.

The 23 diffs line up with a **newer Company Facts snapshot** (v3 index `generatedAt` 2026-10-16; this zip 2026-10-20), not with the GP fallback or ±10-day matcher rewriting HEI/MSFT/NVDA.

| Kind | Notable issuers |
|---|---|
| Values moved a few percent (new quarter / restatement) | ACN, FAST, CMC, SOTK, TRV, LOOP, MRSH, AAME, EDUC, WINA, BMRA, RMCF, FNGR, NTRP, ROLR, GPRO, ILLU, PLUN |
| Flow TTM **lost** (now null) | **CHRN** (ChronoScale) — all flow TTM gone; cash $4.0M → $15.2M; debt newly present. **CGC** (Canopy Growth) — all flow TTM gone; still extracted via other tags. |
| Debt / interest **lost** | **CMTL** (Comtech) — OCF/FCF/cash still present and updated; ST/LT/total/net debt and interest became null (alignment or concept dropped in the new zip). |
| Cash **gained** | BREZ $130,963 |

HEI / MSFT / NVDA overlapping TTM and latest cash/debt are bit-identical to production v3.

### GP + COGS = Revenue

| Result | Count |
|---|---:|
| Holds (`values_agree`) | 1,935 |
| Fails | **39** (exactly the `concept_scope_mismatch` set) |
| Skipped (one of GP / COGS / Revenue missing) | 3,569 |
| Labeled `gross_plus_cogs_equals_revenue` | 1,348 |
| Labeled `unverified_without_revenue` | 44 |
| Labeled `concept_scope_mismatch` | 39 |

The 39 failures are **kept as reported tags**, not overwritten. Examples:

| Ticker | GP TTM | COGS TTM | Revenue TTM | Note |
|---|---:|---:|---:|---|
| TFX | 1,239M | 690M | 2,255M | GP + COGS ≠ Rev; both tags kept |
| AMTX | 23.9M | 206.2M | 219.8M | close but outside tolerance |
| REX | 179.1M | 537.1M | 658.6M | 57.7M gap |
| IT (Gartner) | 4,530M | 1,963M | 6,464M | 29M gap |
| VICR | 277.4M | 194.3M | 724.0M | scope mismatch |
| MO | 14,769M | 5,675M | 23,457M | excise / net-revenue scope |
| FLS | 1,570M | 3,064M | **0** | revenue concept present but TTM 0 — treat as a quality flag, not a foot |
| NSYS | 20.5M | 104.2M | 10.6M | incompatible scopes |

Derived GP examples that **do** foot: ABT, APD, ADP, BDX, BMY, BC, CPB, UHAL (and HEI).

### Unusual ratios

870 values sit outside the validator’s wide bands. Most are pre-revenue biotech / SPACs / banks, not extract bugs.

| Metric | Flags | Band | Extreme examples |
|---|---:|---|---|
| Net margin | 249 | (−5, 2) | STTK −52.6 · ALLO −35.7 · RNAC (see op. margin) |
| Operating margin | 193 | (−5, 2) | RNAC −105 · STTK −55.8 · ALLO −38.9 |
| FCF margin | 137 | (−5, 2) | RNAC −53.2 · ALLO −22.1 · ASTS −14.2 |
| DPO | 91 | (0, 400) | NEON 3,635 days · QURE 1,033 · BURU 931 |
| Cash conversion | 58 | (−5, 20) | CUZ 67 · OMC 50 · VIP −41.5 |
| DIO | 48 | (0, 500) | EDUC 888 · HRTX 660 · BF-A 611 |
| CCC | 35 | (−400, 700) | ONCO −5,853 · EDUC 838 |
| Gross margin | 31 | (−0.5, 1.5) | MVIS −5.51 · ISPC −1.08 · LCID −0.97 |
| DSO | 15 | (0, 400) | AENT 14,085 · KOPN 1,539 |
| Current ratio | 13 | (0, 80) | WTG 451 · DYNC 296 |

Banks (MTB, ZION, IBCP) with FCF/net margin > 2 are model-N/A issuers that still have tags. NEON DPO 3,635 days and AENT DSO 14,085 days are the clearest “ratio is computed, inputs look inconsistent” cases — leave them visible, do not clamp.

### CIK identity (do not publish until reviewed)

| File | Payload `cik` | Ticker | Status |
|---|---|---|---|
| production `0000000000.json` | `0000000000` | ZSTK | extracted (v3) |
| staging `0001790169.json` | `0000000000` | ZSTK | extracted (v4) — `issuers.json` CIK is 0001790169 |
| staging `0000759828.json` | `0000000000` | JHI | insufficient_facts — new file, not in v3 |

`analyze_layer3_facts` overwrites `base.cik` with the Company Facts `cik` field (0 → `0000000000`). Filename uses the `issuers.json` key. Index then collapses both files onto one payload CIK.

## Runtime, size, failures

| Item | Value |
|---|---|
| Rebuild wall time | 199 s |
| Extraction process failures | **0** (exit 0, empty stderr) |
| Issuers written | 5,543 |
| Staging issuer bytes | 319,993,957 (~305 MB) |
| Staging tree | 317 MB including index |
| Staging index | 3,114 B · schema 3 / extract 4 · `generatedAt` 2026-10-20T21:49:27Z |
| Production issuer bytes | 78,392,268 (~75 MB) · 5,542 files · schema 2 / extract 3 · `generatedAt` 2026-10-16T04:06:02Z |
| Typical dense issuer | HEI 87 KB · MSFT 89 KB · NVDA 88 KB (v3 ~21 KB) |
| Zip | 1.41 GB / 20,477 members |
| Pending because zip has no member | 52 / 52 pending issuers |

v4 size landed in the 250–400 MB band estimated in `layer3-data-model.md`.

## Production safety

- `git status` on `web/public/data/layer3` and `layer3.json`: clean.
- Production file count still 5,542.
- No `--publish`, no `--write-live`.
- `refresh.yml` still does not run `screener layer3`.
- PR #19 remains a draft.

## Recommendation

Staging is complete enough to review. **Wait for approval** before:

1. Publishing `/tmp/layer3-full-v4/staging` over `web/public/data/layer3`.
2. Merging PR #19.
3. Enabling the proposed `refresh.yml` Layer 3 step.

Before any publish, fix the payload-CIK overwrite so ZSTK/JHI keep `issuers.json` CIKs, and decide whether production `0000000000.json` is deleted or remapped to `0001790169.json`. Re-run `validate_layer3_publish` after that fix; the current empty error list is not a green light.
