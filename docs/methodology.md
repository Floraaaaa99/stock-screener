# Methodology

This document describes how the pipeline turns raw source data into the figures on the site. The code lives under
`pipeline/src/screener_pipeline/`, and the tests in `pipeline/tests/` cover each rule below.

## 1. Universe (NASDAQ Trader)

NASDAQ Trader's `nasdaqlisted.txt` and `otherlisted.txt` define the universe.

- **Exchanges:** NASDAQ (all tiers), NYSE (`N`) and NYSE American (`A`) only. NYSE Arca, Cboe, IEX and other venues are excluded as `exchange_out_of_scope`.
- **Excluded:**
  - ETFs and test issues, using the files' own flags.
  - Warrants, rights, units, preferred and depositary preferred shares, notes and other debt, ETNs, closed-end and other funds, trust certificates and structured products, and when-issued lines. These are identified from the security name and from the ACT symbol suffix (`$`, `.U`, `.W`, `.WS`, `.R`, `#`).
- **Included:** common stocks and ADRs. ADRs are tagged `ADR` on the site.
- **Duplicates:** NASDAQ Trader is authoritative. A symbol listed twice keeps its first listing, and the other is recorded as `duplicate`. Symbols are normalised to Yahoo/SEC form (`BRK.B` and `BRK/B` become `BRK-B`). Matching a symbol to a SEC CIK also tries its variants, which handles share-class suffixes.
- **Yahoo does not decide inclusion.** A listing is never dropped because Yahoo returns no data or an unexpected `quoteType`. Such cases go to `classification_issues.json` instead.

Every exclusion is recorded with its reason. `meta.json` reports the counts.

## 2. Market data (Yahoo Finance)

yfinance `Ticker.info` provides sector, industry, market cap, price and currency.

- Requests are throttled (about 1 per second plus jitter) and retried with exponential backoff on HTTP 429 and 5xx responses. A run stops early after repeated consecutive failures instead of hammering the service.
- Fields are cached per ticker with their own timestamps. Sector and industry are refreshed every 30 days; market cap and price are treated as fresh for 20 hours. Progress is checkpointed, so an interrupted run resumes where it stopped.
- A batched `yf.download` path exists for prices but is **not used in production** unless a comparison run shows it matches Yahoo `marketCap` (see `screener yahoo-batch-test`).
- Yahoo's terms forbid redistributing these fields as a public full-universe dataset. See [`yahoo-terms.md`](yahoo-terms.md). The site shows when market data was fetched. Missing values are N/A.

## 3. Quarterly revenue (SEC EDGAR Company Facts)

### 3.1 Candidate concepts

Company Facts are loaded from SEC's nightly `companyfacts.zip` for the full universe (one download, then only the needed CIKs and revenue concepts are kept). The per-CIK API is the fallback when a CIK is missing from the zip.

The pipeline considers these `us-gaap` concepts in USD (or the filer's reporting currency): `Revenues`,
`RevenueFromContractWithCustomerExcludingAssessedTax`, `RevenueFromContractWithCustomerIncludingAssessedTax`,
`SalesRevenueNet` and `RevenuesNetOfInterestExpense`. Only facts from 10-Q and 10-K filings, and their amendments, are used.

### 3.2 Standalone quarters

For each concept:

1. **De-duplication and restatements.** Facts for the same (start, end) period are merged. The most recently filed value wins, and the quarter is marked *Restated* if it changed. The cited filing is the earliest one that reported the final value. If a later filing only rounds the same number more coarsely (for example a 10-K in millions repeating a 10-Q in thousands), that is not a restatement, and the more precise value is kept.
2. **Reported quarters** are facts covering 80–100 days.
3. **Derived quarters** are computed from year-to-date facts when no 3-month fact exists:
   - Q2 = 6M YTD − Q1, and Q3 = 9M YTD − 6M YTD.
   - **Q4 = FY − 9M YTD**. If there is no nine-month fact, Q4 = FY − (Q1 + Q2 + Q3).
   - An earlier quarter can be derived from a later one when its own filing is missing from Company Facts, for example Q1 = 6M YTD − Q2.
   - Each derived quarter keeps its formula and source facts, shown under "How obtained" on the site.
   - When a reported quarter disagrees with the value implied by YTD figures, the company is flagged `derivation_mismatch`.
4. **Fiscal labels.** Company Facts tags each fact with the fiscal year and period of the filing that contains it, so comparative columns are mislabelled. The pipeline therefore labels each quarter from the filing in which it is the *current* period. This handles fiscal years that do not end in December and 52/53-week years. Labels inferred from neighbouring quarters are marked with `*`.
5. **Timeline.** The latest 12 quarters are placed in consecutive slots, with ±7 days tolerance for 52/53-week calendars. A slot with no derivable value stays empty (N/A). Annual revenue is **never** substituted for a missing quarter.

Values agree when they differ by at most max($1,000, 0.1%). This absorbs rounding to thousands but not real differences.

### 3.3 Choosing a consistent concept

The concept is **never** chosen because its values are larger. The rules, in order:

1. **Override.** If `pipeline/config/concept_overrides.json` names a concept for the CIK, that concept is used. Each entry must cite the filing it was validated against.
2. **Equivalent concepts.** If all candidates with quarters in the 12-quarter window report the same values where they overlap, they are equivalent. The best-covered current concept is used. Gaps may be filled from an equivalent concept only when at least one overlapping quarter confirms that the two agree. Otherwise the older figures are not used (`concept_change_unverified`).
3. **Income-statement evidence.** If the candidates disagree, the pipeline opens the latest filing's rendered income statement on EDGAR (`FilingSummary.xml` → `R*.htm`). It uses the candidate that appears there as the total-revenue line.
4. **Ambiguous.** If nothing resolves the disagreement, the company is flagged `ambiguous_concept` and no TTM figures are produced.

### 3.4 Verification against filings

Every quarter on the site is checked against the income statement of the filing it comes from, using EDGAR's rendered
statement pages, which are independent of the Company Facts API:

- A reported quarter is compared with the statement's 3-month column.
- A derived quarter is recomputed from its sources' statement columns, for example the 10-K annual column minus the 10-Q nine-month column.

Results appear as *Matches filing*, *Differs from filing* or *Not verifiable*, with a link to the statement. A mismatch
in any of the 8 TTM quarters blocks the growth figure (`filing_mismatch`).

### 3.5 Foreign private issuers

Companies that file 20-F and 6-K reports have no quarterly 10-Q data in Company Facts. Their revenue columns show N/A
with the reason `foreign_filer`. Annual figures are not divided or substituted.

## 4. TTM and growth

- **Current TTM** is the sum of slots 1–4, the latest 4 quarters. **Previous TTM** is the sum of slots 5–8.
- **Growth** = (Current TTM ÷ Previous TTM − 1) × 100.
- Growth is computed only when all 8 slots have values, the quarters are consecutive, they come from one verified comparable concept, none of them disagrees with its filing, and Previous TTM is greater than zero.
- Otherwise the value is N/A, with one of these reasons: `insufficient_quarters`, `gap_in_quarters`, `previous_ttm_not_positive`, `ambiguous_concept`, `filing_mismatch`, `statement_mismatch`, `foreign_filer`, `no_cik`, `no_revenue_concept`.
- Yahoo's `revenueGrowth` is never used.

Additional flags are shown in the expanded row:

- `negative_value`: a quarter is negative, for example a revenue reversal. It is still included.
- `annual_sum_mismatch`: four reported quarters do not add up to the annual figure.
- `stale_filings`: the latest quarter ended more than 270 days ago.
- `other_concept_disagrees`: another revenue concept reports different values.

## 5. Output

`web/public/data/` contains:

- `meta.json`: build timestamps, source file dates, universe and exclusion counts, coverage statistics and N/A reason counts.
- `screener.json`: one compact row per listing, used by the table.
- `companies/<TICKER>.json`: per-company detail, loaded when a row is expanded. It contains all 12 quarters with periods, filings, formulas, verification results, flags and the concepts considered.
- `classification_issues.json`: Yahoo classification problems for listings that are still included.

Files are written atomically: the whole dataset directory is built next to the old one and then swapped in. A failed
run therefore never leaves a half-written dataset.
