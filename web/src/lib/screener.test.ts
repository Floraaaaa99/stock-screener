import { describe, expect, it } from "vitest";
import type { ScreenerRow } from "../types";
import {
  DEFAULT_VIEW,
  filterRows,
  industriesFor,
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
    sector: "Healthcare",
    industry: "Biotechnology",
    marketCap: null,
    price: null,
    priceCurrency: "USD",
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
    row("AAA", { marketCap: 5e9, ttmGrowth: -3 }),
    row("BBB", { marketCap: null, ttmGrowth: 12 }),
    row("CCC", { marketCap: 9e10, ttmGrowth: null }),
    row("DDD", { marketCap: 1e8, ttmGrowth: 0 }),
    row("EEE", { marketCap: null, ttmGrowth: null }),
  ];

  it("sorts descending with N/A last", () => {
    expect(tickers(sortRows(rows, "marketCap", "desc"))).toEqual(["CCC", "AAA", "DDD", "BBB", "EEE"]);
  });

  it("keeps N/A last when ascending", () => {
    expect(tickers(sortRows(rows, "marketCap", "asc"))).toEqual(["DDD", "AAA", "CCC", "BBB", "EEE"]);
    expect(tickers(sortRows(rows, "ttmGrowth", "asc"))).toEqual(["AAA", "DDD", "BBB", "CCC", "EEE"]);
  });

  it("treats zero as a value, not N/A", () => {
    expect(tickers(sortRows(rows, "ttmGrowth", "desc")).slice(0, 3)).toEqual(["BBB", "DDD", "AAA"]);
  });

  it("does not mutate the input", () => {
    const before = tickers(rows);
    sortRows(rows, "marketCap", "asc");
    expect(tickers(rows)).toEqual(before);
  });

  it("ranks exact and prefix ticker matches first when searching", () => {
    const r = [row("ALNY", { marketCap: 1, name: "Alnylam" }), row("AL", { marketCap: 0, name: "Air Lease" }), row("XAL", { marketCap: 9, name: "Almond" })];
    expect(tickers(sortRows(r, "marketCap", "desc", "al"))).toEqual(["AL", "ALNY", "XAL"]);
  });
});

describe("filterRows", () => {
  const rows = [
    row("VRTX", { name: "Vertex Pharmaceuticals" }),
    row("AAPL", { name: "Apple Inc.", sector: "Technology", industry: "Consumer Electronics" }),
    row("NESN", { name: "Nestlé Holdings", sector: "Consumer Defensive", industry: "Packaged Foods" }),
    row("UNK", { name: "Unknown Co", sector: null, industry: null }),
  ];

  it("filters by sector and industry", () => {
    expect(tickers(filterRows(rows, { sector: "Technology", industry: "", query: "" }))).toEqual(["AAPL"]);
    expect(tickers(filterRows(rows, { sector: "", industry: "Biotechnology", query: "" }))).toEqual(["VRTX"]);
    expect(filterRows(rows, { sector: "", industry: "", query: "" })).toHaveLength(4);
  });

  it("matches ticker prefix or name substring, case and accent insensitive", () => {
    expect(tickers(filterRows(rows, { sector: "", industry: "", query: "vr" }))).toEqual(["VRTX"]);
    expect(tickers(filterRows(rows, { sector: "", industry: "", query: "PHARMA" }))).toEqual(["VRTX"]);
    expect(tickers(filterRows(rows, { sector: "", industry: "", query: "nestle" }))).toEqual(["NESN"]);
    expect(filterRows(rows, { sector: "", industry: "", query: "rtx" })).toHaveLength(0);
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

describe("industriesFor", () => {
  const sectors = { Healthcare: ["Biotechnology", "Medical Devices"], Technology: ["Software", "Biotechnology"] };
  it("returns the sector's industries or a de-duplicated sorted list", () => {
    expect(industriesFor(sectors, "Healthcare")).toEqual(["Biotechnology", "Medical Devices"]);
    expect(industriesFor(sectors, "")).toEqual(["Biotechnology", "Medical Devices", "Software"]);
    expect(industriesFor(sectors, "Energy")).toEqual([]);
  });
});

describe("URL state", () => {
  it("round-trips a view", () => {
    const v = { sector: "Healthcare", industry: "Biotechnology", query: "al", sort: "ttmGrowth" as const, dir: "asc" as const, page: 2 };
    expect(readViewFromSearch(viewToSearch(v))).toEqual(v);
  });

  it("omits defaults and rejects invalid values", () => {
    expect(viewToSearch(DEFAULT_VIEW)).toBe("");
    expect(readViewFromSearch("?sort=name&dir=up&page=-4")).toEqual(DEFAULT_VIEW);
  });
});
