import { describe, expect, it } from "vitest";
import type { ScreenerRow } from "../types";
import {
  DEFAULT_VIEW,
  filterRows,
  formatSicIndustry,
  industriesFor,
  mixedCurrencies,
  PAGE_SIZE,
  pageCount,
  paginate,
  readViewFromSearch,
  sortRows,
  viewToSearch,
} from "./screener";

function row(ticker: string, patch: Partial<ScreenerRow> = {}): ScreenerRow {
  return {
    ticker,
    name: `${ticker} Inc.`,
    exchange: "NASDAQ",
    type: "common",
    sicCode: "2836",
    sicMajorGroup: "Chemicals and Allied Products",
    sicIndustry: "2836 — Biological Products",
    revenueCurrency: "USD",
    ttmCurrent: null,
    ttmPrevious: null,
    ttmGrowth: null,
    naReason: null,
    latestQuarter: null,
    latestQuarterEnd: null,
    quartersAvailable: 0,
    ...patch,
  };
}

const tickers = (rows: ScreenerRow[]) => rows.map((r) => r.ticker);

describe("sortRows", () => {
  const rows = [
    row("AAA", { ttmCurrent: 5e9, ttmGrowth: -3 }),
    row("BBB", { ttmCurrent: null, ttmGrowth: 12 }),
    row("CCC", { ttmCurrent: 9e10, ttmGrowth: null }),
    row("DDD", { ttmCurrent: 1e8, ttmGrowth: 0 }),
    row("EEE", { ttmCurrent: null, ttmGrowth: null }),
  ];

  it("sorts TTM growth descending with N/A last", () => {
    expect(tickers(sortRows(rows, "ttmGrowth", "desc"))).toEqual(["BBB", "DDD", "AAA", "CCC", "EEE"]);
  });

  it("keeps N/A last when ascending", () => {
    expect(tickers(sortRows(rows, "ttmCurrent", "asc"))).toEqual(["DDD", "AAA", "CCC", "BBB", "EEE"]);
    expect(tickers(sortRows(rows, "ttmGrowth", "asc"))).toEqual(["AAA", "DDD", "BBB", "CCC", "EEE"]);
  });

  it("treats zero as a value, not N/A", () => {
    expect(tickers(sortRows(rows, "ttmGrowth", "desc")).slice(0, 3)).toEqual(["BBB", "DDD", "AAA"]);
  });

  it("does not mix currencies when sorting amounts", () => {
    const mixed = [
      row("USD1", { revenueCurrency: "USD", ttmCurrent: 1 }),
      row("EUR9", { revenueCurrency: "EUR", ttmCurrent: 9e12 }),
      row("USD8", { revenueCurrency: "USD", ttmCurrent: 8 }),
      row("NA", { revenueCurrency: null, ttmCurrent: 99 }),
    ];
    expect(tickers(sortRows(mixed, "ttmCurrent", "desc"))).toEqual(["USD8", "USD1", "EUR9", "NA"]);
  });

  it("does not mutate the input", () => {
    const before = tickers(rows);
    sortRows(rows, "ttmCurrent", "asc");
    expect(tickers(rows)).toEqual(before);
  });

  it("ranks exact and prefix ticker matches first when searching", () => {
    const r = [row("ALNY", { ttmGrowth: 1, name: "Alnylam" }), row("AL", { ttmGrowth: 0, name: "Air Lease" }), row("XAL", { ttmGrowth: 9, name: "Almond" })];
    expect(tickers(sortRows(r, "ttmGrowth", "desc", "al"))).toEqual(["AL", "ALNY", "XAL"]);
  });
});

describe("filterRows", () => {
  const rows = [
    row("VRTX", { name: "Vertex Pharmaceuticals" }),
    row("AAPL", {
      name: "Apple Inc.",
      sicMajorGroup: "Electronic and Other Electrical Equipment",
      sicIndustry: "3571 — Electronic Computers",
      sicCode: "3571",
    }),
    row("NESN", { name: "Nestlé Holdings", revenueCurrency: "CHF" }),
    row("UNK", { name: "Unknown Co", sicMajorGroup: null, sicIndustry: null, sicCode: null }),
  ];

  it("filters by SEC SIC major group, industry, and currency", () => {
    expect(tickers(filterRows(rows, { sicMajorGroup: "Electronic and Other Electrical Equipment", sicIndustry: "", currency: "", query: "" }))).toEqual(["AAPL"]);
    expect(tickers(filterRows(rows, { sicMajorGroup: "", sicIndustry: "2836 — Biological Products", currency: "", query: "" }))).toEqual(["VRTX", "NESN"]);
    expect(tickers(filterRows(rows, { sicMajorGroup: "", sicIndustry: "", currency: "CHF", query: "" }))).toEqual(["NESN"]);
  });

  it("matches ticker prefix or name substring, case and accent insensitive", () => {
    const f = { sicMajorGroup: "", sicIndustry: "", currency: "", query: "" };
    expect(tickers(filterRows(rows, { ...f, query: "vr" }))).toEqual(["VRTX"]);
    expect(tickers(filterRows(rows, { ...f, query: "PHARMA" }))).toEqual(["VRTX"]);
    expect(tickers(filterRows(rows, { ...f, query: "nestle" }))).toEqual(["NESN"]);
    expect(filterRows(rows, { ...f, query: "rtx" })).toHaveLength(0);
  });
});

describe("pagination", () => {
  it("uses 50 rows per page", () => {
    expect(PAGE_SIZE).toBe(50);
    const rows = Array.from({ length: 120 }, (_, i) => i);
    expect(pageCount(rows.length)).toBe(3);
    expect(paginate(rows, 1)).toHaveLength(50);
    expect(paginate(rows, 3)).toEqual(rows.slice(100));
  });

  it("clamps out-of-range pages", () => {
    const rows = [1, 2, 3];
    expect(pageCount(0)).toBe(1);
    expect(paginate(rows, 99)).toEqual(rows);
    expect(paginate(rows, 0)).toEqual(rows);
  });
});

describe("formatSicIndustry", () => {
  it("puts the industry name first so lists sort alphabetically", () => {
    expect(formatSicIndustry("2836 — Biological Products")).toBe("Biological Products — 2836");
    expect(formatSicIndustry("Pharmaceutical Preparations — 2834")).toBe("Pharmaceutical Preparations — 2834");
    expect(formatSicIndustry("0000")).toBe("0000");
    expect(formatSicIndustry(null)).toBe("");
  });
});

describe("industriesFor and mixedCurrencies", () => {
  const groups = { Chemicals: ["2834 — Pharma", "2836 — Bio"], Electronics: ["3571 — Computers"] };
  it("returns the major group's industries or a de-duplicated list sorted by name", () => {
    expect(industriesFor(groups, "Chemicals")).toEqual(["2836 — Bio", "2834 — Pharma"]);
    expect(industriesFor(groups, "")).toEqual(["2836 — Bio", "3571 — Computers", "2834 — Pharma"]);
    expect(industriesFor(groups, "Energy")).toEqual([]);
  });
  it("detects mixed currencies", () => {
    expect(mixedCurrencies([row("A"), row("B", { revenueCurrency: "EUR" })])).toBe(true);
    expect(mixedCurrencies([row("A"), row("B")])).toBe(false);
  });
});

describe("URL state", () => {
  it("round-trips a view", () => {
    const v = {
      sicMajorGroup: "Chemicals and Allied Products",
      sicIndustry: "2836 — Biological Products",
      currency: "USD",
      query: "al",
      sort: "ttmCurrent" as const,
      dir: "asc" as const,
      page: 2,
    };
    expect(readViewFromSearch(viewToSearch(v))).toEqual(v);
  });

  it("omits defaults and rejects invalid values", () => {
    expect(viewToSearch(DEFAULT_VIEW)).toBe("");
    expect(DEFAULT_VIEW.sort).toBe("ttmGrowth");
    expect(readViewFromSearch("?sort=marketCap&dir=up&page=-4")).toEqual(DEFAULT_VIEW);
  });
});
