import { describe, expect, it } from "vitest";
import {
  CAT_ACCEL,
  CAT_DECLINE,
  CAT_FOUR_POS,
  CAT_JUMP,
  CAT_OTHER,
  CAT_STABLE,
  CAT_UNABLE,
  CAT_VOL,
  classifyQoqBadges,
  filterLayer2,
  layer2ToSearch,
  readLayer2View,
  type Layer2View,
} from "./layer2";
import type { Layer2Row } from "../types";

function applied(rates: (number | null)[], spread: number | null = null, jump: number | null = null) {
  return classifyQoqBadges(rates, { stableSpreadPp: spread, recentJumpPp: jump })
    .filter((b) => b.applied)
    .map((b) => b.id);
}

describe("classifyQoqBadges", () => {
  it("shows Threshold not configured until values are chosen", () => {
    const badges = classifyQoqBadges([5, 5, 5, 8], { stableSpreadPp: null, recentJumpPp: null });
    const blocked = badges.filter((b) => b.blockedByThreshold);
    expect(blocked.map((b) => b.id).sort()).toEqual([CAT_JUMP, CAT_STABLE].sort());
    expect(blocked.every((b) => b.tooltip.includes("Threshold not configured"))).toBe(true);
    expect(blocked.every((b) => !b.applied)).toBe(true);
  });

  it("applies accelerating, stable, and jump together at inclusive boundaries", () => {
    const ids = applied([1, 2, 3, 20], 19, 17);
    expect(ids).toEqual(expect.arrayContaining([CAT_ACCEL, CAT_STABLE, CAT_JUMP]));
    expect(applied([1, 2, 3, 20], 18.999, null)).not.toContain(CAT_STABLE);
    expect(applied([1, 2, 3, 20], null, 17.0001)).not.toContain(CAT_JUMP);
  });

  it("flags latest-quarter decline without earlier QoQ", () => {
    const ids = applied([null, null, null, -1]);
    expect(ids).toContain(CAT_DECLINE);
    expect(ids).not.toContain(CAT_UNABLE);
  });

  it("detects volatility ignoring zeros", () => {
    expect(applied([10, 0, -10, 10])).toContain(CAT_VOL);
  });

  it("does not assign other/flat while thresholds are unconfigured", () => {
    expect(applied([1, 1, 1, 1])).toContain(CAT_FOUR_POS);
    expect(applied([1, 1, 1, 1])).not.toContain(CAT_OTHER);
    expect(applied([1, 1, 1, 1])).not.toContain(CAT_UNABLE);
  });

  it("does not assign other/flat when QoQ classification is incomplete", () => {
    expect(applied([null, null, 1, 1])).toContain(CAT_UNABLE);
    expect(applied([null, null, 1, 1])).not.toContain(CAT_OTHER);
  });

  it("uses other/flat only after every rule that could apply has been evaluated", () => {
    expect(applied([5, 5, 5, 0], 0.5, 10)).toContain(CAT_OTHER);
    expect(applied([5, 5, 5, 0], 0.5, 10)).not.toContain(CAT_FOUR_POS);
  });

  it("flags four consecutive positive QoQ without a spread threshold", () => {
    expect(applied([1.8, 9.5, 8.6, 2.5])).toContain(CAT_FOUR_POS);
    expect(applied([1.8, 9.5, 8.6, 2.5])).not.toContain(CAT_ACCEL);
    expect(applied([15, 12, 10, -15])).not.toContain(CAT_FOUR_POS);
  });
});

describe("filterLayer2", () => {
  const row = (ticker: string, patch: Partial<Layer2Row> = {}): Layer2Row =>
    ({
      ticker,
      name: `${ticker} Inc`,
      exchange: "NASDAQ",
      type: "common",
      sicCode: "2834",
      sicMajorGroup: "Chemicals",
      sicIndustry: "2834 — Pharma",
      revenueCurrency: "USD",
      revenueConcept: "Revenues",
      layer1SchemaVersion: 2,
      ttmGrowth: 10,
      ttmReason: null,
      bucket: "passed",
      dataReviewReasons: [],
      yoy: [],
      qoq: [],
      badges: [],
      appliedCategories: ["qoq_volatility"],
      rulesVersion: 1,
      ...patch,
    }) as Layer2Row;

  it("matches any selected category and keeps SIC/search", () => {
    const rows = [
      row("AAA"),
      row("BBB", { appliedCategories: ["latest_quarter_revenue_decline"] }),
      row("CCC", { sicMajorGroup: "Other", appliedCategories: ["qoq_volatility"] }),
    ];
    const f = { sicMajorGroup: "Chemicals", sicIndustry: "", query: "", categories: ["qoq_volatility"] };
    expect(filterLayer2(rows, "passed", f).map((r) => r.ticker)).toEqual(["AAA"]);
    expect(filterLayer2(rows, "passed", { ...f, categories: ["qoq_volatility", "latest_quarter_revenue_decline"] }).map((r) => r.ticker)).toEqual([
      "AAA",
      "BBB",
    ]);
  });
});

describe("Layer2View type", () => {
  it("defaults tab to passed", () => {
    const v: Layer2View = {
      tab: "passed",
      sicMajorGroup: "",
      sicIndustry: "",
      query: "",
      categories: [],
      stableSpreadPp: null,
      recentJumpPp: null,
      page: 1,
    };
    expect(v.tab).toBe("passed");
  });
});

describe("layer2 URL state", () => {
  it("round-trips layer, tab, categories and thresholds", () => {
    const view: Layer2View = {
      tab: "watchlist",
      sicMajorGroup: "Chemicals",
      sicIndustry: "2834 — Pharma",
      query: "inc",
      categories: ["qoq_volatility", "latest_quarter_revenue_decline"],
      stableSpreadPp: 5,
      recentJumpPp: 10,
      page: 2,
    };
    const search = layer2ToSearch(2, view, "");
    const parsed = readLayer2View(search);
    expect(parsed.layer).toBe(2);
    expect(parsed.view).toEqual(view);
  });

  it("treats missing layer as Layer 1 and leaves thresholds unconfigured", () => {
    const parsed = readLayer2View("");
    expect(parsed.layer).toBe(1);
    expect(parsed.view.tab).toBe("passed");
    expect(parsed.view.stableSpreadPp).toBeNull();
    expect(parsed.view.recentJumpPp).toBeNull();
  });
});
