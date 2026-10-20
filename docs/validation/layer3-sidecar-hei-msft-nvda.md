# Layer 3 sidecar: HEI / MSFT / NVDA (v3 vs v4)

Real Company Facts extract. Staging only. Production `web/public/data/layer3/cik/*.json` was not written.

| | |
|---|---|
| Date | 2026-10-20 |
| Source | SEC per-CIK Company Facts API via `SecClient.companyfacts` (cached under `pipeline/.cache/sec/companyfacts`) |
| Command | `python pipeline/scripts/layer3_sidecar_sample.py --output /tmp/layer3-sidecar` |
| Mode | `--mode full --ciks 0000046619,0000789019,0001045810 --publish` omitted |
| Production files | 5,542 unchanged (HEI/MSFT/NVDA SHA-256 unchanged) |
| GitHub CI on PR #19 | Pipeline tests and web typecheck/tests/build both passed |

## Headline

Existing v3 OCF, CapEx, FCF TTM, cash, and debt match v4 exactly on all three issuers. Quarter-end spines match. New v4 fields populate. Missing stays `null`. Nothing is labeled `statement_verified`.

**HEI Gross Profit is now derived.** us-gaap `GrossProfit` is still stale (newestEnd 2020-10-31). Because current Revenue and `CostOfRevenue` share the same fiscal spine, v4 sets GP = Revenue − COGS = **2,091,317,000** (`calculationMethod=derived`). Gross margin is **40.40%**. Reported COGS is unchanged. MSFT and NVDA still use tagged GP + COGS that foot to revenue.

## Continuity (v3 TTM / latest vs v4)

Values in USD.

| Issuer | Metric | v3 | v4 | Delta |
|---|---|---:|---:|---|
| HEI | OCF TTM | 1,111,232,000 | 1,111,232,000 | unchanged |
| HEI | CapEx TTM | 80,952,000 | 80,952,000 | unchanged |
| HEI | FCF TTM | 1,030,280,000 | 1,030,280,000 | unchanged |
| HEI | Operating income TTM | 1,244,555,000 | 1,244,555,000 | unchanged |
| HEI | Interest TTM | 132,404,000 | 132,404,000 | unchanged |
| HEI | D&A TTM | 217,592,000 | 217,592,000 | unchanged |
| HEI | EBITDA TTM | 1,462,147,000 | 1,462,147,000 | unchanged |
| HEI | Cash | 240,959,000 (2026-07-31) | same | unchanged |
| HEI | Short-term debt | 3,513,000 | 3,513,000 | unchanged |
| HEI | Long-term debt | 2,537,660,000 | 2,537,660,000 | unchanged |
| HEI | Total debt | 2,541,173,000 | 2,541,173,000 | unchanged |
| HEI | Net debt | 2,300,214,000 | 2,300,214,000 | unchanged |
| MSFT | OCF TTM | 182,935,000,000 | 182,935,000,000 | unchanged |
| MSFT | CapEx TTM | 115,948,000,000 | 115,948,000,000 | unchanged |
| MSFT | FCF TTM | 66,987,000,000 | 66,987,000,000 | unchanged |
| MSFT | Operating income TTM | 155,237,000,000 | 155,237,000,000 | unchanged |
| MSFT | Interest TTM | missing (`ttm_window_not_aligned`) | missing (same) | unchanged |
| MSFT | D&A TTM | 39,100,000,000 | 39,100,000,000 | unchanged |
| MSFT | EBITDA TTM | 194,337,000,000 | 194,337,000,000 | unchanged |
| MSFT | Cash | 20,935,000,000 (2026-06-30) | same | unchanged |
| MSFT | Short-term debt | 9,227,000,000 | 9,227,000,000 | unchanged |
| MSFT | Long-term debt | 31,067,000,000 | 31,067,000,000 | unchanged |
| MSFT | Total debt | 40,294,000,000 | 40,294,000,000 | unchanged |
| MSFT | Net debt | 19,359,000,000 | 19,359,000,000 | unchanged |
| NVDA | OCF TTM | 134,360,000,000 | 134,360,000,000 | unchanged |
| NVDA | CapEx TTM | 7,354,000,000 | 7,354,000,000 | unchanged |
| NVDA | FCF TTM | 127,006,000,000 | 127,006,000,000 | unchanged |
| NVDA | Operating income TTM | 197,579,000,000 | 197,579,000,000 | unchanged |
| NVDA | Interest TTM | missing (`ttm_window_not_aligned`) | missing (same) | unchanged |
| NVDA | D&A TTM | 3,687,000,000 | 3,687,000,000 | unchanged |
| NVDA | EBITDA TTM | 201,266,000,000 | 201,266,000,000 | unchanged |
| NVDA | Cash | 22,443,000,000 (2026-07-26) | same | unchanged |
| NVDA | Short-term debt | 1,000,000,000 | 1,000,000,000 | unchanged |
| NVDA | Long-term debt | 32,366,000,000 | 32,366,000,000 | unchanged |
| NVDA | Total debt | 33,366,000,000 | 33,366,000,000 | unchanged |
| NVDA | Net debt | 10,923,000,000 | 10,923,000,000 | unchanged |

OCF quarter ends and values match v3 on all three issuers (HEI October FY; MSFT June FY; NVDA 52/53-week ends including 2026-07-26).

## New v4 fields

| Metric | HEI | MSFT | NVDA |
|---|---:|---:|---:|
| Revenue TTM | 5,176,756,000 `Revenues` | 331,839,000,000 `RevenueFromContractWithCustomerExcludingAssessedTax` | 302,969,000,000 `Revenues` |
| Matches Layer 1 `layer1.revenueTtm` | yes | yes | yes |
| Net income TTM | 847,724,000 `NetIncomeLoss` | 133,749,000,000 `NetIncomeLoss` | 192,879,000,000 `NetIncomeLoss` |
| Gross profit TTM | **2,091,317,000 derived** (Revenue − `CostOfRevenue`; tagged `GrossProfit` last 2020-10-31) | 225,465,000,000 extracted | 226,241,000,000 extracted |
| Cost of revenue TTM | 3,085,439,000 `CostOfRevenue` extracted | 106,374,000,000 `CostOfGoodsAndServicesSold` | 76,728,000,000 `CostOfRevenue` |
| GP + COGS = Revenue | exact (derived GP) | exact | exact |
| Gross margin | **40.40%** derived | 67.94% | 74.67% |
| Operating margin | 24.04% | 46.78% | 65.21% |
| Net margin | 16.38% | 40.31% | 63.66% |
| FCF margin | 19.90% | 20.19% | 41.92% |
| Cash conversion (OCF/NI) | 1.311 | 1.368 | 0.697 |
| AR | 736,335,000 | 80,876,000,000 | 63,059,000,000 |
| Inventory | 1,447,885,000 | 1,397,000,000 | 31,575,000,000 |
| AP | 297,102,000 | 42,416,000,000 | 15,059,000,000 |
| Current assets | 2,725,491,000 | 207,710,000,000 | 197,412,000,000 |
| Current liabilities | 1,003,079,000 | 168,825,000,000 | 43,019,000,000 |
| Current ratio | 2.72 | 1.23 | 4.59 |
| OWC | 1,887,118,000 | 39,857,000,000 | 79,575,000,000 |
| DSO (days) | 47.0 | 82.9 | 54.6 |
| DIO (days) | 163.1 | 4.0 | 110.4 |
| DPO (days) | 31.2 | 120.3 | 57.2 |
| CCC (days) | 179.0 | −33.4 | 107.8 |
| AR YoY | 23.2% | 15.7% | 126.8% |
| Inventory YoY | 10.5% | 48.9% | 111.0% |
| AP YoY | 28.8% | 53.0% | 66.1% |
| FCF / EBITDA quarter series | 8 derived quarters each | 8 | 8 |
| BS history slots with values | cash/AR/Inv/AP/CA/CL 8/8 | 8/8 | cash/AR/Inv/AP/CA/CL 8/8; ST debt 6/8 |

Stock concepts used: `AccountsReceivableNetCurrent`, `InventoryNet`, `AccountsPayableCurrent`, `AssetsCurrent`, `LiabilitiesCurrent`.

## Alignment and provenance

- HEI spine is the October fiscal year (`dataAsOf` 2026-07-31). Cash history uses the same eight month-end dates.
- MSFT spine is the June fiscal year (`dataAsOf` 2026-06-30).
- NVDA spine is the 52/53-week calendar (`dataAsOf` 2026-07-26). Cash and AR history ends are 2026-07-26, 2026-04-26, 2026-01-25, 2025-10-26, 2025-07-27, 2025-04-27, 2025-01-26, 2024-10-27. DSO used begin 2025-07-27 / close 2026-07-26 (364-day window). The ±10-day matcher is what allows those slots to pair.
- Every extracted flow/stock is `verification: company_facts_only`. FCF and EBITDA TTM keep `verification: derived`. Margins / WC ratios are `not_checked`. `statement_verified` does not appear.
- `calculationMethod` is `extracted` on tagged series and `derived` on FCF, EBITDA, HEI GP, margins, and WC.
- HEI FCF quarters equal OCF − CapEx on all eight slots.
- Sidecar issuer files are ~88 KB each (v3 was ~21 KB).

## Missing-value behavior

- No missing or not-applicable metric was written as `0`.
- MSFT / NVDA interest remains `missing` / `ttm_window_not_aligned` (newest facts 2024-06-30 and 2024-04-28). Same as v3.
- NVDA short-term debt history: 2025-07-27 and 2025-04-27 are `null`; 2025-01-26 and 2024-10-27 are reported `0` (extracted, not imputed).
- HEI tagged `GrossProfit` remains unaligned (`newestEnd` 2020-10-31). The current GP metric is **derived**, not that stale series.

## Data-quality concerns

1. **HEI Gross Profit is derived, not a current XBRL tag.** Safe because Revenue and COGS share the current October-FY spine and foot (`2,091,317,000 + 3,085,439,000 = 5,176,756,000`). Labeled `calculationMethod=derived`, `derivedFrom=revenue_minus_cost_of_revenue`, `verification=not_checked`. The FY2020 `GrossProfit` tag is unused for current TTM. Two aligned-but-conflicting tags are still both kept.
2. **MSFT and NVDA interest** are still unusable for TTM (Company Facts lag). Unchanged from v3.
3. **MSFT inventory is present** (`InventoryNet` 1.40B). DIO is 4.0 days, not `not_applicable`. Software SIC does not force inventory N/A when the tag exists.
4. **All new income-statement and WC figures are Company Facts only.** They are not face-checked against rendered 10-Q/10-K statements. Layer 1 remains the statement-verified revenue TTM; it happens to equal Layer 3 revenue TTM on these three issuers.

## Not done

- No production issuer file was replaced.
- Full-universe v4 rebuild exists only under `/tmp/layer3-full-v4/staging` — see `docs/validation/layer3-full-staging.md`. It was not published.
- `refresh.yml` was not enabled.
- PR #19 was not merged.
