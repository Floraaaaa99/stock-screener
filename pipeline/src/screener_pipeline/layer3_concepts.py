"""Proposed US-GAAP mappings for Layer 3 Phase 2.

Priority is a preference order among *equivalent* tags, not a reason to mix scopes or
to treat investing/financing cash flows as operating or CapEx. One concept is selected
per metric unless a documented aggregation (debt components) is applied.
"""

from __future__ import annotations

# Operating cash flow — continuing operations only. Do not use financing or investing totals.
OCF_CONCEPTS = [
    "NetCashProvidedByUsedInOperatingActivities",
    "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
]

# CapEx as cash paid for PPE / productive assets. Not acquisitions, not all investing outflows.
# The net productive-assets tag is last-resort only (some issuers tag face CapEx this way).
CAPEX_CONCEPTS = [
    "PaymentsToAcquirePropertyPlantAndEquipment",
    "PaymentsToAcquireProductiveAssets",
    "PaymentsForCapitalImprovements",
    "PaymentsForProceedsFromProductiveAssets",
]
CAPEX_MAY_BE_NET = {"PaymentsForProceedsFromProductiveAssets"}

OPERATING_INCOME_CONCEPTS = [
    "OperatingIncomeLoss",
    "IncomeLossFromContinuingOperationsBeforeInterestAndTaxes",
]

INTEREST_CONCEPTS = [
    "InterestExpense",
    "InterestExpenseDebt",
    "InterestAndDebtExpense",
]

DA_CONCEPTS = [
    "DepreciationDepletionAndAmortization",
    "DepreciationAndAmortization",
    "Depreciation",
]
# Used only when the selected D&A concept is depreciation-only. Financing-cost
# amortization stays out of EBITDA.
DEPRECIATION_ONLY_CONCEPTS = {"Depreciation"}
AMORTIZATION_ADDON_CONCEPTS = [
    "AmortizationOfIntangibleAssets",
    "AmortizationOfIntangibles",
]

CASH_CONCEPTS = [
    "CashAndCashEquivalentsAtCarryingValue",
    "Cash",
    "CashAndDueFromBanks",
]

# Prefer a single current-debt total. Component tags are summed only when no total exists.
# LongTermDebt (unqualified) is a common *total* tag and is not added here — see TOTAL_DEBT_FALLBACK.
ST_DEBT_TOTAL_CONCEPTS = ["DebtCurrent"]
ST_DEBT_PART_CONCEPTS = [
    "LongTermDebtCurrent",
    "LongTermDebtAndCapitalLeaseObligationsCurrent",
    "ShortTermBorrowings",
    "CommercialPaper",
    "CurrentPortionOfLongTermDebt",
    "ShortTermBankLoansAndNotesPayable",
]

# Noncurrent carrying value only. Do not add LongTermDebt + LongTermDebtNoncurrent.
# Lease-inclusive tags are last-resort fallbacks and are flagged.
LT_DEBT_CONCEPTS = [
    "LongTermDebtNoncurrent",
    "LongTermBorrowings",
    "LongTermNotesAndLoans",
    "LongTermDebtAndCapitalLeaseObligationsNoncurrent",
    "LongTermDebtAndCapitalLeaseObligations",
]
LT_DEBT_INCLUDES_LEASES = {
    "LongTermDebtAndCapitalLeaseObligationsNoncurrent",
    "LongTermDebtAndCapitalLeaseObligations",
}

# Used only when short-term and long-term parts cannot both be aligned to the same date.
TOTAL_DEBT_FALLBACK_CONCEPTS = [
    "DebtAndCapitalLeaseObligations",
    "LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities",
    "LongTermDebt",
    "NotesPayable",
]
TOTAL_DEBT_INCLUDES_LEASES = {
    "DebtAndCapitalLeaseObligations",
    "LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities",
}

FLOW_CONCEPTS = (
    OCF_CONCEPTS
    + CAPEX_CONCEPTS
    + OPERATING_INCOME_CONCEPTS
    + INTEREST_CONCEPTS
    + DA_CONCEPTS
    + AMORTIZATION_ADDON_CONCEPTS
)
STOCK_CONCEPTS = (
    CASH_CONCEPTS
    + ST_DEBT_TOTAL_CONCEPTS
    + ST_DEBT_PART_CONCEPTS
    + LT_DEBT_CONCEPTS
    + TOTAL_DEBT_FALLBACK_CONCEPTS
)

STOCK_ALIGN_DAYS = 10
FLOW_ALIGN_DAYS = 50

# SIC major groups that should not be forced through corporate FCF / net-debt definitions.
FINANCIAL_SIC_PREFIXES = ("60", "61", "62", "63", "64", "67")

LAYER3_EXTRACTION_VERSION = 3
LAYER3_SCHEMA_VERSION = 1


def is_financial_sic(code: str | None) -> bool:
    if not code:
        return False
    digits = "".join(ch for ch in str(code) if ch.isdigit())
    return any(digits.startswith(p) for p in FINANCIAL_SIC_PREFIXES)
