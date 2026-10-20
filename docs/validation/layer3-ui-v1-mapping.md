# Layer 3 UI v1 — architecture and metric mapping

Implemented on Draft PR #20 against the deployed Layer 3 v4 issuer JSON (schema 3 / extraction 4) on `main`.

Do not change Layer 1, Layer 2, the extraction pipeline, published issuer JSON, Add/Remove membership, issuer identity, or `refresh.yml`. Do not merge or deploy without approval.

## 1. What exists today

The Layer 3 page is a saved-company table (`Layer3View`) with an in-row expand (`Layer3Detail`). That detail shows Phase 2 cash-flow TTM/quarters and the latest balance-sheet snapshot. It does not render:

- a dedicated research page or sticky section navigation
- Growth Quality / Financial Health / Working Capital
- 8-quarter charts
- Gross Profit, margins, working-capital ratios, or quality-flag panels

Routing is `?layer=3` only. Issuer files are already lazy-loaded per CIK (`loadLayer3Issuer` → `data/layer3/cik/{cik}.json`) and cached. The browser never downloads the 5,543-file universe.

There is no chart library. The only chart is the Layer 2 `QoqChart` sparkline (inline SVG). Formatters already treat `null` as `N/A` (`formatCompactMoney`, `formatMillions`, `formatPercent`). Missing amounts must stay `null`; they are never shown as zero.

## 2. Page architecture

Keep the existing research list. Clicking a saved company opens a financial research detail view for that issuer.

### Routing

| URL | View |
|---|---|
| `?layer=3` | Existing Layer 3 list |
| `?layer=3&cik=0000046619` | Research page for that canonical CIK |

Section anchors (in-page, not separate routes): `#growth`, `#health`, `#working-capital`.

Layer 1 / Layer 2 search strings stay unchanged. The Layer 3 writer today always emits `?layer=3`; it will keep the `cik` param only while a research page is open.

Deep links to a CIK that is not on the saved list: load failure / “not on your Layer 3 list” + back. Do not silently add the issuer. ZSTK saved as `cik:0000000000` is already rewritten to `cik:0001790169` on membership load; the research URL uses the canonical CIK.

### List behavior

- Keep the current table, Add/Remove confirmation, and lazy fetch of saved CIKs.
- Row click opens the research page instead of expanding `Layer3Detail` in place.
- Remove on the list keeps the existing two-step confirm.

### Research page layout

```
Layer3ResearchPage
  Layer3ResearchHeader
  Layer3Overview            (4 metric cards)
  Layer3SectionNav          (sticky: Growth Quality / Financial Health / Working Capital)
  section#growth            G1, G2, G3
  section#health            F1, F2, F3
  section#working-capital   W1, W2, W3
```

Header contents, all from the issuer JSON / membership entry:

| UI | JSON / source |
|---|---|
| Back to Layer 3 list | clears `cik` |
| Ticker + name | `displayTicker`, `name` (also `tickers` for share-class note) |
| Industry / SIC | `sicIndustry`, `sicCode` |
| Latest reporting date | `dataAsOf` (issuer-level). Per-metric `end` on stocks. |
| Data source + extraction status | `extractionStatus`, `verificationStatus`, `modelApplicability`, `inputCompleteness`, `schemaVersion`, `extractionVersion` |
| Remove from Layer 3 | existing `removeIssuer` + confirm |

States the page must handle without inventing numbers:

| State | Behavior |
|---|---|
| Loading | spinner; do not render zeros |
| Fetch / 404 | error + back |
| `insufficient_facts` (JHI) | three sections render; every metric N/A + reason |
| `pending_analysis` | same; no fabricated series |
| `modelApplicability: not_applicable` (JPM, ZSTK) | banner “corporate FCF / net-debt model not applicable”; still show extracted metrics |
| Issuer `flags` includes `concept_scope_mismatch` | banner; derived GP/COGS ratios stay suppressed |
| `financial_institution` | same banner as model not applicable |

### Proposed files (after approval)

```
web/src/components/layer3/
  Layer3ResearchPage.tsx
  Layer3ResearchHeader.tsx
  Layer3Overview.tsx
  Layer3SectionNav.tsx
  Layer3GrowthQuality.tsx      # G1–G3
  Layer3FinancialHealth.tsx    # F1–F3
  Layer3WorkingCapital.tsx     # W1–W3
  MetricCard.tsx
  MetricProvenance.tsx         # popover / expandable
  SeriesChart.tsx              # bar / line; gaps stay gaps
  SeriesTable.tsx              # expandable exact values
  QualityStatus.tsx            # missing / N/A / derived / flags
web/src/lib/layer3Research.ts  # presentation pairing + display helpers
web/src/lib/layer3Research.test.ts
```

`Layer3View.tsx` gains navigation only. `Layer3Detail.tsx` is retired from the list (not deleted until the research page replaces it). `web/src/lib/layer3.ts` membership / identity helpers stay as-is.

Charts: reusable SVG primitives in the existing visual language. No new runtime dependency unless a later review finds SVG insufficient. Do not import a scoring or dashboard kit.

Progressive disclosure: the first screen shows the header, four overview cards, and one default chart per subsection. Alternate views (YoY %, QoQ %, margins) and numerical tables are toggles / `<details>`.

## 3. Metric kinds in v4

| Kind | Shape | TTM? | History |
|---|---|---|---|
| Flow | `Layer3FlowMetric` | `ttm`, `previousTtm`, `ttmYoy` | `quarters[]` up to 8 standalone |
| Stock | `Layer3StockMetric` | never | `value` + `end` + `history[]` up to 8 |
| Derived with quarters | `Layer3DerivedMetric` | `ttm`, `previousTtm`, `ttmYoy` | `quarters[]` up to 8 |
| Derived snapshot | `Layer3DerivedMetric` | no TTM | latest `value` (+ `end` when it is a stock ratio) |

`Layer3Quarter` has `value`, fiscal labels, dates, concept, filing provenance, `method` / `calculationMethod`, `verification`. It does **not** have `yoy` or `qoq` keys.

Units that the UI must not mix:

| Field | Unit in JSON | Display |
|---|---|---|
| Flow / stock amounts | currency (`USD`, …) | compact on cards; exact in tables |
| `ttmYoy`, `arYoy`, `inventoryYoy`, `apYoy` | **percent** (20.69 = +20.7%) | `formatPercent` |
| `grossMargin`, `operatingMargin`, `netMargin`, `fcfMargin`, `cashConversion` | **ratio** (0.40 = 40.0%) | × 100, then percent |
| `dso`, `dio`, `dpo`, `cashConversionCycle` | days | one decimal + “days” |
| `currentRatio` | ratio | two decimals, not a percent |

`calculationMethod: extracted` = reported Company Facts (or YTD→Q derivation already stored as quarter `method: reported|derived`). `calculationMethod: derived` = pipeline formula (GP fallback, FCF, margins, WC). Never label either as `statement_verified`. Company Facts verification is `company_facts_only` or `not_checked`.

## 4. Field map

Paths are under the issuer JSON root. `metrics.*` is null when the file has no extracted block.

### Header / overview

| UI | JSON | Notes |
|---|---|---|
| Revenue TTM | `metrics.revenue.ttm` | fiscal window = first four `quarters[]` ends; quality = `status` / `reason` / `verification` / `calculationMethod` |
| Gross Margin TTM | `metrics.grossMargin.ttm` | derived; suppressed when `qualityFlags` contains `incompatible_inputs` |
| OCF TTM | `metrics.ocf.ttm` | |
| FCF TTM | `metrics.fcf.ttm` | derived; formula `OCF − CapEx (CapEx as positive cash outflow)` |
| Overview period | each metric’s latest quarter `end` or stock `end`; issuer `dataAsOf` in the header | |
| Overview quality | metric `status`, `reason`, `calculationMethod`, `identity`, `qualityFlags` | missing → N/A, not 0 |

HEI check: Revenue TTM 5,176,756,000; Gross Margin TTM 0.40398 (derived); OCF 1,111,232,000; FCF 1,030,280,000 (derived). GP itself is derived (`Revenue − Cost of Revenue`).

### G1 — Revenue Trend

| UI | JSON | Supported? |
|---|---|---|
| Revenue amount 8Q | `metrics.revenue.quarters[].value` + `end` / FY / FQ | yes |
| Current / prior TTM | `metrics.revenue.ttm`, `previousTtm` | yes |
| TTM YoY | `metrics.revenue.ttmYoy` / `ttmYoyReason` | yes (null when prior ≤ 0) |
| Quarterly YoY % | **not a v4 field** | presentation pairing only (below) |
| Quarterly QoQ % | **not a v4 field** | presentation pairing only (below) |

Default chart: 8Q revenue bars. YoY % and QoQ % are view toggles. Expandable table shows exact `value` (unrounded), dates, concept, filing URL.

### G2 — Profitability

| UI | JSON | View |
|---|---|---|
| Revenue | `metrics.revenue` | Amount |
| Gross Profit | `metrics.grossProfit` | Amount (HEI: derived) |
| Operating Income | `metrics.operatingIncome` | Amount |
| Net Income | `metrics.netIncome` | Amount |
| Gross Margin | `metrics.grossMargin` | Margin (ratio) |
| Operating Margin | `metrics.operatingMargin` | Margin |
| Net Margin | `metrics.netMargin` | Margin |

All seven have 8Q + TTM + prior TTM + TTM YoY when extracted. Amount and Margin are separate views (do not mix dollars and percents on one axis). Default: Amount (Revenue / GP / OpInc / NI). Margin view is a toggle. GP/COGS `identity: concept_scope_mismatch` (VSXY): raw series still charted; `grossMargin.status=missing` with `unreliableTtm` — show quality status, not the unreliable number as a clean margin.

### G3 — Growth Efficiency

| UI | JSON | Supported? |
|---|---|---|
| Revenue YoY | `metrics.revenue.ttmYoy` | TTM yes |
| Operating Income YoY | `metrics.operatingIncome.ttmYoy` | TTM yes |
| Net Income YoY | `metrics.netIncome.ttmYoy` | TTM yes |
| Dollar change when % is not meaningful | `ttm − previousTtm` when `ttmYoy` is null and both TTM values exist | presentation only |
| Quarterly YoY of the three series | not stored | optional pairing, same rules as G1 |

ZSTK: OI / NI `ttmYoy` is null (`previous_ttm_not_positive`); show dollar change, not a fabricated rate. Do not classify growth as good / bad / accelerating.

### F1 — Earnings vs Cash

| UI | JSON | Supported? |
|---|---|---|
| Net Income 8Q + TTM | `metrics.netIncome` | yes |
| OCF 8Q + TTM | `metrics.ocf` | yes |
| Cash Conversion 8Q + TTM | `metrics.cashConversion` (`OCF / Net Income`, ratio) | yes when NI TTM > 0 |
| Align periods | pair on matching `quarters[].end` | already how the pipeline built conversion |

ZSTK cash conversion is `missing` / `denominator_not_positive` (negative NI). Show that status; do not invert the ratio.

### F2 — Cash Flow & Reinvestment

| UI | JSON | Notes |
|---|---|---|
| OCF | `metrics.ocf` | extracted |
| CapEx | `metrics.capex` | stored as a **positive outflow** |
| FCF | `metrics.fcf` | derived: OCF − \|CapEx\| |
| FCF Margin | `metrics.fcfMargin` | ratio; TTM + 8Q |

Explain the pipeline definition in the section copy. Chart OCF / CapEx / FCF together with that sign convention (CapEx down or as a positive spend series, labeled). Quarterly + TTM supported.

### F3 — Liquidity & Debt

| UI | JSON | TTM? |
|---|---|---|
| Cash | `metrics.cash` | never |
| Short-term Debt | `metrics.shortTermDebt` | never |
| Long-term Debt | `metrics.longTermDebt` | never |
| Total Debt | `metrics.totalDebt` (derived: ST + LT) | never |
| Net Debt | `metrics.netDebt` (derived: total − cash) | never |
| Current Assets | `metrics.currentAssets` | never |
| Current Liabilities | `metrics.currentLiabilities` | never |
| Current Ratio | `metrics.currentRatio` | **latest snapshot only** — no history array |

Always show the balance-sheet `end` date. History charts use `history[]` (up to 8). Never sum stocks into a TTM. Current ratio has no 8Q series in v4 — show the latest card + provenance; do **not** compute a history from CA/CL in the browser.

### W1 — Receivables and Revenue

| UI | JSON | Series? |
|---|---|---|
| Revenue trend | `metrics.revenue.quarters` | 8Q flow |
| AR trend | `metrics.accountsReceivable.history` | 8 snapshots |
| AR YoY | `metrics.arYoy.value` (percent) | **latest only** |
| DSO | `metrics.dso.value` (days) | **latest only** |

Do not overlay AR dollars on revenue dollars as if they were the same kind of number. Default: two charts (revenue flow, AR stock) plus DSO / AR YoY cards. DSO formula already on the metric: `Average AR / TTM Revenue × days_in_window`.

### W2 — Inventory and COGS

| UI | JSON | Series? |
|---|---|---|
| Inventory | `metrics.inventory` | 8 snapshots when extracted |
| COGS | `metrics.costOfRevenue` | 8Q + TTM |
| Inventory YoY | `metrics.inventoryYoy.value` | latest only |
| DIO | `metrics.dio.value` | latest only |

`inventory.status === "not_applicable"` (JPM, JHI, AIFA, …) → explicit Not Applicable. Missing inventory stays N/A, never 0. If `dio` is suppressed (`incompatible_inputs`), show that flag, not a clean DIO.

### W3 — Payables and Cash Conversion Cycle

| UI | JSON | Series? |
|---|---|---|
| AP | `metrics.accountsPayable` | 8 snapshots |
| DPO | `metrics.dpo.value` | latest only |
| DSO | `metrics.dso.value` | latest only |
| DIO | `metrics.dio.value` | latest only |
| CCC | `metrics.cashConversionCycle.value` | latest only; formula `DSO + DIO − DPO` |
| OWC | `metrics.operatingWorkingCapital.value` | latest only; `AR + Inventory − AP`, or `AR − AP` when inventory is N/A |

CCC / DIO / DPO are suppressed when GP/COGS/Revenue scopes conflict. OWC is not TTM’d and has no history array — do not synthesize one.

### Present but out of this spec

`metrics.interestExpense`, `depreciationAmortization`, `ebitda`, `noInterestBurden`, `growthSource`, Layer 1 copied revenue. Leave them off the research page (list table may still show the Phase 2 columns). No valuation, price, score, or AI fields exist to display.

## 5. Presentation pairing (quarterly YoY / QoQ)

v4 does not store quarterly growth rates. The spec still asks G1 (and optionally G3) to show them. Proposed rule — **UI pairing of already-extracted standalone quarters**, labeled as such, not written back to JSON and not added to the pipeline:

1. Use only quarters whose `value` is a finite number. A missing quarter is a gap, not a zero and not interpolated.
2. **YoY:** pair `fiscalYear` / `fiscalQuarter` with `fiscalYear − 1` / same `fiscalQuarter`. If the prior quarter is absent → Unavailable.
3. **QoQ:** pair consecutive standalone quarters in fiscal order (`Q1→Q2→Q3→Q4→next Q1`). If the previous standalone quarter is absent → Unavailable.
4. **Rate:** `(current / prior − 1) × 100` only when `prior > 0`.
5. **When `prior ≤ 0` or the rate is undefined:** show Unavailable for the percentage and, when both values exist, the dollar change `current − prior`.
6. Copy: “Paired from extracted standalone quarters. Not a published pipeline field.”

This matches the pipeline’s TTM YoY rule (`ttm_yoy`: prior ≤ 0 → no ratio) and Layer 2’s existing YoY/QoQ pairing style, without copying Layer 2 badges or classifications.

Not proposed as presentation math (would be new derived metrics):

- 8Q DSO / DIO / DPO / CCC / OWC / current-ratio histories
- quarterly AR YoY / inventory YoY / AP YoY series
- browser-side Gross Profit or FCF
- any clamp of extreme ratios

## 6. Provenance and quality display

Reusable `MetricProvenance` popover / expandable panel on every card and table row. Fields when present:

| Shown as | JSON |
|---|---|
| SEC concept | `concept` (metric or quarter) |
| Filing | `form`, `accn`, `filed`, `url` |
| Fiscal period | `fiscalYear`, `fiscalQuarter`, `start`, `end` |
| Calculation | `calculationMethod`, `formula`, quarter `method` |
| Verification | `verification`, `verificationNote` |
| Identity | `identity` (`gross_plus_cogs_equals_revenue`, `concept_scope_mismatch`, …) |
| Quality | `qualityFlags`, `qualityNote` |
| Missing | `status`, `reason` |
| Suppressed math | `unreliableTtm` / `unreliableValue` — labeled “suppressed; not shown as a clean ratio” |

Status vocabulary (neutral chips, not red/green ratings):

| Status | Meaning |
|---|---|
| Reported | `calculationMethod=extracted` and a value is present |
| Derived | `calculationMethod=derived` (or verification `derived`) |
| Missing | `status=missing` — N/A + reason |
| Not applicable | `status=not_applicable` (inventory / DIO / financial model) |
| Concept scope mismatch | issuer flag or metric `identity` / `incompatible_inputs` |
| Extreme ratio | `qualityFlags` contains `extreme_ratio` (value still shown) |
| Unreliable suppressed | derived ratio hidden; raw inputs remain |

Add the v4 reason codes that `explain.ts` does not yet know (`concept_scope_mismatch`, `incompatible_inputs`, `no_inventory_concept`, `insufficient_stock_history`, `denominator_not_positive`, `previous_ttm_not_positive`, `ttm_window_not_aligned`, …) as display strings only.

Extreme-ratio bands (inspect-only, already applied in JSON; UI does not re-threshold): DSO 0–400, DIO 0–500, DPO 0–400, CCC −400–700, current ratio 0–80.

## 7. Representative issuers

| Issuer | Why | What the UI must show |
|---|---|---|
| HEI `0000046619` | derived GP, manufacturing WC | GP/margin derived; 8Q + inventory; CCC extracted |
| MSFT `0000789019` | software, reported GP | GP identity `gross_plus_cogs_equals_revenue`; inventory still extracted (small) |
| NVDA `0001045810` | 52/53-week calendar | `dataAsOf` / cash `end` 2026-07-26, not a month-end |
| ZSTK `0001790169` | canonical CIK, negative CF, financial SIC | model not applicable; OCF TTM −5,601,000; cash conversion missing |
| JHI `0000759828` | insufficient facts | every metric N/A; inventory N/A |
| VSXY `0001856437` | concept-scope mismatch | GP/COGS shown; grossMargin/DIO/DPO/CCC missing + `incompatible_inputs` |
| JPM `0000019617` | financial sector | model not applicable; GP/COGS missing `no_concept`; inventory N/A |
| AIFA `0001708341` | inventory N/A, model applicable | W2 Not Applicable; OWC formula `AR − AP` if present |

## 8. Unsupported by v4 (do not invent)

1. Quarterly YoY / QoQ keys on `Layer3Quarter` — presentation pairing only, labeled.
2. 8-quarter DSO, DIO, DPO, CCC, OWC, current-ratio, AR/Inv/AP YoY series — latest snapshot only.
3. Statement-verified CF/BS/GP — verification stays `company_facts_only` / `not_checked`.
4. Scores, rankings, research notes, valuation, share price, multi-company comparison, AI.
5. New pipeline metrics or changes to published JSON.

## 9. Implementation notes

Shipped on this branch:

- Research route `?layer=3&cik=` with the saved list unchanged
- Overview cards + sticky Growth / Health / Working Capital nav
- One primary chart per subsection, alternate views, expandable exact-value tables, provenance `<details>`
- UI-only quarterly YoY/QoQ pairing (`web/src/lib/layer3Research.ts`)
- Latest-only DSO/DIO/DPO/CCC/OWC/current ratio/stock YoY cards
- Representative tests for HEI, MSFT, NVDA, ZSTK, JHI, VSXY, JPM

G2 amount view is split into Revenue & GP vs operating results so dollars of different scale do not share a misleading axis.

## 10. Implementation order (after approval)

1. Routing (`cik` query) + research page shell + header + empty-section states. List click navigates.
2. Shared `MetricCard`, `MetricProvenance`, `QualityStatus`, format helpers (ratio vs percent; null ≠ 0).
3. Overview cards.
4. `SeriesChart` / `SeriesTable` + G1 revenue.
5. G2 amount/margin, G3 TTM YoY + dollar-change fallback.
6. F1–F3.
7. W1–W3 including N/A and suppressed-ratio states.
8. Tests: pairing rules, null handling, HEI/MSFT/NVDA/ZSTK/JHI/VSXY/JPM fixtures (sliced JSON, not the universe). Typecheck, web tests, production build.
9. Screenshots of HEI, MSFT, NVDA research pages.

Small, reviewable commits. No merge or deploy without approval.
