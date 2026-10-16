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
  missing_short_term_debt: "Short-term debt is missing, so total and net debt stay N/A.",
  missing_long_term_debt: "Long-term debt is missing, so total and net debt stay N/A.",
  missing_cash: "Cash and cash equivalents are missing, so net debt stays N/A.",
  debt_period_mismatch: "Short-term debt component tags do not share the same balance-sheet date.",
  layer3_concepts_not_in_compact_facts:
    "Cash-flow and balance-sheet concepts are not stored in the compact revenue/earnings facts cache.",
  financial_institution_review_required:
    "This SIC industry is a financial institution; corporate FCF and net-debt definitions are not applied.",
  official_filing_unparsed:
    "A newer official 10-Q/10-K is on EDGAR, but its income statement could not be read, so this window is stale.",
  official_filing_no_applicable_revenue:
    "A newer official 10-Q/10-K was read and has no applicable total-revenue line. The verified window is older than that filing.",
  official_quarter_not_in_window:
    "Official revenue from a newer filing was read but is not yet in the verified eight-quarter TTM window.",
};

export const FLAG_TEXT: Record<string, string> = {
  negative_value: "A quarter has negative revenue (for example a reversal of previously recognized revenue).",
  derivation_mismatch: "A reported quarter differs from the value implied by year-to-date totals.",
  financial_institution: "Financial-institution SIC: metrics may be shown, but the corporate scoring model does not apply.",
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
