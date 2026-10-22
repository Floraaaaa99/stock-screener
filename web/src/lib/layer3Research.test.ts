import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { formatDays, formatExactMoney, formatRatio, formatRatioPercent } from "./format";
import {
  capitalLineTitle,
  cashReconciliationState,
  chartableFlowPoints,
  chronologicalQuarters,
  displayAmount,
  displayKind,
  EIGHT_K_AWAITING_LABEL,
  formatPeriodLabel,
  hasAwaitingEightK,
  hasConceptScopeMismatch,
  isEightKDerived,
  isFiniteNumber,
  isNetDebtFinancingTag,
  LAYER3_RESEARCH_SECTIONS,
  layer3ToSearch,
  pairQuarterGrowth,
  periodKey,
  readLayer3Cik,
  ttmChange,
  verificationLabel,
} from "./layer3Research";
import type { Layer3Quarter, Layer3Row } from "../types";

function q(
  fy: number,
  fq: number,
  value: number | null,
  extra: Partial<Layer3Quarter> = {},
): Layer3Quarter {
  return {
    fiscalYear: fy,
    fiscalQuarter: fq,
    start: extra.start ?? null,
    end: extra.end ?? `${fy}-${String(fq * 3).padStart(2, "0")}-28`,
    value,
    method: extra.method ?? "reported",
    formula: extra.formula ?? null,
    ...extra,
  };
}

function loadIssuer(cik: string): Layer3Row {
  return JSON.parse(readFileSync(`public/data/layer3/cik/${cik}.json`, "utf8")) as Layer3Row;
}

describe("overview period labels", () => {
  it("treats matching fiscal period and end date as the same TTM window", () => {
    const period = { fiscalYear: 2026, fiscalQuarter: 3, end: "2026-07-31" };
    expect(periodKey(period)).toBe("2026|3|2026-07-31");
    expect(periodKey(period)).toBe(periodKey({ ...period }));
    expect(formatPeriodLabel(period)).toBe("FY2026 Q3 · 2026-07-31");
    expect(periodKey(null)).toBe("");
    expect(formatPeriodLabel(null)).toBeNull();
  });
});

describe("Layer 3 research URL", () => {
  it("reads and writes a canonical CIK without changing the list URL", () => {
    expect(readLayer3Cik("?layer=3")).toBeNull();
    expect(readLayer3Cik("?layer=3&cik=46619")).toBe("0000046619");
    expect(readLayer3Cik("?layer=3&cik=0000000000")).toBeNull();
    expect(layer3ToSearch(null)).toBe("?layer=3");
    expect(layer3ToSearch("46619")).toBe("?layer=3&cik=0000046619");
    expect(layer3ToSearch("0000000000")).toBe("?layer=3");
  });
});

describe("pairQuarterGrowth", () => {
  const series = [
    q(2024, 3, 100),
    q(2024, 4, 110),
    q(2025, 1, 80),
    q(2025, 2, null),
    q(2025, 3, 130),
    q(2025, 4, 0),
    q(2026, 1, 40),
    q(2026, 2, -10),
  ];

  it("pairs YoY on the same fiscal quarter only", () => {
    const pairs = pairQuarterGrowth(series, "yoy", "USD");
    const q3 = pairs.find((p) => p.current.fiscalYear === 2025 && p.current.fiscalQuarter === 3);
    expect(q3?.prior?.fiscalYear).toBe(2024);
    expect(q3?.prior?.fiscalQuarter).toBe(3);
    expect(q3?.rate).toBeCloseTo(30);
    expect(q3?.absoluteChange).toBe(30);
  });

  it("does not skip a missing QoQ predecessor", () => {
    const pairs = pairQuarterGrowth(series, "qoq", "USD");
    const q3 = pairs.find((p) => p.current.fiscalYear === 2025 && p.current.fiscalQuarter === 3);
    expect(q3?.prior?.value ?? null).toBeNull();
    expect(q3?.rate).toBeNull();
    expect(q3?.reason).toBe("no_comparable_quarter");
  });

  it("pairs consecutive fiscal quarters including year wrap", () => {
    const pairs = pairQuarterGrowth(series, "qoq", "USD");
    const q1 = pairs.find((p) => p.current.fiscalYear === 2025 && p.current.fiscalQuarter === 1);
    expect(q1?.prior?.fiscalYear).toBe(2024);
    expect(q1?.prior?.fiscalQuarter).toBe(4);
    expect(q1?.rate).toBeCloseTo((80 / 110 - 1) * 100);
  });

  it("does not invent a percentage when the base is zero or negative", () => {
    const pairs = pairQuarterGrowth(series, "qoq", "USD");
    const afterZero = pairs.find((p) => p.current.fiscalYear === 2026 && p.current.fiscalQuarter === 1);
    expect(afterZero?.rate).toBeNull();
    expect(afterZero?.absoluteChange).toBe(40);
    expect(afterZero?.reason).toBe("prior_zero");
    const afterNeg = pairQuarterGrowth([q(2025, 4, -20), q(2026, 1, 10)], "qoq", "USD")[1];
    expect(afterNeg?.rate).toBeNull();
    expect(afterNeg?.absoluteChange).toBe(30);
    expect(afterNeg?.reason).toBe("prior_not_positive");
  });

  it("rejects a currency mismatch instead of pairing", () => {
    const pairs = pairQuarterGrowth(
      [
        { ...q(2025, 1, 100), unit: "USD" } as Layer3Quarter,
        { ...q(2025, 2, 120), unit: "CAD" } as Layer3Quarter,
      ],
      "qoq",
    );
    expect(pairs[1]?.rate).toBeNull();
    expect(pairs[1]?.reason).toBe("currency_mismatch");
  });

  it("does not treat a missing current quarter as zero", () => {
    const pairs = pairQuarterGrowth([q(2025, 1, 100), q(2025, 2, null)], "qoq", "USD");
    expect(pairs[1]?.rate).toBeNull();
    expect(pairs[1]?.absoluteChange).toBeNull();
    expect(pairs[1]?.reason).toBe("missing_value");
  });

  it("does not interpolate a YoY gap", () => {
    const pairs = pairQuarterGrowth([q(2024, 2, 50), q(2025, 3, 80)], "yoy", "USD");
    const later = pairs.find((p) => p.current.fiscalYear === 2025);
    expect(later?.rate).toBeNull();
    expect(later?.reason).toBe("no_comparable_quarter");
  });
});

describe("display helpers never coerce missing to zero", () => {
  it("returns null for missing and not-applicable metrics", () => {
    expect(displayAmount({ status: "missing", reason: "no_concept", ttm: null, verification: "not_checked" })).toBeNull();
    expect(
      displayAmount({ status: "not_applicable", reason: "no_inventory_concept", value: null, verification: "not_checked" }),
    ).toBeNull();
    expect(displayAmount({ status: "extracted", reason: null, ttm: 0, verification: "company_facts_only" })).toBe(0);
    expect(isFiniteNumber(null)).toBe(false);
    expect(displayKind({ status: "missing", reason: "no_concept", ttm: null, verification: "not_checked" })).toBe("missing");
    expect(
      displayKind({
        status: "missing",
        reason: "concept_scope_mismatch",
        ttm: null,
        verification: "not_checked",
        qualityFlags: ["incompatible_inputs"],
        unreliableTtm: 0.4,
      }),
    ).toBe("suppressed");
  });

  it("uses stored TTM YoY when present and dollar change when the base is negative", () => {
    expect(ttmChange({ status: "extracted", reason: null, ttm: 120, previousTtm: 100, ttmYoy: 20, verification: "company_facts_only" })).toEqual({
      rate: 20,
      absoluteChange: 20,
      reason: null,
    });
    expect(
      ttmChange({
        status: "extracted",
        reason: null,
        ttm: -10,
        previousTtm: -40,
        ttmYoy: null,
        ttmYoyReason: "previous_ttm_not_positive",
        verification: "company_facts_only",
      }),
    ).toEqual({
      rate: null,
      absoluteChange: 30,
      reason: "previous_ttm_not_positive",
    });
  });
});

describe("format helpers for research units", () => {
  it("keeps missing as N/A and distinguishes ratios from percent fields", () => {
    expect(formatRatioPercent(null)).toBe("N/A");
    expect(formatRatioPercent(0.40398)).toBe("+40.4%");
    expect(formatExactMoney(null)).toBe("N/A");
    expect(formatExactMoney(1_111_232_000, "USD")).toBe("$1,111,232,000 USD");
    expect(formatDays(null)).toBe("N/A");
    expect(formatDays(47.02697)).toBe("47.0 days");
    expect(formatRatio(2.717)).toBe("2.72");
  });
});

describe("representative issuer files", () => {
  it("HEI uses derived gross profit and extracted manufacturing working capital", () => {
    const hei = loadIssuer("0000046619");
    expect(hei.schemaVersion).toBe(3);
    expect(hei.extractionVersion).toBe(5);
    expect(hei.metrics?.grossProfit?.calculationMethod).toBe("derived");
    expect(hei.metrics?.grossProfit?.ttm).toBe(2_091_317_000);
    expect(hei.metrics?.grossMargin?.ttm).toBeCloseTo(0.4039821463480218);
    expect(displayKind(hei.metrics?.grossProfit)).toBe("derived");
    expect(displayKind(hei.metrics?.revenue)).toBe("reported");
    expect(hei.metrics?.inventory?.status).toBe("extracted");
    expect(hei.metrics?.cashConversionCycle?.status).toBe("extracted");
    expect(chronologicalQuarters(hei.metrics?.revenue?.quarters).every((row) => row.value !== 0 || isFiniteNumber(row.value))).toBe(true);
  });

  it("MSFT reports gross profit and keeps inventory as extracted, not N/A", () => {
    const msft = loadIssuer("0000789019");
    expect(msft.metrics?.grossProfit?.calculationMethod).toBe("extracted");
    expect(msft.metrics?.grossProfit?.identity).toBe("gross_plus_cogs_equals_revenue");
    expect(msft.metrics?.inventory?.status).toBe("extracted");
    expect(displayAmount(msft.metrics?.revenue)).toBe(331_839_000_000);
  });

  it("NVDA keeps the 52/53-week fiscal end date", () => {
    const nvda = loadIssuer("0001045810");
    expect(nvda.dataAsOf).toBe("2026-07-26");
    expect(nvda.metrics?.cash?.end).toBe("2026-07-26");
    expect(nvda.metrics?.revenue?.quarters?.[0]?.end).toBe("2026-07-26");
  });

  it("ZSTK uses the canonical CIK and does not invent cash-conversion or YoY on a negative base", () => {
    const zstk = loadIssuer("0001790169");
    expect(zstk.cik).toBe("0001790169");
    expect(zstk.modelApplicability).toBe("not_applicable");
    expect(zstk.metrics?.ocf?.ttm).toBe(-5_601_000);
    expect(zstk.metrics?.cashConversion?.status).toBe("missing");
    expect(zstk.metrics?.cashConversion?.reason).toBe("denominator_not_positive");
    expect(zstk.metrics?.netIncome?.ttmYoy).toBeNull();
    const change = ttmChange(zstk.metrics?.netIncome);
    expect(change.rate).toBeNull();
    expect(change.absoluteChange).toBe(-177_837_000 - -13_046_000);
  });

  it("JHI is insufficient facts and does not turn missing inventory into zero", () => {
    const jhi = loadIssuer("0000759828");
    expect(jhi.extractionStatus).toBe("insufficient_facts");
    expect(displayAmount(jhi.metrics?.revenue)).toBeNull();
    expect(jhi.metrics?.inventory?.status).toBe("not_applicable");
    expect(displayKind(jhi.metrics?.inventory)).toBe("not_applicable");
    expect(jhi.metrics?.inventory?.value).toBeNull();
  });

  it("VSXY keeps conflicting GP/COGS and suppresses derived ratios", () => {
    const vsxy = loadIssuer("0001856437");
    expect(hasConceptScopeMismatch(vsxy)).toBe(true);
    expect(vsxy.metrics?.grossProfit?.identity).toBe("concept_scope_mismatch");
    expect(vsxy.metrics?.grossProfit?.ttm).toBe(2_735_000_000);
    expect(vsxy.metrics?.grossMargin?.status).toBe("missing");
    expect(displayAmount(vsxy.metrics?.grossMargin)).toBeNull();
    expect(displayKind(vsxy.metrics?.grossMargin)).toBe("suppressed");
    expect(vsxy.metrics?.grossMargin?.unreliableTtm).toBeCloseTo(0.3956886574074074);
    expect(vsxy.metrics?.dio?.qualityFlags).toContain("incompatible_inputs");
  });

  it("JPM is a financial issuer with inventory not applicable", () => {
    const jpm = loadIssuer("0000019617");
    expect(jpm.modelApplicability).toBe("not_applicable");
    expect(jpm.flags).toContain("financial_institution");
    expect(jpm.metrics?.inventory?.status).toBe("not_applicable");
    expect(displayAmount(jpm.metrics?.inventory)).toBeNull();
    expect(jpm.metrics?.grossProfit?.status).toBe("missing");
    expect(displayAmount(jpm.metrics?.revenue)).toBe(199_408_000_000);
  });
});

describe("capital allocation presentation", () => {
  it("keeps gross issuance, gross repayment, and net financing as distinct labels", () => {
    expect(LAYER3_RESEARCH_SECTIONS.map((s) => s.id)).toContain("capital-allocation");
    expect(isNetDebtFinancingTag("ProceedsFromRepaymentsOfCommercialPaper")).toBe(true);
    expect(isNetDebtFinancingTag("ProceedsFromIssuanceOfLongTermDebt")).toBe(false);
    expect(capitalLineTitle("issuance", { concept: "ProceedsFromIssuanceOfLongTermDebt", financingBasis: "gross" })).toBe(
      "Debt issuance (gross)",
    );
    expect(
      capitalLineTitle("issuance", {
        concept: "ProceedsFromRepaymentsOfLongTermDebt",
        financingBasis: "net",
      }),
    ).toBe("Net debt financing");
    expect(
      capitalLineTitle("net", {
        concept: "ProceedsFromRepaymentsOfShortTermDebtMaturingInThreeMonthsOrLess",
        financingBasis: "net",
      }),
    ).toBe("Net debt financing");
    expect(capitalLineTitle("repayment", { concept: "RepaymentsOfLongTermDebt", financingBasis: "gross" })).toBe(
      "Debt repayment (gross)",
    );
  });

  it("does not treat missing FX or a missing CF change as a reconciliation failure", () => {
    expect(
      cashReconciliationState({
        status: "missing",
        reason: "fx_effect_not_disclosed",
        ttm: null,
        identity: null,
        usedF3Cash: false,
      }),
    ).toBe("unavailable");
    expect(
      cashReconciliationState({
        status: "missing",
        reason: "missing_cf_cash_change",
        ttm: null,
        identity: null,
        usedF3Cash: false,
      }),
    ).toBe("unavailable");
    expect(
      cashReconciliationState({
        status: "extracted",
        reason: "identity_mismatch",
        ttm: 100,
        identity: "mismatch",
        usedF3Cash: false,
      }),
    ).toBe("mismatch");
    expect(
      cashReconciliationState({
        status: "extracted",
        reason: null,
        ttm: 100,
        identity: "holds",
        usedF3Cash: true,
      }),
    ).toBe("unavailable");
    expect(displayAmount({ status: "missing", reason: "no_concept", ttm: null, verification: "not_checked" })).toBeNull();
    expect(
      chartableFlowPoints(
        {
          status: "missing",
          reason: "ttm_window_not_aligned",
          ttm: null,
          verification: "not_checked",
          concept: "ProceedsFromIssuanceOfLongTermDebt",
          quarters: [{ fiscalYear: 2021, fiscalQuarter: 1, start: null, end: "2021-03-31", value: 12, method: "reported", formula: null }],
        },
        "quarter",
      ),
    ).toEqual([]);
  });
});

describe("8-K provisional Layer 3 labels", () => {
  it("labels awaiting 10-Q verification and does not treat missing 8-K metrics as zero", () => {
    expect(verificationLabel("awaiting_10q")).toBe(EIGHT_K_AWAITING_LABEL);
    expect(isEightKDerived({ sourceType: "8k_earnings_release", verification: "awaiting_10q" })).toBe(true);
    expect(isEightKDerived({ sourceType: "company_facts" })).toBe(false);
    const row = {
      flags: ["eight_k_awaiting_10q"],
      provisionalEarnings: { status: "awaiting_10q", label: EIGHT_K_AWAITING_LABEL, fiscalYear: 2026, fiscalQuarter: 3 },
    } as Layer3Row;
    expect(hasAwaitingEightK(row)).toBe(true);
    const eightK = q(2026, 3, 51_242_000_000, {
      sourceType: "8k_earnings_release",
      verification: "awaiting_10q",
    });
    const prior = q(2025, 3, 40_589_000_000, { sourceType: "company_facts" });
    const yoy = pairQuarterGrowth([prior, eightK], "yoy", "USD");
    expect(yoy[1]?.rate).toBeCloseTo((51_242_000_000 / 40_589_000_000 - 1) * 100);
    expect(isEightKDerived(yoy[1]?.current)).toBe(true);
  });
});
