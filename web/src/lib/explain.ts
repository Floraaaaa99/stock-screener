/** Human-readable explanations for the pipeline's reason codes and flags. */

export const NA_REASONS: Record<string, string> = {
  foreign_filer:
    "Foreign private issuer: files annual 20-F and 6-K reports, so SEC Company Facts has no quarterly 10-Q revenue.",
  no_cik: "No SEC company (CIK) matches this ticker.",
  no_company_facts: "SEC Company Facts data is not available for this company.",
  no_revenue_concept: "No total-revenue concept is reported in this company's 10-Q/10-K XBRL data.",
  no_quarterly_revenue: "No quarterly revenue could be derived from the company's filings.",
  ambiguous_concept:
    "Revenue concepts in the filings disagree and the income statement does not show which is total revenue.",
  gap_in_quarters: "A quarter is missing within the 8 quarters needed for the TTM comparison.",
  insufficient_quarters: "Fewer than 8 consecutive quarters of revenue history are available.",
  previous_ttm_not_positive: "Previous TTM revenue is zero or negative, so growth is not meaningful.",
  statement_mismatch: "The latest revenue figure disagrees with the filing's income statement.",
  filing_mismatch: "A quarter used in the TTM disagrees with the income statement of its filing.",
  no_sic: "SEC submissions did not include an SIC code for this company.",
};

export const FLAG_TEXT: Record<string, string> = {
  negative_value: "A quarter has negative revenue (for example a reversal of previously recognized revenue).",
  derivation_mismatch: "A reported quarter differs from the value implied by year-to-date totals.",
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
