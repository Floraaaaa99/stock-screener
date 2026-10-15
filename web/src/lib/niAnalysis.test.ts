import { describe, expect, it } from "vitest";
import type { Layer2Rate, Layer2Row } from "../types";
import {
  NI_IMP_FOUR_YOY,
  NI_IMP_SEQ,
  NI_IMP_TO_LOSS,
  NI_IMP_TURNAROUND,
  NI_PROF_ALL,
  NI_PROF_ALL_LOSS,
  NI_PROF_BREAKEVEN,
  NI_PROF_INSUFFICIENT,
  NI_PROF_MULTI_LOSS,
  NI_PROF_ONE_LOSS,
  analyzeNetIncome,
  formatNiChange,
  niRuleStatus,
} from "./niAnalysis";

function rate(patch: Partial<Layer2Rate> = {}): Layer2Rate {
  return {
    fiscalYear: 2026,
    fiscalQuarter: 2,
    start: "2026-04-01",
    end: "2026-06-30",
    label: "FY2026 Q2",
    rate: 10,
    reason: null,
    kind: "yoy",
    currentValue: 100,
    otherValue: 80,
    absoluteChange: 20,
    currentUrl: "https://ex/c",
    otherUrl: "https://ex/p",
    currentForm: "10-Q",
    otherForm: "10-Q",
    currentCheck: "match",
    otherCheck: "match",
    ...patch,
  };
}

function four(
  values: number[],
  priors: number[],
  extra: Partial<Layer2Rate> = {},
): Layer2Rate[] {
  const labels = [
    { fy: 2026, fq: 1, end: "2025-09-30", label: "FY2026 Q1" },
    { fy: 2026, fq: 2, end: "2025-12-31", label: "FY2026 Q2" },
    { fy: 2026, fq: 3, end: "2026-03-31", label: "FY2026 Q3" },
    { fy: 2026, fq: 4, end: "2026-06-30", label: "FY2026 Q4" },
  ];
  return labels.map((l, i) =>
    rate({
      fiscalYear: l.fy,
      fiscalQuarter: l.fq,
      end: l.end,
      label: l.label,
      currentValue: values[i],
      otherValue: priors[i],
      absoluteChange: values[i]! - priors[i]!,
      rate: priors[i]! > 0 ? ((values[i]! / priors[i]! - 1) * 100) : null,
      reason: priors[i]! > 0 ? null : "nonpositive_denominator",
      ...extra,
    }),
  );
}

function row(values: number[], priors: number[], patch: Partial<Layer2Row> = {}): Layer2Row {
  const yoy = four(values, priors);
  return {
    ticker: "TST",
    name: "Test",
    exchange: "NASDAQ",
    type: "common",
    sicCode: "2834",
    sicMajorGroup: "Chemicals",
    sicIndustry: "Pharmaceutical Preparations — 2834",
    revenueCurrency: "USD",
    revenueConcept: "Revenues",
    layer1SchemaVersion: 2,
    ttmGrowth: 20,
    ttmReason: null,
    bucket: "passed",
    dataReviewReasons: [],
    yoy,
    qoq: four(values, [values[0]! - 1, values[0]!, values[1]!, values[2]!], { kind: "qoq" }),
    earningsConcept: "NetIncomeLoss",
    earningsYoy: four(values, priors),
    earningsQoq: four(values, [priors[0]!, values[0]!, values[1]!, values[2]!], { kind: "qoq" }),
    badges: [],
    appliedCategories: [],
    freshness: {
      status: "current",
      asOf: "2026-10-15",
      window: "verified_historical",
      latestVerified: null,
      expectedNext: null,
      message: null,
    },
    rulesVersion: 4,
    ...patch,
  };
}

function applied(ids: { applied: boolean; id: string }[]): string[] {
  return ids.filter((b) => b.applied).map((b) => b.id);
}

describe("profitability", () => {
  it("flags all four profitable and TTM as the sum", () => {
    const ni = analyzeNetIncome(row([10, 20, 30, 40], [5, 6, 7, 8]));
    expect(ni.ttm).toBe(100);
    expect(ni.profitableCount).toBe(4);
    expect(ni.lossCount).toBe(0);
    expect(ni.breakEvenCount).toBe(0);
    expect(ni.latestIsLoss).toBe(false);
    expect(applied(ni.profitability)).toEqual([NI_PROF_ALL]);
  });

  it("flags one historical loss separately from a latest-quarter loss", () => {
    const hist = analyzeNetIncome(row([10, -2, 30, 40], [5, 6, 7, 8]));
    expect(applied(hist.profitability)).toEqual([NI_PROF_ONE_LOSS]);
    expect(hist.lossQuarters).toEqual(["FY2026 Q2"]);
    expect(hist.latestIsLoss).toBe(false);

    const latest = analyzeNetIncome(row([10, 20, 30, -4], [5, 6, 7, 8]));
    expect(applied(latest.profitability)).toEqual([NI_PROF_ONE_LOSS]);
    expect(latest.lossQuarters).toEqual(["FY2026 Q4"]);
    expect(latest.latestIsLoss).toBe(true);
  });

  it("flags two or three losses and all four loss-making", () => {
    expect(applied(analyzeNetIncome(row([10, -1, -2, 4], [1, 1, 1, 1])).profitability)).toEqual([NI_PROF_MULTI_LOSS]);
    expect(applied(analyzeNetIncome(row([-1, -2, -3, 4], [1, 1, 1, 1])).profitability)).toEqual([NI_PROF_MULTI_LOSS]);
    expect(applied(analyzeNetIncome(row([-1, -2, -3, -4], [1, 1, 1, 1])).profitability)).toEqual([NI_PROF_ALL_LOSS]);
  });

  it("adds break-even as an extra badge and counts zeros separately", () => {
    const ni = analyzeNetIncome(row([10, 0, 30, 40], [5, 6, 7, 8]));
    expect(ni.profitableCount).toBe(3);
    expect(ni.lossCount).toBe(0);
    expect(ni.breakEvenCount).toBe(1);
    expect(applied(ni.profitability)).toEqual([NI_PROF_BREAKEVEN]);
    expect(ni.profitability[0]?.tooltip).toContain("FY2026 Q2");
  });

  it("does not treat unverified or missing NI as zero", () => {
    const base = row([10, 20, 30, 40], [5, 6, 7, 8]);
    const unverified = base.earningsYoy!.map((e, i) => (i === 3 ? { ...e, currentCheck: "unavailable", reason: "unverified" } : e));
    const ni = analyzeNetIncome({ ...base, earningsYoy: unverified });
    expect(ni.ttm).toBeNull();
    expect(ni.quarters[3]?.display).toBeNull();
    expect(applied(ni.profitability)).toEqual([NI_PROF_INSUFFICIENT]);
    expect(ni.ttmReason).toBe("insufficient_ni_window");
  });

  it("does not substitute older quarters when a window quarter is missing", () => {
    const base = row([10, 20, 30, 40], [5, 6, 7, 8]);
    const missing = base.earningsYoy!.map((e, i) => (i === 1 ? { ...e, currentValue: null, currentCheck: null, reason: "missing_quarter" } : e));
    const ni = analyzeNetIncome({ ...base, earningsYoy: missing });
    expect(ni.quarters[1]?.value).toBeNull();
    expect(ni.ttm).toBeNull();
    expect(applied(ni.profitability)).toEqual([NI_PROF_INSUFFICIENT]);
  });
});

describe("profit improvement", () => {
  it("treats a narrower loss as YoY improvement without using a percentage", () => {
    const ni = analyzeNetIncome(row([-8, -6, -4, -2], [-20, -18, -16, -14]));
    expect(applied(ni.improvement)).toEqual(expect.arrayContaining([NI_IMP_FOUR_YOY, NI_IMP_SEQ]));
    expect(applied(ni.profitability)).toEqual([NI_PROF_ALL_LOSS]);
    expect(ni.quarters.every((q) => q.yoyAbs != null && q.yoyAbs > 0)).toBe(true);
    const fmt = formatNiChange(6_000_000, -14_000_000, null, "USD");
    expect(fmt.text).toBe("+$6.000M USD");
    expect(fmt.title).toContain("zero or negative");
  });

  it("flags a latest-quarter turnaround independently of YoY", () => {
    const ni = analyzeNetIncome(row([5, 6, -3, 4], [9, 9, 9, 9]));
    expect(applied(ni.improvement)).toContain(NI_IMP_TURNAROUND);
    expect(applied(ni.improvement)).not.toContain(NI_IMP_FOUR_YOY);
    expect(applied(ni.improvement)).not.toContain(NI_IMP_TO_LOSS);
    expect(applied(ni.profitability)).toEqual([NI_PROF_ONE_LOSS]);
  });

  it("flags latest-quarter turned to loss", () => {
    const ni = analyzeNetIncome(row([5, 6, 7, -1], [1, 1, 1, 1]));
    expect(applied(ni.improvement)).toContain(NI_IMP_TO_LOSS);
    expect(applied(ni.improvement)).not.toContain(NI_IMP_TURNAROUND);
    expect(ni.latestIsLoss).toBe(true);
  });

  it("leaves an unavailable rule off without blocking others", () => {
    const base = row([5, 6, -3, 4], [1, 1, 1, 1]);
    const yoy = base.earningsYoy!.map((e, i) => (i === 0 ? { ...e, otherValue: null, otherCheck: null, reason: "missing_quarter" } : e));
    const ni = analyzeNetIncome({ ...base, earningsYoy: yoy });
    const four = ni.improvement.find((b) => b.id === NI_IMP_FOUR_YOY);
    expect(four?.applied).toBe(false);
    expect(four?.tooltip).toMatch(/Unavailable/);
    expect(applied(ni.improvement)).toContain(NI_IMP_TURNAROUND);
  });

  it("uses fiscal labels for a June year-end (non-calendar)", () => {
    const ni = analyzeNetIncome(row([1, 2, 3, 4], [0.5, 0.5, 0.5, 0.5]));
    expect(ni.quarters[0]?.label).toBe("FY2026 Q1");
    expect(ni.quarters[0]?.end).toBe("2025-09-30");
    expect(applied(ni.improvement)).toContain(NI_IMP_SEQ);
  });

  it("does not treat no-badge as deterioration", () => {
    const ni = analyzeNetIncome(row([40, 30, 20, 10], [10, 10, 10, 10]));
    const seq = ni.improvement.find((b) => b.id === NI_IMP_SEQ);
    expect(seq?.applied).toBe(false);
    expect(seq?.tooltip).toMatch(/Unmet/);
    expect(niRuleStatus(seq!)).toBe("unmet");
    expect(applied(ni.profitability)).toEqual([NI_PROF_ALL]);
  });

  it("keeps profitable-but-declining NI as Passed-descriptive all-profitable", () => {
    const ni = analyzeNetIncome(row([40, 30, 20, 10], [50, 40, 30, 20]));
    expect(applied(ni.profitability)).toEqual([NI_PROF_ALL]);
    expect(applied(ni.improvement)).not.toContain(NI_IMP_FOUR_YOY);
    expect(applied(ni.improvement)).not.toContain(NI_IMP_SEQ);
    expect(ni.ttm).toBe(100);
    expect(ni.quarters.every((q) => q.yoyAbs != null && q.yoyAbs < 0)).toBe(true);
  });

  it("does not apply four YoY improvements when the window is empty", () => {
    const base = row([10, 20, 30, 40], [5, 6, 7, 8]);
    const ni = analyzeNetIncome({ ...base, yoy: [], earningsYoy: [], earningsQoq: [] });
    const four = ni.improvement.find((b) => b.id === NI_IMP_FOUR_YOY);
    expect(four?.applied).toBe(false);
    expect(niRuleStatus(four!)).toBe("unavailable");
    expect(applied(ni.profitability)).toEqual([NI_PROF_INSUFFICIENT]);
  });

  it("does not treat incomparable NI concepts as YoY improvement", () => {
    const base = row([12, 13, 14, 15], [1, 2, 3, 4]);
    const yoy = base.earningsYoy!.map((e, i) => (i === 1 ? { ...e, reason: "incomparable_concept" } : e));
    const ni = analyzeNetIncome({ ...base, earningsYoy: yoy });
    expect(ni.quarters[1]?.priorVerified).toBe(false);
    expect(applied(ni.improvement)).not.toContain(NI_IMP_FOUR_YOY);
    expect(applied(ni.profitability)).toEqual([NI_PROF_ALL]);
  });
});
