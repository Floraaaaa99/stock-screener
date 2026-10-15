import { describe, expect, it } from "vitest";
import {
  addSelectedToMembership,
  deselectFiltered,
  headerCheckState,
  issuerIdFor,
  issuerIdForTicker,
  isTickerSaved,
  normalizeCik,
  removeIssuer,
  restrictSelectionToCurrentList,
  selectFiltered,
  selectedAlreadySavedCount,
  toggleFilteredSelection,
  toggleTicker,
  type Layer3CatalogRow,
  type Layer3Entry,
} from "./layer3";
import {
  LAYER3_MEMBERSHIP_KEY,
  LAYER3_SCHEMA_VERSION,
  LAYER3_SELECTION_KEY,
  Layer3Store,
  createMemoryStore,
} from "./layer3Storage";
import { filterRows } from "./screener";
import { filterLayer2, layer2ToSearch, readLayer2View } from "./layer2";
import type { Layer2Row, ScreenerRow } from "../types";

function catalog(ticker: string, patch: Partial<Layer3CatalogRow> = {}): Layer3CatalogRow {
  return {
    ticker,
    name: `${ticker} Inc.`,
    exchange: "NYSE",
    sicIndustry: "3724 — Aircraft Engines & Engine Parts",
    sicMajorGroup: "Transportation Equipment",
    ...patch,
  };
}

function screener(ticker: string, patch: Partial<ScreenerRow> = {}): ScreenerRow {
  return {
    ticker,
    name: `${ticker} Inc.`,
    exchange: "NASDAQ",
    type: "common",
    sicCode: "2836",
    sicMajorGroup: "Chemicals and Allied Products",
    sicIndustry: "2836 — Biological Products",
    revenueCurrency: "USD",
    ttmCurrent: 10,
    ttmPrevious: 8,
    ttmGrowth: 25,
    naReason: null,
    latestQuarter: null,
    latestQuarterEnd: null,
    quartersAvailable: 8,
    ...patch,
  };
}

function layer2(ticker: string, patch: Partial<Layer2Row> = {}): Layer2Row {
  return {
    ticker,
    name: `${ticker} Inc`,
    exchange: "NASDAQ",
    type: "common",
    sicCode: "3724",
    sicMajorGroup: "Transportation Equipment",
    sicIndustry: "3724 — Aircraft Engines",
    revenueCurrency: "USD",
    revenueConcept: "RevenueFromContractWithCustomerExcludingAssessedTax",
    layer1SchemaVersion: 2,
    ttmGrowth: 10,
    ttmReason: null,
    bucket: "passed",
    dataReviewReasons: [],
    yoy: [],
    qoq: [],
    badges: [],
    appliedCategories: [],
    freshness: { status: "current", asOf: null, window: "verified_historical", latestVerified: null, expectedNext: null, message: null },
    rulesVersion: 3,
    ...patch,
  };
}

describe("issuer identity", () => {
  it("normalizes CIK to 10 digits and ignores punctuation", () => {
    expect(normalizeCik("46619")).toBe("0000046619");
    expect(normalizeCik("0000046619")).toBe("0000046619");
    expect(normalizeCik("CIK 0000046619")).toBe("0000046619");
    expect(normalizeCik(null)).toBeNull();
    expect(normalizeCik("")).toBeNull();
  });

  it("uses CIK as issuer id and falls back to ticker", () => {
    expect(issuerIdFor("HEI", "0000046619")).toBe("cik:0000046619");
    expect(issuerIdFor("HEI-A", "46619")).toBe("cik:0000046619");
    expect(issuerIdFor("FOO", null)).toBe("ticker:FOO");
    expect(issuerIdFor("foo", undefined)).toBe("ticker:FOO");
  });

  it("treats HEI and HEI-A as one issuer when CIK is known", () => {
    const cikByTicker = { HEI: "0000046619", "HEI-A": "0000046619" };
    expect(issuerIdForTicker("HEI", cikByTicker)).toBe(issuerIdForTicker("HEI-A", cikByTicker));
  });
});

describe("filtered select-all", () => {
  const page1 = ["AAA", "BBB"];
  const page2 = ["CCC", "DDD"];
  const filtered = [...page1, ...page2];

  it("selects every currently filtered ticker, including other pages", () => {
    const next = selectFiltered(new Set(), filtered);
    expect([...next].sort()).toEqual(["AAA", "BBB", "CCC", "DDD"]);
  });

  it("replaces leftover tickers so select-all is only the current list", () => {
    const next = selectFiltered(new Set(["ZZZ", "OLD"]), filtered);
    expect(next.has("ZZZ")).toBe(false);
    expect([...next].sort()).toEqual(["AAA", "BBB", "CCC", "DDD"]);
  });

  it("drops companies that leave the list after a tighter filter", () => {
    const selectedAll = selectFiltered(new Set(), ["A", "B", "C", "D", "E"]);
    const afterIndustry = restrictSelectionToCurrentList(selectedAll, ["A", "B", "C"]);
    expect([...afterIndustry].sort()).toEqual(["A", "B", "C"]);
  });

  it("does not add unfiltered tickers on select-all", () => {
    const next = selectFiltered(new Set(), page1);
    expect(next.has("CCC")).toBe(false);
    expect(next.has("HIDDEN")).toBe(false);
    expect([...next]).toEqual(["AAA", "BBB"]);
  });

  it("deselects only currently filtered tickers", () => {
    const selected = new Set(["AAA", "BBB", "CCC", "KEEP"]);
    const next = deselectFiltered(selected, page1);
    expect([...next].sort()).toEqual(["CCC", "KEEP"]);
  });

  it("reports none / some / all against the filtered set, not the universe", () => {
    expect(headerCheckState(new Set(), filtered)).toBe("none");
    expect(headerCheckState(new Set(["AAA", "BBB"]), filtered)).toBe("some");
    expect(headerCheckState(new Set(filtered), filtered)).toBe("all");
    expect(headerCheckState(new Set(["OUTSIDER"]), filtered)).toBe("none");
    expect(headerCheckState(new Set([...filtered, "OUTSIDER"]), filtered)).toBe("all");
  });

  it("toggles select-all from some to all, then back to none of the filtered set", () => {
    const some = toggleFilteredSelection(new Set(["AAA"]), filtered);
    expect(headerCheckState(some, filtered)).toBe("all");
    const none = toggleFilteredSelection(some, filtered);
    expect(headerCheckState(none, filtered)).toBe("none");
    expect(none.has("AAA")).toBe(false);
  });

  it("toggles a single ticker without affecting others", () => {
    const on = toggleTicker(new Set(["AAA"]), "BBB", true);
    expect([...on].sort()).toEqual(["AAA", "BBB"]);
    const off = toggleTicker(on, "AAA", false);
    expect([...off]).toEqual(["BBB"]);
  });
});

describe("membership add/remove", () => {
  const cikByTicker = { HEI: "0000046619", "HEI-A": "0000046619", LOAR: "0001951089", NEG: null };
  const rows = [catalog("HEI"), catalog("HEI-A"), catalog("LOAR", { name: "Loar Holdings" }), catalog("NEG")];

  it("adds selected issuers and is idempotent", () => {
    const first = addSelectedToMembership([], ["LOAR", "NEG"], cikByTicker, rows, "2026-10-15T00:00:00.000Z");
    expect(first.result).toEqual({ added: 2, alreadySaved: 0, issuerIds: ["cik:0001951089", "ticker:NEG"] });
    expect(first.entries.map((e) => e.issuerId)).toEqual(["cik:0001951089", "ticker:NEG"]);
    expect(first.entries[0]?.analysisStatus).toBe("pending_implementation");

    const again = addSelectedToMembership(first.entries, ["LOAR"], cikByTicker, rows, "2026-10-16T00:00:00.000Z");
    expect(again.result).toEqual({ added: 0, alreadySaved: 1, issuerIds: [] });
    expect(again.entries).toHaveLength(2);
    expect(again.entries[0]?.addedAt).toBe("2026-10-15T00:00:00.000Z");
    expect(again.entries[0]?.name).toBe("Loar Holdings");
  });

  it("does not create a second issuer record for a share class of an already-saved company", () => {
    const first = addSelectedToMembership([], ["HEI"], cikByTicker, rows, "2026-10-15T00:00:00.000Z");
    const second = addSelectedToMembership(first.entries, ["HEI-A"], cikByTicker, rows, "2026-10-16T00:00:00.000Z");
    expect(second.entries).toHaveLength(1);
    expect(second.result.alreadySaved).toBe(1);
    expect(second.entries[0]?.tickers).toEqual(["HEI", "HEI-A"]);
    expect(second.entries[0]?.displayTicker).toBe("HEI");
    expect(second.entries[0]?.addedAt).toBe("2026-10-15T00:00:00.000Z");
  });

  it("collapses HEI and HEI-A into one issuer when added together", () => {
    const { entries, result } = addSelectedToMembership([], ["HEI", "HEI-A"], cikByTicker, rows);
    expect(result.added).toBe(1);
    expect(entries).toHaveLength(1);
    expect(entries[0]?.tickers).toEqual(["HEI", "HEI-A"]);
  });

  it("does not block negative NI, declining revenue, or missing data", () => {
    const { entries } = addSelectedToMembership(
      [],
      ["NEG"],
      cikByTicker,
      [catalog("NEG", { name: "Loss Co", sicIndustry: null })],
    );
    expect(entries).toHaveLength(1);
    expect(entries[0]?.issuerId).toBe("ticker:NEG");
  });

  it("removes one issuer without touching the others", () => {
    const { entries } = addSelectedToMembership([], ["HEI", "LOAR"], cikByTicker, rows);
    const next = removeIssuer(entries, issuerIdFor("HEI", "0000046619"));
    expect(next.map((e) => e.displayTicker)).toEqual(["LOAR"]);
  });

  it("treats saved membership as distinct from the checkbox selection", () => {
    const { entries } = addSelectedToMembership([], ["HEI"], cikByTicker, rows);
    expect(isTickerSaved("HEI", entries, cikByTicker)).toBe(true);
    expect(isTickerSaved("HEI-A", entries, cikByTicker)).toBe(true);
    expect(isTickerSaved("LOAR", entries, cikByTicker)).toBe(false);
    expect(selectedAlreadySavedCount(["HEI", "HEI-A", "LOAR"], entries, cikByTicker)).toBe(1);
  });
});

describe("versioned localStorage", () => {
  it("round-trips selection and membership", () => {
    const store = new Layer3Store(createMemoryStore());
    expect(store.saveSelection(["HEI", "LOAR"])).toBe("ok");
    expect(store.loadSelection()).toEqual({ tickers: ["HEI", "LOAR"], status: "ok" });

    const entry: Layer3Entry = {
      issuerId: "cik:0000046619",
      cik: "0000046619",
      tickers: ["HEI"],
      displayTicker: "HEI",
      name: "Heico Corporation",
      exchange: "NYSE",
      sicIndustry: "3724 — Aircraft Engines & Engine Parts",
      sicMajorGroup: "Transportation Equipment",
      addedAt: "2026-10-15T00:00:00.000Z",
      analysisStatus: "pending_implementation",
    };
    expect(store.saveMembership([entry])).toBe("ok");
    expect(store.loadMembership()).toEqual({ entries: [entry], status: "ok" });
  });

  it("recovers from corrupt JSON and unknown shapes", () => {
    const kv = createMemoryStore({
      [LAYER3_SELECTION_KEY]: "{not json",
      [LAYER3_MEMBERSHIP_KEY]: JSON.stringify({ version: 1, data: { entries: [{ ticker: "nope" }] } }),
    });
    const store = new Layer3Store(kv);
    expect(store.loadSelection()).toEqual({ tickers: [], status: "recovered" });
    expect(store.loadMembership()).toEqual({ entries: [], status: "recovered" });
  });

  it("migrates a bare ticker array from an older payload", () => {
    const kv = createMemoryStore({
      [LAYER3_SELECTION_KEY]: JSON.stringify({ version: 0, data: ["AAA", "AAA", "BBB"] }),
    });
    const store = new Layer3Store(kv);
    expect(store.loadSelection()).toEqual({ tickers: ["AAA", "BBB"], status: "migrated" });
  });

  it("writes the current schema version", () => {
    const kv = createMemoryStore();
    const store = new Layer3Store(kv);
    store.saveSelection(["AAA"]);
    const raw = JSON.parse(kv.getItem(LAYER3_SELECTION_KEY) ?? "{}");
    expect(raw.version).toBe(LAYER3_SCHEMA_VERSION);
    expect(raw.data.tickers).toEqual(["AAA"]);
  });

  it("reports unavailable storage and keeps working without a backend", () => {
    const store = new Layer3Store(null);
    expect(store.loadSelection().status).toBe("unavailable");
    expect(store.saveMembership([])).toBe("unavailable");
  });

  it("treats write failures as unavailable", () => {
    const store = new Layer3Store({
      getItem: () => null,
      setItem: () => {
        throw new Error("quota");
      },
      removeItem: () => {},
    });
    expect(store.saveSelection(["AAA"])).toBe("unavailable");
  });
});

describe("Layer 1 / Layer 2 regressions", () => {
  it("does not change Layer 1 filter semantics", () => {
    const rows = [
      screener("AAA", { sicIndustry: "2836 — Biological Products", ttmGrowth: 10 }),
      screener("BBB", { sicIndustry: "3571 — Electronic Computers", ttmGrowth: 20 }),
    ];
    const filtered = filterRows(rows, {
      sicMajorGroup: "",
      sicIndustries: ["2836 — Biological Products"],
      currency: "",
      query: "",
    });
    expect(filtered.map((r) => r.ticker)).toEqual(["AAA"]);
  });

  it("does not change Layer 2 filter semantics", () => {
    const rows = [
      layer2("AAA", { bucket: "passed", appliedCategories: ["stable_sequential_growth"] }),
      layer2("BBB", { bucket: "watchlist", appliedCategories: [] }),
    ];
    expect(filterLayer2(rows, "passed", { sicMajorGroup: "", sicIndustries: [], query: "", categories: [], niProfitability: [], niImprovement: [] }).map((r) => r.ticker)).toEqual(["AAA"]);
    expect(filterLayer2(rows, "watchlist", { sicMajorGroup: "", sicIndustries: [], query: "", categories: [], niProfitability: [], niImprovement: [] }).map((r) => r.ticker)).toEqual(["BBB"]);
  });

  it("parses layer=3 without treating it as Layer 1 or Layer 2", () => {
    const parsed = readLayer2View("?layer=3");
    expect(parsed.layer).toBe(3);
    expect(layer2ToSearch(3, parsed.view, "?q=abc")).toBe("?layer=3");
  });

  it("still round-trips Layer 2 URLs", () => {
    const search = layer2ToSearch(
      2,
      {
        tab: "watchlist",
        sicMajorGroup: "Chemicals",
        sicIndustries: ["2834 — Pharma"],
        query: "inc",
        categories: ["qoq_volatility"],
        niProfitability: [],
        niImprovement: [],
        stableSpreadPp: 5,
        recentJumpPp: null,
        page: 2,
      },
      "",
    );
    const parsed = readLayer2View(search);
    expect(parsed.layer).toBe(2);
    expect(parsed.view.tab).toBe("watchlist");
    expect(parsed.view.sicIndustries).toEqual(["2834 — Pharma"]);
  });
});
