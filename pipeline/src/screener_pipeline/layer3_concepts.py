"""US-GAAP mappings for Layer 3 financial research extracts.

Priority is a preference order among *equivalent* tags, not a reason to mix scopes or
to treat investing/financing cash flows as operating or CapEx. One concept is selected
per metric unless a documented aggregation (debt components) is applied.

Gross Profit and Cost of Revenue are chosen together so they stay in the same
accounting scope as the selected revenue concept. The first non-empty tag is never
selected by itself.
"""

from __future__ import annotations

from .sec.facts import EARNINGS_CONCEPTS, REVENUE_CONCEPTS

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

# Investing / financing statement totals. Never a sum of child lines.
INVESTING_CF_CONCEPTS = [
    "NetCashProvidedByUsedInInvestingActivities",
    "NetCashProvidedByUsedInInvestingActivitiesContinuingOperations",
]
FINANCING_CF_CONCEPTS = [
    "NetCashProvidedByUsedInFinancingActivities",
    "NetCashProvidedByUsedInFinancingActivitiesContinuingOperations",
]

# Gross cash proceeds from new borrowings. Not ProceedsFromRepayments* (those are net).
# Tags whose US-GAAP name is "Net" of issuance costs are still gross of repayments.
DEBT_ISSUANCE_GROSS_CONCEPTS = [
    "ProceedsFromIssuanceOfLongTermDebt",
    "ProceedsFromLongTermDebt",
    "ProceedsFromIssuanceOfSeniorLongTermDebt",
    "ProceedsFromIssuanceOfLongTermDebtAndCapitalSecuritiesNet",
    "ProceedsFromDebtNetOfIssuanceCosts",
    "ProceedsFromDebtMaturingInMoreThanThreeMonths",
    "ProceedsFromNotesPayable",
    "ProceedsFromLinesOfCredit",
    "ProceedsFromShortTermDebt",
    "ProceedsFromShortTermDebtMaturingInMoreThanThreeMonths",
    "ProceedsFromShortTermDebtMaturingInThreeMonthsOrLess",
    "ProceedsFromOtherShortTermDebt",
    "ProceedsFromConvertibleDebt",
]
DEBT_ISSUANCE_NET_OF_COSTS = {
    "ProceedsFromIssuanceOfLongTermDebtAndCapitalSecuritiesNet",
    "ProceedsFromDebtNetOfIssuanceCosts",
}

# Gross cash repayments of debt. Maturity-schedule notes are not cash-flow amounts.
DEBT_REPAYMENT_GROSS_CONCEPTS = [
    "RepaymentsOfLongTermDebt",
    "RepaymentsOfLongTermDebtAndCapitalSecurities",
    "RepaymentsOfDebtMaturingInMoreThanThreeMonths",
    "RepaymentsOfSeniorDebt",
    "RepaymentsOfDebt",
    "RepaymentsOfNotesPayable",
    "RepaymentsOfShortTermDebt",
    "RepaymentsOfShortTermDebtMaturingInMoreThanThreeMonths",
    "RepaymentsOfShortTermDebtMaturingInThreeMonthsOrLess",
    "RepaymentsOfOtherShortTermDebt",
    "RepaymentsOfCommercialPaper",
    "RepaymentsOfConvertibleDebt",
]

# Single cash-flow line that nets issuances and repayments. Never labeled gross issuance.
DEBT_FINANCING_NET_CONCEPTS = [
    "ProceedsFromRepaymentsOfLongTermDebt",
    "ProceedsFromRepaymentsOfOtherLongTermDebt",
    "ProceedsFromRepaymentsOfDebt",
    "ProceedsFromRepaymentsOfBankDebt",
    "ProceedsFromRepaymentsOfNotesPayable",
    "ProceedsFromRepaymentsOfShortTermDebt",
    "ProceedsFromRepaymentsOfShortTermDebtMaturingInMoreThanThreeMonths",
    "ProceedsFromRepaymentsOfShortTermDebtMaturingInThreeMonthsOrLess",
    "ProceedsFromRepaymentsOfCommercialPaper",
    "ProceedsFromRepaymentsOfBankOverdrafts",
    "ProceedsFromRepaymentsOfOtherDebt",
]
NET_DEBT_FINANCING_NOTE = (
    "US-GAAP tag nets issuances and repayments. Shown as Net debt financing, "
    "not gross issuance or gross repayment."
)
DEBT_ISSUANCE_COSTS_NOTE = (
    "US-GAAP tag is net of issuance costs. It is still gross of repayments, "
    "not a ProceedsFromRepayments net-financing line."
)

EQUITY_ISSUANCE_CONCEPTS = [
    "ProceedsFromIssuanceOfCommonStock",
    "ProceedsFromIssuanceOfSharesUnderIncentiveAndShareBasedCompensationPlans",
    "ProceedsFromStockOptionsExercised",
    "ProceedsFromIssuanceOfPreferredStockAndPreferenceStock",
    "ProceedsFromIssuanceOfCommonStockWarrants",
]

ASSET_SALE_CONCEPTS = [
    "ProceedsFromSaleOfPropertyPlantAndEquipment",
    "ProceedsFromDivestitureOfBusinessesNetOfCashDivested",
    "ProceedsFromDivestitureOfBusinesses",
]

SHARE_REPURCHASE_CONCEPTS = [
    "PaymentsForRepurchaseOfCommonStock",
    "PaymentsForRepurchaseOfEquity",
    "PaymentsForRepurchaseOfPreferredStockAndPreferenceStock",
]

DIVIDEND_PAID_CONCEPTS = [
    "PaymentsOfDividends",
    "PaymentsOfDividendsCommonStock",
    "PaymentsOfOrdinaryDividends",
    "PaymentsOfDividendsPreferredStockAndPreferenceStock",
]

ACQUISITION_CF_CONCEPTS = [
    "PaymentsToAcquireBusinessesNetOfCashAcquired",
    "PaymentsToAcquireBusinessesGross",
    "PaymentsToAcquireBusinessesAndInterestInAffiliates",
]

# Cash-flow statement change in cash. Never F3 CashAndCashEquivalentsAtCarryingValue.
CF_CASH_CHANGE_INCLUDING_FX_CONCEPTS = [
    "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsPeriodIncreaseDecreaseIncludingExchangeRateEffect",
    "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsPeriodIncreaseDecreaseIncludingExchangeRateEffectContinuingOperations",
    "CashAndCashEquivalentsPeriodIncreaseDecrease",
]
CF_CASH_CHANGE_EXCLUDING_FX_CONCEPTS = [
    "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsPeriodIncreaseDecreaseExcludingExchangeRateEffect",
    "CashAndCashEquivalentsPeriodIncreaseDecreaseExcludingExchangeRateEffect",
]
FX_ON_CASH_CONCEPTS = [
    "EffectOfExchangeRateOnCashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
    "EffectOfExchangeRateOnCashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsIncludingDisposalGroupAndDiscontinuedOperations",
    "EffectOfExchangeRateOnCashAndCashEquivalents",
]
RESTRICTED_CASH_FAMILY = "cash_equivalents_and_restricted_cash"
UNRESTRICTED_CASH_FAMILY = "cash_and_cash_equivalents"

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

GROSS_PROFIT_CONCEPTS = [
    "GrossProfit",
    "GrossProfitLoss",
]

# Total cost of sales / services. Component tags (depreciation in COGS, shipping)
# are not used as stand-ins for the income-statement cost-of-revenue line.
COST_OF_REVENUE_CONCEPTS = [
    "CostOfRevenue",
    "CostOfGoodsAndServicesSold",
    "CostOfGoodsSold",
    "CostOfServices",
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

# Current net trade receivables. Gross / unbilled / other-receivable tags stay out.
AR_CONCEPTS = [
    "AccountsReceivableNetCurrent",
    "ReceivablesNetCurrent",
    "AccountsReceivableNet",
    "TradeAccountsReceivableNetCurrent",
]

# Merchandise / total inventory at carrying value. Finished-goods-only tags are last-resort.
INVENTORY_CONCEPTS = [
    "InventoryNet",
    "InventoryFinishedGoodsNetOfReserves",
    "InventoryFinishedGoods",
]
INVENTORY_NARROW_SCOPE = {
    "InventoryFinishedGoodsNetOfReserves",
    "InventoryFinishedGoods",
}

# Current trade payables. Accrued expenses and other current liabilities stay out.
AP_CONCEPTS = [
    "AccountsPayableCurrent",
    "AccountsPayableTradeCurrent",
    "AccountsPayable",
]

CURRENT_ASSET_CONCEPTS = ["AssetsCurrent"]
CURRENT_LIABILITY_CONCEPTS = ["LiabilitiesCurrent"]

FLOW_CONCEPTS = (
    list(REVENUE_CONCEPTS)
    + list(EARNINGS_CONCEPTS)
    + OCF_CONCEPTS
    + CAPEX_CONCEPTS
    + OPERATING_INCOME_CONCEPTS
    + INTEREST_CONCEPTS
    + DA_CONCEPTS
    + AMORTIZATION_ADDON_CONCEPTS
    + GROSS_PROFIT_CONCEPTS
    + COST_OF_REVENUE_CONCEPTS
    + INVESTING_CF_CONCEPTS
    + FINANCING_CF_CONCEPTS
    + DEBT_ISSUANCE_GROSS_CONCEPTS
    + DEBT_REPAYMENT_GROSS_CONCEPTS
    + DEBT_FINANCING_NET_CONCEPTS
    + EQUITY_ISSUANCE_CONCEPTS
    + ASSET_SALE_CONCEPTS
    + SHARE_REPURCHASE_CONCEPTS
    + DIVIDEND_PAID_CONCEPTS
    + ACQUISITION_CF_CONCEPTS
    + CF_CASH_CHANGE_INCLUDING_FX_CONCEPTS
    + CF_CASH_CHANGE_EXCLUDING_FX_CONCEPTS
    + FX_ON_CASH_CONCEPTS
)
STOCK_CONCEPTS = (
    CASH_CONCEPTS
    + ST_DEBT_TOTAL_CONCEPTS
    + ST_DEBT_PART_CONCEPTS
    + LT_DEBT_CONCEPTS
    + TOTAL_DEBT_FALLBACK_CONCEPTS
    + AR_CONCEPTS
    + INVENTORY_CONCEPTS
    + AP_CONCEPTS
    + CURRENT_ASSET_CONCEPTS
    + CURRENT_LIABILITY_CONCEPTS
)

STOCK_ALIGN_DAYS = 10
FLOW_ALIGN_DAYS = 50
HISTORY_SLOTS = 8

# SIC major groups that should not be forced through corporate FCF / net-debt definitions.
FINANCIAL_SIC_PREFIXES = ("60", "61", "62", "63", "64", "67")

LAYER3_EXTRACTION_VERSION = 5
LAYER3_SCHEMA_VERSION = 3
LAYER3_ISSUER_FILE_TEMPLATE = "layer3/cik/{cik}.json"
ZERO_CIK = "0000000000"


def normalize_cik(value: object | None) -> str | None:
    """Canonical 10-digit CIK, or None when the value is missing/zero/unusable."""
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() == "none":
        return None
    digits = "".join(ch for ch in text if ch.isdigit())
    if not digits:
        return None
    padded = str(int(digits)).zfill(10)
    if padded == ZERO_CIK:
        return None
    return padded


def is_financial_sic(code: str | None) -> bool:
    if not code:
        return False
    digits = "".join(ch for ch in str(code) if ch.isdigit())
    return any(digits.startswith(p) for p in FINANCIAL_SIC_PREFIXES)


def gaap_concepts_present(companyfacts: dict, concepts: list[str]) -> list[str]:
    """us-gaap concept names that exist in the payload, regardless of units or forms."""
    gaap = (companyfacts.get("facts") or {}).get("us-gaap") or {}
    return [c for c in concepts if c in gaap]


def cf_cash_family(concept: str | None) -> str | None:
    """Cash definition used by a cash-flow-statement change tag. Not F3 cash."""
    if not concept:
        return None
    if "RestrictedCash" in concept:
        return RESTRICTED_CASH_FAMILY
    if concept.startswith("CashAndCashEquivalentsPeriodIncreaseDecrease"):
        return UNRESTRICTED_CASH_FAMILY
    return None


def cash_change_includes_fx(concept: str | None) -> bool | None:
    """Whether the CF change line already includes FX. None when the tag is not a change line."""
    if not concept:
        return None
    if "ExcludingExchangeRateEffect" in concept:
        return False
    if "IncludingExchangeRateEffect" in concept:
        return True
    if concept == "CashAndCashEquivalentsPeriodIncreaseDecrease":
        return True
    return None
