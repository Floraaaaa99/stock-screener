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
- **Duplicates:** NASDAQ Trader is authoritative. A symbol listed twice keeps its first listing, and the other is recorded as `duplicate`. Symbols are normalised to SEC form (`BRK.B` and `BRK/B` become `BRK-B`). Matching a symbol to a SEC CIK also tries its variants, which handles share-class suffixes.
- **Missing SEC data does not drop a listing.** A company without a CIK, SIC code, or quarterly revenue stays in the table with N/A and a reason. Missing cases go to `classification_issues.json` when they are a CIK or SIC gap.

Every exclusion is recorded with its reason. `meta.json` reports the counts. Coverage is split into **full-universe coverage** (how many eligible listings are present, CIK-matched, SIC-assigned) and **TTM coverage** (how many have current TTM and growth).

## 2. Industry (SEC SIC)

Industry comes from each company's EDGAR submissions JSON (`sic` and `sicDescription`), labeled **SEC SIC** on the site. The two-digit prefix is mapped to the U.S. SIC manual major-group title for the filter roll-up.

- Bulk source: nightly `https://www.sec.gov/Archives/edgar/daily-index/bulkdata/submissions.zip`. The per-CIK submissions API is the fallback.
- Compact SIC records are stored in pipeline state (`sic/*.json`) and packed into the `pipeline-state` release.
- Filters are **SEC SIC major group** and **SEC SIC industry** (`description — code`, sorted by name). They are not Yahoo or commercial sector/industry names.
- Stock price and market cap are not collected.

## 3. Quarterly revenue (SEC EDGAR filings)

Official 10-Q and 10-K income statements are the source of truth. Company Facts (nightly
`companyfacts.zip` or the per-CIK API) is an index of those filings, not a newer data source.
If EDGAR submissions already list a 10-Q or 10-K whose period end is after the latest Company
Facts quarter, the pipeline opens that filing's rendered income statement and uses the officially
reported revenue. Cached Company Facts are never treated as "latest" when a newer filing is on
EDGAR. Third-party estimates are not used.

`screener freshness --data-dir …` compares a built dataset with EDGAR submissions. Publication
(`--write-live` / `screener gate --publish`) fails when a newer official filing was found but its
standalone-quarter revenue could not be read (`unresolved_edgar_lag`).

### 3.1 Candidate concepts

Company Facts are loaded from SEC's nightly `companyfacts.zip` for the full universe (one download, then only the needed CIKs and revenue concepts are kept). The per-CIK API is the fallback when a CIK is missing from the zip. A newer EDGAR 10-Q/10-K is then merged from the filing itself when Facts lag.

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
statement pages. A quarter taken from a filing that Company Facts had not yet indexed is checked the same way and
keeps that filing's SEC link:

- A reported quarter is compared with the statement's 3-month column.
- A derived quarter is recomputed from its sources' statement columns, for example the 10-K annual column minus the 10-Q nine-month column.

Results appear as *Matches filing*, *Differs from filing* or *Not verifiable*, with a link to the statement. A mismatch
or unverifiable result in **any** of the 8 TTM-window quarters excludes that company’s Current TTM, Previous TTM, and
growth (`filing_mismatch` or `unverified_quarters`). Those quarters never enter Layer 2 Passed/Watchlist eligibility.
The company stays in the table with N/A and the reason. The 10% quarter-mismatch gate is a **dataset publish brake**
only: if more than 10% of checked quarters in the file are mismatches, the dataset may not replace live Pages. It does
not allow mismatched or unverified numbers into TTM.

### 3.5 Foreign private issuers

Companies that file 20-F and 6-K reports have no quarterly 10-Q data in Company Facts. Their revenue columns show N/A
with the reason `foreign_filer`. Annual figures are not divided or substituted.

## 4. TTM and growth

- **Current TTM** is the sum of slots 1–4, the latest 4 quarters. **Previous TTM** is the sum of slots 5–8.
- **Growth** = (Current TTM ÷ Previous TTM − 1) × 100.
- Growth is computed only when all 8 slots have values, the quarters are consecutive, they come from one verified comparable concept, every TTM-window quarter matches its filing, and Previous TTM is greater than zero.
- A mismatched or unverified TTM-window quarter blocks Current TTM, Previous TTM, and growth together. The company remains listed with N/A.
- Otherwise the value is N/A, with one of these reasons: `insufficient_quarters`, `gap_in_quarters`, `previous_ttm_not_positive`, `ambiguous_concept`, `filing_mismatch`, `unverified_quarters`, `statement_mismatch`, `foreign_filer`, `no_cik`, `no_company_facts`, `no_revenue_concept`.
- Revenue amounts keep the SEC reporting currency (always labeled, including USD). The site does not convert currencies. Sorting Current or Previous TTM groups by currency (USD first) so amounts in different currencies are never ranked as one series. Growth is a ratio and may be sorted across currencies.
- Default table sort is TTM growth descending, with N/A last. Current and Previous TTM columns are also sortable.

Additional flags are shown in the expanded row:

- `negative_value`: a quarter is negative, for example a revenue reversal. It is still included.
- `annual_sum_mismatch`: four reported quarters do not add up to the annual figure.
- `stale_filings`: the latest quarter ended more than 270 days ago.
- `other_concept_disagrees`: another revenue concept reports different values.

## 5. Sequential growth (Layer 2)

Layer 2 does not fetch or reinterpret revenue. It reads Layer 1’s latest eight consecutive, comparable, filing-validated
quarters and preserves currency, revenue concept, schema version, and quarter-level validation. Dependent YoY/QoQ rates
are recomputed whenever that window changes (new filings or restatements).

Classification rules are versioned (`rulesVersion`, currently 3). Decisions use unrounded values.

- **Eligibility.** Start from Layer 1 companies with TTM revenue growth **> 0%** computed only from filing-matched
  quarters. Valid TTM growth **≤ 0%** is a separate bucket (`ttm_nonpositive`) and is never labeled Data Review.
  TTM N/A because a TTM-window quarter is mismatched or unverified is Data Review, not Passed or Watchlist.
- **Quarterly YoY** for the latest four quarters, oldest to newest:
  `(current quarter ÷ same fiscal quarter last year − 1) × 100`.
  - **Passed:** all four YoY rates are strictly > 0% (deceleration is allowed; accelerating growth is not required).
  - **Watchlist:** all required data is valid, but at least one YoY is ≤ 0%.
  - **Data Review:** a required quarter is missing, unverified, incomparable, or a prior-year denominator is ≤ 0%.
- **Quarterly QoQ** is calculated for display on the same four quarters:
  `(current ÷ immediately preceding quarter − 1) × 100`. Missing inputs or denominators ≤ 0 are N/A with a reason, never
  zero. QoQ never excludes a YoY-passing company.
- **Verified historical vs latest available.** Layer 2 always uses Layer 1’s filing-validated consecutive window.
  That window is **verified historical data**, not a live EDGAR listing of the newest 10-Q. If the dataset as-of date
  (`meta.generatedAt`) is after the next fiscal quarter’s typical filing deadline — 45 days after quarter-end for a
  10-Q (the slower of the 40/45-day SEC windows) or 75 days for a 10-K (the slower of the 60/75-day windows) — the
  company is marked `verified_lagging` and the UI shows a freshness warning. Company Facts can lag EDGAR submissions:
  a 10-Q may already be on file while the XBRL snapshot used for revenue still ends at the previous quarter.
- **QoQ category badges** (multiple allowed; they do not affect YoY eligibility). Objective rules run immediately:
  four consecutive quarters of positive QoQ (no spread/jump threshold), accelerating sequential growth, QoQ volatility,
  latest-quarter revenue decline, other/flat, unable to classify.
  Threshold-dependent rules — stable sequential growth (max − min ≤ configured spread) and recent QoQ jump
  (latest − max of preceding three ≥ configured jump) — stay inactive until
  `pipeline/config/layer2.json` (or the on-site inputs) set those values. Until then the UI shows
  **Threshold not configured**. Other / flat is assigned only when all four QoQ rates are present **and** every rule
  that could apply has been evaluated — it is not used while a threshold is unconfigured, and not used when QoQ data
  is incomplete (`unable_to_classify` covers that). An unavailable earlier QoQ does not block identifying a
  latest-quarter decline.
- There is no top-N limit and no valuation screen.

## 6. Output

`web/public/data/` contains:

- `meta.json`: build timestamps, source file dates, universe and exclusion counts, coverage statistics and N/A reason counts.
- `screener.json`: one compact row per listing, used by the table.
- `layer2.json`: sequential-growth rows and bucket counts derived from Layer 1 company JSON.
- `companies/<TICKER>.json`: per-company detail, loaded when a row is expanded. It contains all 12 quarters with periods, filings, formulas, verification results, flags and the concepts considered.
- `classification_issues.json`: missing CIK or missing SEC SIC for listings that are still included.

Files are written atomically: the whole dataset directory is built next to the old one and then swapped in. A failed
run therefore never leaves a half-written dataset.
