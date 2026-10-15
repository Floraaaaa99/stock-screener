import { describe, expect, it } from "vitest";
import type { Layer2Rate, Layer2Row } from "../types";
import { comparisonRows, priorYearRows } from "./compare";

function rate(patch: Partial<Layer2Rate>): Layer2Rate {
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
    currentUrl: "https://example.test/cur",
    otherUrl: "https://example.test/pri",
    currentForm: "10-Q",
    otherForm: "10-Q",
    currentCheck: "match",
    otherCheck: "match",
    ...patch,
  };
}

function row(patch: Partial<Layer2Row> = {}): Layer2Row {
  return {
    ticker: "INCY",
    name: "Incyte",
    exchange: "NASDAQ",
    type: "common",
    sicCode: "2834",
    sicMajorGroup: "Chemicals",
    sicIndustry: "Pharmaceutical Preparations — 2834",
    revenueCurrency: "USD",
    revenueConcept: "Revenues",
    layer1SchemaVersion: 2,
    ttmGrowth: 26.9,
    ttmReason: null,
    bucket: "passed",
    dataReviewReasons: [],
    yoy: [
      rate({ fiscalYear: 2026, fiscalQuarter: 1, end: "2026-03-31", label: "FY2026 Q1", currentValue: 127, otherValue: 105, rate: 20.9, kind: "yoy" }),
      rate({ currentValue: 167, otherValue: 122, rate: 37.7, kind: "yoy" }),
    ],
    qoq: [
      rate({ fiscalYear: 2026, fiscalQuarter: 1, end: "2026-03-31", label: "FY2026 Q1", currentValue: 127, otherValue: 151, rate: -15.5, kind: "qoq" }),
      rate({ currentValue: 167, otherValue: 127, rate: 31.5, kind: "qoq" }),
    ],
    earningsConcept: "NetIncomeLoss",
    earningsYoy: [
      rate({ fiscalYear: 2026, fiscalQuarter: 1, end: "2026-03-31", label: "FY2026 Q1", currentValue: 303, otherValue: 158, rate: 91.7, kind: "yoy" }),
      rate({ currentValue: 586, otherValue: 405, rate: 44.6, kind: "yoy" }),
    ],
    earningsQoq: [
      rate({ fiscalYear: 2026, fiscalQuarter: 1, end: "2026-03-31", label: "FY2026 Q1", currentValue: 303, otherValue: 299, rate: 1.4, kind: "qoq" }),
      rate({ currentValue: 586, otherValue: 303, rate: 93.1, kind: "qoq" }),
    ],
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

describe("comparisonRows", () => {
  it("puts revenue and net income rates on one row per quarter", () => {
    const rows = comparisonRows(row());
    expect(rows).toHaveLength(2);
    const latest = rows[1]!;
    expect(latest).toMatchObject({
      label: "FY2026 Q2",
      end: "2026-06-30",
      revenue: 167,
      earnings: 586,
    });
    expect(latest.revYoy?.rate).toBe(37.7);
    expect(latest.niYoy?.rate).toBe(44.6);
    expect(latest.revQoq?.rate).toBe(31.5);
    expect(latest.niQoq?.rate).toBe(93.1);
  });

  it("leaves net income empty when earnings series is missing", () => {
    const latest = comparisonRows(row({ earningsYoy: [], earningsQoq: [] }))[1]!;
    expect(latest.earnings).toBeNull();
    expect(latest.niYoy).toBeNull();
    expect(latest.niQoq).toBeNull();
    expect(latest.revenue).toBe(167);
  });
});

describe("priorYearRows", () => {
  it("labels the YoY denominator as the same fiscal quarter last year", () => {
    const prior = priorYearRows(row())[1]!;
    expect(prior).toMatchObject({
      label: "FY2025 Q2",
      revenue: 122,
      earnings: 405,
      form: "10-Q",
    });
  });
});
