"""Phase 1 Capital Allocation extract: gross vs net debt, CF identity, missing stays null."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest
from helpers import companyfacts
from test_layer3_extract import _instant, _ytd_year

from screener_pipeline.layer3_build import default_facts_zip
from screener_pipeline.layer3_concepts import (
    CASH_CONCEPTS,
    CF_CASH_CHANGE_EXCLUDING_FX_CONCEPTS,
    CF_CASH_CHANGE_INCLUDING_FX_CONCEPTS,
    DEBT_FINANCING_NET_CONCEPTS,
    DEBT_ISSUANCE_COSTS_NOTE,
    DEBT_ISSUANCE_GROSS_CONCEPTS,
    DEBT_ISSUANCE_NET_OF_COSTS,
    DEBT_REPAYMENT_GROSS_CONCEPTS,
    FLOW_CONCEPTS,
    LAYER3_EXTRACTION_VERSION,
    NET_DEBT_FINANCING_NOTE,
)
from screener_pipeline.layer3_derived import cash_flow_identity
from screener_pipeline.layer3_extract import analyze_layer3_facts

CF_CHANGE_INCL_FX = (
    "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsPeriodIncreaseDecreaseIncludingExchangeRateEffect"
)
CF_CHANGE_EXCL_FX = (
    "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsPeriodIncreaseDecreaseExcludingExchangeRateEffect"
)
FX_ON_RESTRICTED_CASH = "EffectOfExchangeRateOnCashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"
ISSUANCE_NET_OF_COSTS = "ProceedsFromIssuanceOfLongTermDebtAndCapitalSecuritiesNet"


def _cf_core(**extra):
    concepts = {
        "NetCashProvidedByUsedInOperatingActivities": (
            _ytd_year(2025, 40, 40, 40, 40, prefix="O") + _ytd_year(2024, 30, 30, 30, 30, prefix="P")
        ),
        "PaymentsToAcquirePropertyPlantAndEquipment": (
            _ytd_year(2025, 10, 10, 10, 10, prefix="C") + _ytd_year(2024, 8, 8, 8, 8, prefix="D")
        ),
        "CashAndCashEquivalentsAtCarryingValue": [_instant("2025-12-31", 50, "cash", 2025, "FY", form="10-K")],
        **extra,
    }
    return companyfacts(concepts)


def test_ocf_capex_fcf_unchanged_when_capital_allocation_tags_present():
    facts = _cf_core(
        ResearchAndDevelopmentExpense=_ytd_year(2025, 5, 5, 5, 5, prefix="R")
        + _ytd_year(2024, 4, 4, 4, 4, prefix="S"),
        ProceedsFromIssuanceOfLongTermDebt=_ytd_year(2025, 20, 0, 0, 0, prefix="I")
        + _ytd_year(2024, 0, 0, 0, 0, prefix="J"),
    )
    analysis = analyze_layer3_facts(facts)
    assert analysis.extraction_version == LAYER3_EXTRACTION_VERSION
    assert analysis.metrics["ocf"]["ttm"] == 160
    assert analysis.metrics["capex"]["ttm"] == 40
    assert analysis.metrics["fcf"]["ttm"] == 120
    assert analysis.metrics["fcf"]["formula"].startswith("OCF − CapEx")
    assert "researchAndDevelopment" not in analysis.metrics
    assert analysis.metrics["ocf"]["concept"] == "NetCashProvidedByUsedInOperatingActivities"
    assert analysis.metrics["capex"]["concept"] == "PaymentsToAcquirePropertyPlantAndEquipment"


def test_gross_issuance_is_not_a_net_repayments_tag():
    facts = _cf_core(
        ProceedsFromIssuanceOfLongTermDebt=_ytd_year(2025, 100, 0, 0, 0, prefix="G")
        + _ytd_year(2024, 0, 0, 0, 0, prefix="H"),
        RepaymentsOfLongTermDebt=_ytd_year(2025, 40, 0, 0, 0, prefix="R")
        + _ytd_year(2024, 0, 0, 0, 0, prefix="S"),
        ProceedsFromRepaymentsOfCommercialPaper=_ytd_year(2025, 7, -2, 1, 0, prefix="N")
        + _ytd_year(2024, 1, 1, 1, 1, prefix="M"),
    )
    m = analyze_layer3_facts(facts).metrics
    assert m["debtIssuance"]["concept"] == "ProceedsFromIssuanceOfLongTermDebt"
    assert m["debtIssuance"]["financingBasis"] == "gross"
    assert m["debtIssuance"]["ttm"] == 100
    assert "Repayments" not in (m["debtIssuance"]["concept"] or "")
    assert m["debtRepayment"]["concept"] == "RepaymentsOfLongTermDebt"
    assert m["debtRepayment"]["financingBasis"] == "gross"
    assert m["debtRepayment"]["signPolicy"] == "positive_cash_outflow_magnitude"
    assert m["debtRepayment"]["ttm"] == 40
    assert m["netDebtFinancing"]["concept"] == "ProceedsFromRepaymentsOfCommercialPaper"
    assert m["netDebtFinancing"]["financingBasis"] == "net"
    assert m["netDebtFinancing"]["scopeNote"] == NET_DEBT_FINANCING_NOTE
    assert m["netDebtFinancing"]["ttm"] == 6


def test_net_only_debt_is_labeled_net_financing_not_gross_issuance():
    facts = _cf_core(
        ProceedsFromRepaymentsOfLongTermDebt=_ytd_year(2025, 12, -4, 2, 1, prefix="N")
        + _ytd_year(2024, 3, 3, 3, 3, prefix="O"),
    )
    m = analyze_layer3_facts(facts).metrics
    assert m["debtIssuance"]["status"] == "missing"
    assert m["debtIssuance"]["ttm"] is None
    assert m["debtIssuance"].get("financingBasis") is None
    assert m["debtRepayment"]["status"] == "missing"
    assert m["debtRepayment"]["ttm"] is None
    assert m["netDebtFinancing"]["status"] == "extracted"
    assert m["netDebtFinancing"]["financingBasis"] == "net"
    assert m["netDebtFinancing"]["concept"] == "ProceedsFromRepaymentsOfLongTermDebt"
    assert m["netDebtFinancing"]["scopeNote"] == NET_DEBT_FINANCING_NOTE


def test_missing_capital_lines_stay_null_not_zero():
    m = analyze_layer3_facts(_cf_core()).metrics
    for key in (
        "debtIssuance",
        "debtRepayment",
        "netDebtFinancing",
        "equityIssuance",
        "assetSales",
        "shareRepurchases",
        "dividendsPaid",
        "acquisitions",
        "investingCf",
        "financingCf",
    ):
        assert m[key]["ttm"] is None, key
        assert m[key]["status"] == "missing", key
        assert m[key]["reason"] == "no_concept", key
        assert m[key]["ttm"] != 0


def test_debt_balance_change_is_not_treated_as_issuance():
    facts = companyfacts(
        {
            "NetCashProvidedByUsedInOperatingActivities": (
                _ytd_year(2025, 10, 10, 10, 10, prefix="O") + _ytd_year(2024, 9, 9, 9, 9, prefix="P")
            ),
            "PaymentsToAcquirePropertyPlantAndEquipment": (
                _ytd_year(2025, 1, 1, 1, 1, prefix="C") + _ytd_year(2024, 1, 1, 1, 1, prefix="D")
            ),
            "CashAndCashEquivalentsAtCarryingValue": [
                _instant("2025-12-31", 20, "cash25", 2025, "FY", form="10-K"),
                _instant("2024-12-31", 15, "cash24", 2024, "FY", form="10-K"),
            ],
            "LongTermDebtNoncurrent": [
                _instant("2025-12-31", 80, "d25", 2025, "FY", form="10-K"),
                _instant("2024-12-31", 50, "d24", 2024, "FY", form="10-K"),
            ],
            "DebtCurrent": [
                _instant("2025-12-31", 5, "s25", 2025, "FY", form="10-K"),
                _instant("2024-12-31", 5, "s24", 2024, "FY", form="10-K"),
            ],
        }
    )
    m = analyze_layer3_facts(facts).metrics
    assert m["totalDebt"]["value"] == 85
    assert m["debtIssuance"]["ttm"] is None
    assert m["debtIssuance"]["reason"] == "no_concept"
    assert m["netDebtFinancing"]["ttm"] is None


def test_capital_lines_are_not_summed_into_section_totals():
    facts = _cf_core(
        NetCashProvidedByUsedInInvestingActivities=_ytd_year(2025, -25, -25, -25, -25, prefix="V")
        + _ytd_year(2024, -20, -20, -20, -20, prefix="W"),
        NetCashProvidedByUsedInFinancingActivities=_ytd_year(2025, -15, -15, -15, -15, prefix="F")
        + _ytd_year(2024, -10, -10, -10, -10, prefix="G"),
        PaymentsForRepurchaseOfCommonStock=_ytd_year(2025, 8, 8, 8, 8, prefix="B")
        + _ytd_year(2024, 7, 7, 7, 7, prefix="U"),
        PaymentsOfDividends=_ytd_year(2025, 3, 3, 3, 3, prefix="Y")
        + _ytd_year(2024, 2, 2, 2, 2, prefix="Z"),
        PaymentsToAcquireBusinessesNetOfCashAcquired=_ytd_year(2025, 4, 0, 0, 0, prefix="A")
        + _ytd_year(2024, 0, 0, 0, 0, prefix="E"),
    )
    m = analyze_layer3_facts(facts).metrics
    assert m["investingCf"]["ttm"] == -100
    assert m["financingCf"]["ttm"] == -60
    assert m["shareRepurchases"]["ttm"] == 32
    assert m["dividendsPaid"]["ttm"] == 12
    assert m["acquisitions"]["ttm"] == 4
    assert m["investingCf"]["ttm"] != m["capex"]["ttm"] + m["acquisitions"]["ttm"]
    assert m["financingCf"]["ttm"] != -(m["shareRepurchases"]["ttm"] + m["dividendsPaid"]["ttm"])


def test_reconciliation_unavailable_when_fx_required_but_missing():
    facts = _cf_core(
        NetCashProvidedByUsedInInvestingActivities=_ytd_year(2025, -12, -12, -12, -12, prefix="V")
        + _ytd_year(2024, -11, -11, -11, -11, prefix="W"),
        NetCashProvidedByUsedInFinancingActivities=_ytd_year(2025, -8, -8, -8, -8, prefix="F")
        + _ytd_year(2024, -7, -7, -7, -7, prefix="G"),
        **{
            CF_CHANGE_INCL_FX: (
                _ytd_year(2025, 20, 20, 20, 20, prefix="X") + _ytd_year(2024, 10, 10, 10, 10, prefix="Q")
            ),
        },
    )
    ident = analyze_layer3_facts(facts).metrics["cashCfIdentity"]
    assert ident["status"] == "missing"
    assert ident["reason"] == "fx_effect_not_disclosed"
    assert ident["identity"] is None
    assert ident["ttm"] is None
    assert ident["usedF3Cash"] is False
    assert ident["reason"] != "identity_mismatch"


def test_reconciliation_does_not_use_f3_cash_and_holds_on_cf_change():
    inv = _ytd_year(2025, -10, -10, -10, -10, prefix="V") + _ytd_year(2024, -8, -8, -8, -8, prefix="W")
    fin = _ytd_year(2025, -5, -5, -5, -5, prefix="F") + _ytd_year(2024, -4, -4, -4, -4, prefix="G")
    fx = _ytd_year(2025, 1, 1, 1, 1, prefix="X") + _ytd_year(2024, 0, 0, 0, 0, prefix="Y")
    change = _ytd_year(2025, 26, 26, 26, 26, prefix="K") + _ytd_year(2024, 18, 18, 18, 18, prefix="L")
    facts = _cf_core(
        **{
            "NetCashProvidedByUsedInInvestingActivities": inv,
            "NetCashProvidedByUsedInFinancingActivities": fin,
            FX_ON_RESTRICTED_CASH: fx,
            CF_CHANGE_INCL_FX: change,
        }
    )
    # Keep OCF from _cf_core (160 TTM). 160 + (-40) + (-20) + 4 = 104; change TTM = 104.
    m = analyze_layer3_facts(facts).metrics
    assert m["ocf"]["ttm"] == 160
    assert m["cash"]["concept"] == "CashAndCashEquivalentsAtCarryingValue"
    ident = m["cashCfIdentity"]
    assert ident["usedF3Cash"] is False
    assert ident["f3CashConcept"] == "CashAndCashEquivalentsAtCarryingValue"
    assert ident["cashFamily"] == "cash_equivalents_and_restricted_cash"
    assert ident["status"] == "extracted"
    assert ident["identity"] == "holds"
    assert ident["fxIncluded"] is True
    assert ident["ttm"] == 160 - 40 - 20 + 4
    assert ident["reportedChangeTtm"] == 104
    assert ident["ttm"] != m["cash"]["value"]


def test_reconciliation_mismatch_only_when_comparable_inputs_disagree():
    # values_agree uses a $1,000 floor; fixtures must be million-scale so a real gap is a mismatch.
    scale = 1_000_000
    facts = _cf_core(
        NetCashProvidedByUsedInOperatingActivities=(
            _ytd_year(2025, 40 * scale, 40 * scale, 40 * scale, 40 * scale, prefix="O")
            + _ytd_year(2024, 30 * scale, 30 * scale, 30 * scale, 30 * scale, prefix="P")
        ),
        PaymentsToAcquirePropertyPlantAndEquipment=(
            _ytd_year(2025, 10 * scale, 10 * scale, 10 * scale, 10 * scale, prefix="C")
            + _ytd_year(2024, 8 * scale, 8 * scale, 8 * scale, 8 * scale, prefix="D")
        ),
        NetCashProvidedByUsedInInvestingActivities=(
            _ytd_year(2025, -10 * scale, -10 * scale, -10 * scale, -10 * scale, prefix="V")
            + _ytd_year(2024, -8 * scale, -8 * scale, -8 * scale, -8 * scale, prefix="W")
        ),
        NetCashProvidedByUsedInFinancingActivities=(
            _ytd_year(2025, -5 * scale, -5 * scale, -5 * scale, -5 * scale, prefix="F")
            + _ytd_year(2024, -4 * scale, -4 * scale, -4 * scale, -4 * scale, prefix="G")
        ),
        **{
            FX_ON_RESTRICTED_CASH: (
                _ytd_year(2025, 1 * scale, 1 * scale, 1 * scale, 1 * scale, prefix="X")
                + _ytd_year(2024, 0, 0, 0, 0, prefix="Y")
            ),
            CF_CHANGE_INCL_FX: (
                _ytd_year(2025, 99 * scale, 99 * scale, 99 * scale, 99 * scale, prefix="K")
                + _ytd_year(2024, 1 * scale, 1 * scale, 1 * scale, 1 * scale, prefix="L")
            ),
        },
    )
    ident = analyze_layer3_facts(facts).metrics["cashCfIdentity"]
    assert ident["status"] == "extracted"
    assert ident["identity"] == "mismatch"
    assert ident["reason"] == "identity_mismatch"
    assert ident["usedF3Cash"] is False
    assert ident["ttm"] == 104 * scale
    assert ident["reportedChangeTtm"] == 396 * scale


def test_gross_and_net_concept_lists_stay_disjoint():
    issuance = set(DEBT_ISSUANCE_GROSS_CONCEPTS)
    repayment = set(DEBT_REPAYMENT_GROSS_CONCEPTS)
    net = set(DEBT_FINANCING_NET_CONCEPTS)
    assert issuance.isdisjoint(net)
    assert repayment.isdisjoint(net)
    assert issuance.isdisjoint(repayment)
    assert DEBT_ISSUANCE_NET_OF_COSTS <= issuance
    assert all("ProceedsFromRepayments" not in name for name in issuance)
    assert all("ProceedsFromRepayments" not in name for name in repayment)
    assert all("MaturitiesRepaymentsOfPrincipal" not in name for name in repayment)
    assert "CashAndCashEquivalentsAtCarryingValue" not in FLOW_CONCEPTS
    assert "CashAndCashEquivalentsAtCarryingValue" not in CF_CASH_CHANGE_INCLUDING_FX_CONCEPTS
    assert "CashAndCashEquivalentsAtCarryingValue" not in CF_CASH_CHANGE_EXCLUDING_FX_CONCEPTS
    assert set(CASH_CONCEPTS).isdisjoint(set(CF_CASH_CHANGE_INCLUDING_FX_CONCEPTS))
    assert set(CASH_CONCEPTS).isdisjoint(set(CF_CASH_CHANGE_EXCLUDING_FX_CONCEPTS))


def test_issuance_net_of_costs_is_still_gross_of_repayments():
    facts = _cf_core(
        ProceedsFromRepaymentsOfCommercialPaper=_ytd_year(2025, 7, -2, 1, 0, prefix="N")
        + _ytd_year(2024, 1, 1, 1, 1, prefix="M"),
        **{
            ISSUANCE_NET_OF_COSTS: _ytd_year(2025, 15, 0, 0, 0, prefix="G")
            + _ytd_year(2024, 0, 0, 0, 0, prefix="H"),
        },
    )
    m = analyze_layer3_facts(facts).metrics
    assert m["debtIssuance"]["concept"] == ISSUANCE_NET_OF_COSTS
    assert m["debtIssuance"]["financingBasis"] == "gross"
    assert m["debtIssuance"]["scopeNote"] == DEBT_ISSUANCE_COSTS_NOTE
    assert m["debtIssuance"]["ttm"] == 15
    assert m["netDebtFinancing"]["financingBasis"] == "net"
    assert m["netDebtFinancing"]["concept"] == "ProceedsFromRepaymentsOfCommercialPaper"
    assert m["netDebtFinancing"]["scopeNote"] == NET_DEBT_FINANCING_NOTE


def test_maturity_schedule_notes_are_not_cash_repayments():
    facts = _cf_core(
        LongTermDebtMaturitiesRepaymentsOfPrincipalInNextTwelveMonths=[
            _instant("2025-12-31", 9, "mat", 2025, "FY", form="10-K")
        ],
        LongTermDebtMaturitiesRepaymentsOfPrincipalInYearTwo=[
            _instant("2025-12-31", 11, "mat2", 2025, "FY", form="10-K")
        ],
    )
    m = analyze_layer3_facts(facts).metrics
    assert m["debtRepayment"]["status"] == "missing"
    assert m["debtRepayment"]["ttm"] is None
    assert m["debtRepayment"]["reason"] == "no_concept"


def test_missing_cf_change_is_unavailable_not_a_reconciliation_failure():
    ident = analyze_layer3_facts(_cf_core()).metrics["cashCfIdentity"]
    assert ident["status"] == "missing"
    assert ident["reason"] == "missing_cf_cash_change"
    assert ident["identity"] is None
    assert ident["reason"] != "identity_mismatch"
    assert ident["usedF3Cash"] is False
    assert ident["f3CashConcept"] == "CashAndCashEquivalentsAtCarryingValue"


def test_cash_flow_identity_helper_does_not_use_f3_cash():
    def _m(ttm, concept, end="2025-12-31"):
        return {
            "status": "extracted",
            "ttm": ttm,
            "previousTtm": None,
            "concept": concept,
            "quarters": [{"end": end, "value": ttm}],
        }

    ident = cash_flow_identity(
        ocf=_m(160_000_000, "NetCashProvidedByUsedInOperatingActivities"),
        investing=_m(-40_000_000, "NetCashProvidedByUsedInInvestingActivities"),
        financing=_m(-20_000_000, "NetCashProvidedByUsedInFinancingActivities"),
        fx=_m(4_000_000, FX_ON_RESTRICTED_CASH),
        cash_change=_m(104_000_000, CF_CHANGE_INCL_FX),
        includes_fx=True,
        cash_family="cash_equivalents_and_restricted_cash",
        f3_cash_concept="CashAndCashEquivalentsAtCarryingValue",
        align_days=50,
    )
    assert ident["identity"] == "holds"
    assert ident["usedF3Cash"] is False
    assert ident["ttm"] == 104_000_000
    assert ident["ttm"] != 50  # F3 cash stock is not the reconciling amount

    unavailable = cash_flow_identity(
        ocf=_m(160_000_000, "NetCashProvidedByUsedInOperatingActivities"),
        investing=_m(-40_000_000, "NetCashProvidedByUsedInInvestingActivities"),
        financing=_m(-20_000_000, "NetCashProvidedByUsedInFinancingActivities"),
        fx={"status": "missing", "ttm": None, "concept": None, "quarters": []},
        cash_change=_m(104_000_000, CF_CHANGE_INCL_FX),
        includes_fx=True,
        cash_family="cash_equivalents_and_restricted_cash",
        f3_cash_concept="CashAndCashEquivalentsAtCarryingValue",
        align_days=50,
    )
    assert unavailable["status"] == "missing"
    assert unavailable["reason"] == "fx_effect_not_disclosed"
    assert unavailable["identity"] is None
    assert unavailable["reason"] != "identity_mismatch"


def test_excluding_fx_change_line_does_not_require_fx():
    facts = _cf_core(
        NetCashProvidedByUsedInInvestingActivities=_ytd_year(2025, -10, -10, -10, -10, prefix="V")
        + _ytd_year(2024, -8, -8, -8, -8, prefix="W"),
        NetCashProvidedByUsedInFinancingActivities=_ytd_year(2025, -5, -5, -5, -5, prefix="F")
        + _ytd_year(2024, -4, -4, -4, -4, prefix="G"),
        **{
            CF_CHANGE_EXCL_FX: (
                _ytd_year(2025, 25, 25, 25, 25, prefix="K") + _ytd_year(2024, 18, 18, 18, 18, prefix="L")
            ),
        },
    )
    ident = analyze_layer3_facts(facts).metrics["cashCfIdentity"]
    assert ident["status"] == "extracted"
    assert ident["identity"] == "holds"
    assert ident["fxIncluded"] is False
    assert ident["ttm"] == 100
    assert ident["reason"] != "fx_effect_not_disclosed"


def _slim_from_zip(zf: zipfile.ZipFile, cik: str, concepts: set[str]) -> dict:
    with zf.open(f"CIK{cik}.json") as fh:
        raw_payload = json.load(fh)
    gaap = (raw_payload.get("facts") or {}).get("us-gaap") or {}
    slim = {name: gaap[name] for name in concepts if name in gaap}
    return {"cik": raw_payload.get("cik"), "entityName": raw_payload.get("entityName"), "facts": {"us-gaap": slim}}


REAL_CONCEPTS = {
    "NetCashProvidedByUsedInOperatingActivities",
    "PaymentsToAcquirePropertyPlantAndEquipment",
    "CashAndCashEquivalentsAtCarryingValue",
    "NetCashProvidedByUsedInInvestingActivities",
    "NetCashProvidedByUsedInFinancingActivities",
    "ProceedsFromIssuanceOfLongTermDebt",
    "ProceedsFromDebtMaturingInMoreThanThreeMonths",
    "RepaymentsOfLongTermDebt",
    "RepaymentsOfDebtMaturingInMoreThanThreeMonths",
    "ProceedsFromRepaymentsOfCommercialPaper",
    "ProceedsFromRepaymentsOfShortTermDebtMaturingInThreeMonthsOrLess",
    "PaymentsForRepurchaseOfCommonStock",
    "PaymentsOfDividends",
    "PaymentsOfDividendsCommonStock",
    "ProceedsFromIssuanceOfCommonStock",
    "PaymentsToAcquireBusinessesNetOfCashAcquired",
    CF_CHANGE_INCL_FX,
    "CashAndCashEquivalentsPeriodIncreaseDecrease",
    FX_ON_RESTRICTED_CASH,
    "EffectOfExchangeRateOnCashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"
    "IncludingDisposalGroupAndDiscontinuedOperations",
    "EffectOfExchangeRateOnCashAndCashEquivalents",
    "DebtCurrent",
    "LongTermDebtNoncurrent",
}


@pytest.mark.skipif(default_facts_zip() is None, reason="companyfacts.zip not in cache")
def test_real_issuers_distinguish_gross_net_and_do_not_use_f3_cash():
    zpath = default_facts_zip()
    assert zpath is not None
    with zipfile.ZipFile(zpath) as zf:
        meta = analyze_layer3_facts(_slim_from_zip(zf, "0001326801", REAL_CONCEPTS), sic_code="7370")
        msft = analyze_layer3_facts(_slim_from_zip(zf, "0000789019", REAL_CONCEPTS), sic_code="7372")
        aapl = analyze_layer3_facts(_slim_from_zip(zf, "0000320193", REAL_CONCEPTS), sic_code="3571")

    m = meta.metrics
    assert m["ocf"]["ttm"] is not None and m["ocf"]["ttm"] != 0
    assert m["capex"]["ttm"] is not None
    assert m["fcf"]["formula"].startswith("OCF − CapEx")
    assert m["debtIssuance"]["concept"] == "ProceedsFromIssuanceOfLongTermDebt"
    assert m["debtIssuance"]["financingBasis"] == "gross"
    assert "Repayments" not in (m["debtIssuance"]["concept"] or "")
    if m["debtRepayment"]["status"] == "extracted":
        assert m["debtRepayment"]["financingBasis"] == "gross"
        assert m["debtRepayment"]["concept"].startswith("Repayments")
    else:
        assert m["debtRepayment"]["ttm"] is None
    if m["netDebtFinancing"].get("concept"):
        assert m["netDebtFinancing"]["financingBasis"] == "net"
        assert m["netDebtFinancing"]["concept"].startswith("ProceedsFromRepayments")
    assert m["shareRepurchases"]["concept"] == "PaymentsForRepurchaseOfCommonStock"
    assert m["cashCfIdentity"]["usedF3Cash"] is False
    if m["cashCfIdentity"]["status"] == "missing":
        assert m["cashCfIdentity"]["reason"] != "identity_mismatch"
    assert m["cash"]["concept"] == "CashAndCashEquivalentsAtCarryingValue"
    if m["cashChangeCf"].get("concept"):
        assert m["cashChangeCf"]["concept"] != m["cash"]["concept"]

    s = msft.metrics
    assert s["debtIssuance"]["financingBasis"] == "gross"
    assert s["debtIssuance"]["concept"] != "ProceedsFromRepaymentsOfShortTermDebtMaturingInThreeMonthsOrLess"
    if s["netDebtFinancing"].get("concept"):
        assert s["netDebtFinancing"]["financingBasis"] == "net"
        assert s["netDebtFinancing"]["concept"].startswith("ProceedsFromRepayments")
    assert s["shareRepurchases"]["ttm"] is not None
    assert s["dividendsPaid"]["ttm"] is not None
    assert s["cashCfIdentity"]["usedF3Cash"] is False

    a = aapl.metrics
    assert a["debtIssuance"]["concept"] == "ProceedsFromIssuanceOfLongTermDebt"
    assert a["debtIssuance"]["financingBasis"] == "gross"
    assert a["debtRepayment"]["concept"] == "RepaymentsOfLongTermDebt"
    assert a["netDebtFinancing"]["financingBasis"] == "net"
    assert a["netDebtFinancing"]["concept"].startswith("ProceedsFromRepayments")
    assert a["netDebtFinancing"]["concept"] != a["debtIssuance"]["concept"]
    assert a["cashCfIdentity"]["usedF3Cash"] is False
    Path("/tmp/capital-allocation-real.json").write_text(
        json.dumps(
            {
                name: {
                    "ocfTtm": row["ocf"]["ttm"],
                    "capexTtm": row["capex"]["ttm"],
                    "fcfTtm": row["fcf"]["ttm"],
                    "debtIssuance": {
                        "concept": row["debtIssuance"].get("concept"),
                        "basis": row["debtIssuance"].get("financingBasis"),
                        "ttm": row["debtIssuance"].get("ttm"),
                        "status": row["debtIssuance"]["status"],
                    },
                    "debtRepayment": {
                        "concept": row["debtRepayment"].get("concept"),
                        "basis": row["debtRepayment"].get("financingBasis"),
                        "ttm": row["debtRepayment"].get("ttm"),
                        "status": row["debtRepayment"]["status"],
                    },
                    "netDebtFinancing": {
                        "concept": row["netDebtFinancing"].get("concept"),
                        "basis": row["netDebtFinancing"].get("financingBasis"),
                        "ttm": row["netDebtFinancing"].get("ttm"),
                        "status": row["netDebtFinancing"]["status"],
                    },
                    "investingCfTtm": row["investingCf"].get("ttm"),
                    "financingCfTtm": row["financingCf"].get("ttm"),
                    "buybacksTtm": row["shareRepurchases"].get("ttm"),
                    "dividendsTtm": row["dividendsPaid"].get("ttm"),
                    "cashFamily": row["cashCfIdentity"].get("cashFamily"),
                    "cashChangeConcept": row["cashChangeCf"].get("concept"),
                    "f3CashConcept": row["cash"].get("concept"),
                    "identity": {
                        "status": row["cashCfIdentity"]["status"],
                        "reason": row["cashCfIdentity"].get("reason"),
                        "identity": row["cashCfIdentity"].get("identity"),
                        "usedF3Cash": row["cashCfIdentity"].get("usedF3Cash"),
                        "fxIncluded": row["cashCfIdentity"].get("fxIncluded"),
                    },
                }
                for name, row in (("META", m), ("MSFT", s), ("AAPL", a))
            },
            indent=2,
        )
    )
