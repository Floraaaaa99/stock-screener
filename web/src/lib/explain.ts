/** Human-readable explanations for the pipeline's reason codes and flags. */

export const NA_REASONS: Record<string, string> = {
  foreign_filer:
    "Foreign private issuer: files annual 20-F and 6-K reports, so SEC Company Facts has no quarterly 10-Q revenue.",
  no_cik: "No SEC company (CIK) matches this ticker.",
  no_company_facts: "SEC Company Facts data is not available for this company.",
  no_revenue_concept: "No total-revenue concept is reported in this company's 10-Q/10-K XBRL data.",
  no_earnings_concept: "No net-income concept is reported in this company's 10-Q/10-K XBRL data.",
  no_quarterly_revenue: "No quarterly revenue could be derived from the company's filings.",
  no_quarterly_earnings: "No quarterly net income could be derived from the company's filings.",
  ambiguous_concept:
    "Revenue concepts in the filings disagree and the income statement does not show which is total revenue.",
  gap_in_quarters: "A quarter is missing within the 8 quarters needed for the TTM comparison.",
  insufficient_quarters: "Fewer than 8 consecutive quarters of revenue history are available.",
  previous_ttm_not_positive: "Previous TTM is zero or negative, so growth is not meaningful.",
  statement_mismatch: "The latest revenue figure disagrees with the filing's income statement.",
  filing_mismatch: "A quarter used in the TTM disagrees with the income statement of its filing.",
  unverified_quarters:
    "A quarter in the TTM window could not be verified against its filing income statement, so TTM is N/A.",
  no_sic: "SEC submissions did not include an SIC code for this company.",
  nonpositive_denominator: "The prior-period amount is zero or negative, so a percentage change is not meaningful.",
  unverified: "A quarter used in this rate is not verified against its filing income statement.",
  unverified_mismatch: "A quarter used in this rate differs from its filing income statement.",
  missing_quarter: "A required quarter is missing from the Layer 1 eight-quarter window.",
  missing_quarter_current: "The current quarter is missing from the Layer 1 eight-quarter window.",
  missing_quarter_prior_year: "The same fiscal quarter last year is missing from the Layer 1 eight-quarter window.",
  incomparable_concept: "The two quarters use different accounting concepts, so they are not comparable.",
  insufficient_ni_window:
    "Need four verified standalone net-income quarters in the same window as revenue; missing quarters are N/A and are not replaced with older figures.",
  incomplete_yoy: "The four YoY rates cannot all be computed from validated, comparable quarters.",
  no_concept: "No matching US-GAAP concept is present in this issuer's 10-Q/10-K Company Facts.",
  missing_ocf: "Operating cash flow could not be derived, so free cash flow stays N/A.",
  missing_capex: "Capital expenditure could not be derived, so free cash flow stays N/A.",
  missing_operating_income: "Operating income is missing, so EBITDA is not calculated.",
  missing_depreciation_amortization: "Depreciation and amortization is missing, so EBITDA is not calculated.",
  depreciation_excludes_amortization:
    "Only a depreciation tag is aligned; amortization exists in Company Facts but not in the same TTM window, so EBITDA is left N/A rather than treating amortization as zero.",
  missing_short_term_debt: "Short-term debt is missing, so total and net debt stay N/A.",
  missing_long_term_debt: "Long-term debt is missing, so total and net debt stay N/A.",
  missing_cash: "Cash and cash equivalents are missing, so net debt stays N/A.",
  debt_period_mismatch: "Short-term debt component tags do not share the same balance-sheet date.",
  layer3_concepts_not_in_compact_facts:
    "Cash-flow and balance-sheet concepts are not stored in the compact revenue/earnings facts cache.",
  financial_institution_review_required:
    "This SIC industry is a financial institution; corporate FCF and net-debt definitions are not applied.",
  ttm_window_not_aligned:
    "This concept’s latest standalone quarter is not in the same fiscal window as operating cash flow, so its TTM is left N/A.",
  stock_not_as_of_latest_quarter:
    "No balance-sheet instant for this concept falls on the latest cash-flow quarter-end. Older amounts are not carried forward.",
  official_filing_unparsed:
    "A newer official 10-Q/10-K is on EDGAR, but its income statement could not be read, so this window is stale.",
  official_filing_no_applicable_revenue:
    "A newer official 10-Q/10-K was read and has no applicable total-revenue line. The verified window is older than that filing.",
  official_quarter_not_in_window:
    "Official revenue from a newer filing was read but is not yet in the verified eight-quarter TTM window.",
  concept_scope_mismatch:
    "Gross Profit, Cost of Revenue, and Revenue do not share a compatible concept scope, so derived ratios are not shown as clean values.",
  incompatible_inputs:
    "A derived ratio was suppressed because its inputs do not share a compatible concept scope. Raw series are unchanged.",
  previous_ttm_zero: "Previous TTM is zero, so a percentage change is not meaningful.",
  insufficient_ttm: "Current or previous TTM is missing, so TTM growth is not calculated.",
  missing_numerator: "The numerator for this ratio is missing.",
  missing_denominator: "The denominator for this ratio is missing.",
  denominator_zero: "The denominator is zero, so the ratio is not calculated.",
  denominator_not_positive: "The denominator is zero or negative, so the ratio is not meaningful.",
  no_inventory_concept: "No inventory concept is present in this issuer's Company Facts. That is not treated as zero.",
  insufficient_stock_history: "There are not enough aligned balance-sheet snapshots to compute this figure.",
  prior_balance_zero: "The year-ago balance is zero, so a percentage change is not meaningful.",
  prior_balance_not_positive: "The year-ago balance is negative, so a percentage change is not meaningful.",
  missing_accounts_receivable: "Accounts receivable is missing, so operating working capital stays N/A.",
  missing_accounts_payable: "Accounts payable is missing, so operating working capital stays N/A.",
  missing_cost_of_revenue: "Cost of revenue is missing, so this inventory or payables ratio stays N/A.",
  missing_dso: "Days sales outstanding is missing, so the cash conversion cycle stays N/A.",
  missing_revenue: "Revenue is missing, so this working-capital ratio stays N/A.",
  ttm_window_unknown: "The TTM window length is unknown, so days-outstanding is not calculated.",
  no_comparable_quarter: "The corresponding or previous standalone quarter is not available, so growth is not calculated.",
  currency_mismatch: "The two periods are not in the same reporting currency, so they are not compared.",
  prior_not_positive: "The comparison base is zero or negative, so a percentage change is not meaningful.",
  prior_zero: "The comparison base is zero, so a percentage change is not meaningful.",
  missing_value: "This period has no extracted amount. Missing values are not replaced with zero.",
};

export const FLAG_TEXT: Record<string, string> = {
  negative_value: "A quarter has negative revenue (for example a reversal of previously recognized revenue).",
  derivation_mismatch: "A reported quarter differs from the value implied by year-to-date totals.",
  financial_institution:
    "Financial-institution SIC: metrics may be shown, but the corporate FCF and net-debt model does not apply.",
  no_fabricated_foreign_quarters: "Foreign 20-F/6-K reports are not turned into 10-Q quarters.",
  concept_merged: "Two XBRL revenue concepts with identical values were combined to cover the window.",
  concept_change_unverified:
    "The company changed revenue concepts and no overlapping quarter verifies the older figures, so they are not used.",
  other_concept_disagrees:
    "Another revenue concept reports different values; the one presented on the income statement is used.",
  annual_sum_mismatch: "Four reported quarters of a fiscal year do not add up to the reported annual revenue.",
  stale_filings: "The latest quarterly filing is more than 9 months old.",
  statement_mismatch: NA_REASONS.statement_mismatch!,
  filing_mismatch: NA_REASONS.filing_mismatch!,
  ambiguous_concept: NA_REASONS.ambiguous_concept!,
  concept_scope_mismatch: NA_REASONS.concept_scope_mismatch!,
  incompatible_inputs: NA_REASONS.incompatible_inputs!,
  extreme_ratio:
    "This ratio is outside the usual inspect-only range. The computed value is preserved and is not an investment rating.",
};

export const CONCEPT_STATUS: Record<string, string> = {
  single: "Only revenue concept reported in the 12-quarter window.",
  equivalent: "All revenue concepts in the window report the same values.",
  statement_verified: "Selected because it is the revenue line presented on the income statement.",
  override: "Set by a documented override verified against the filings.",
  ambiguous: "Ambiguous — not used for TTM.",
};

export function naReason(code: string | null | undefined): string {
  if (!code) return "";
  return NA_REASONS[code] ?? code.replace(/_/g, " ");
}

export function flagText(code: string): string {
  return FLAG_TEXT[code] ?? code.replace(/_/g, " ");
}
