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
CAPEX_CONCEPTS = [
    "PaymentsToAcquirePropertyPlantAndEquipment",
    "PaymentsToAcquireProductiveAssets",
    "PaymentsForCapitalImprovements",
]

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

CASH_CONCEPTS = [
    "CashAndCashEquivalentsAtCarryingValue",
    "Cash",
    "CashAndDueFromBanks",
]

# Prefer a single current-debt total. Component tags are summed only when no total exists.
ST_DEBT_TOTAL_CONCEPTS = ["DebtCurrent"]
ST_DEBT_PART_CONCEPTS = [
    "LongTermDebtCurrent",
    "ShortTermBorrowings",
    "CommercialPaper",
    "CurrentPortionOfLongTermDebt",
    "ShortTermBankLoansAndNotesPayable",
]

# Prefer noncurrent carrying value. Do not add LongTermDebt + LongTermDebtNoncurrent.
LT_DEBT_CONCEPTS = [
    "LongTermDebtNoncurrent",
    "LongTermDebt",
    "LongTermBorrowings",
    "LongTermNotesAndLoans",
]

FLOW_CONCEPTS = (
    OCF_CONCEPTS
    + CAPEX_CONCEPTS
    + OPERATING_INCOME_CONCEPTS
    + INTEREST_CONCEPTS
    + DA_CONCEPTS
)
STOCK_CONCEPTS = CASH_CONCEPTS + ST_DEBT_TOTAL_CONCEPTS + ST_DEBT_PART_CONCEPTS + LT_DEBT_CONCEPTS

# SIC major groups that should not be forced through corporate FCF / net-debt definitions.
FINANCIAL_SIC_PREFIXES = ("60", "61", "62", "63", "64", "67")

LAYER3_EXTRACTION_VERSION = 1
LAYER3_SCHEMA_VERSION = 1


def is_financial_sic(code: str | None) -> bool:
    if not code:
        return False
    digits = "".join(ch for ch in str(code) if ch.isdigit())
    return any(digits.startswith(p) for p in FINANCIAL_SIC_PREFIXES)
