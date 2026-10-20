import { describe, expect, it } from "vitest";
import {
  addSelectedToMembership,
  deselectFiltered,
  displayStatus,
  headerCheckState,
  ciksForEntries,
  indexLayer3,
  layer3IssuerFile,
  LAYER3_INPUT_DETAIL,
  LAYER3_INPUT_LABEL,
  issuerIdFor,
  issuerIdForTicker,
  isTickerSaved,
  metricsForEntry,
  metricValue,
  migrateLegacyIssuerEntry,
  migrateLegacyMembership,
  normalizeCik,
  removeIssuer,
  restrictSelectionToCurrentList,
  selectFiltered,
  syncSelectionToCurrentList,
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
    expect(normalizeCik("0000000000")).toBeNull();
    expect(normalizeCik("0")).toBeNull();
  });

  it("does not treat the invalid zero CIK as an issuer id", () => {
    expect(issuerIdFor("ZSTK", "0000000000")).toBe("ticker:ZSTK");
    expect(layer3IssuerFile("0000000000")).toBe("layer3/cik/invalid.json");
  });

  it("rewrites a saved ZSTK zero-CIK membership entry to 0001790169", () => {
    const legacy: Layer3Entry = {
      issuerId: "cik:0000000000",
      cik: "0000000000",
      tickers: ["ZSTK"],
      displayTicker: "ZSTK",
      name: "ZeroStack Corp.",
      exchange: "NASDAQ",
      sicIndustry: "6199 — Finance Services",
      sicMajorGroup: "Non-depository Credit Institutions",
      addedAt: "2026-10-16T00:00:00.000Z",
      analysisStatus: "pending_implementation",
    };
    expect(migrateLegacyIssuerEntry(legacy)).toEqual({
      ...legacy,
      issuerId: "cik:0001790169",
      cik: "0001790169",
    });
    const other: Layer3Entry = { ...legacy, tickers: ["JHI"], displayTicker: "JHI", name: "JHI" };
    expect(migrateLegacyIssuerEntry(other)).toEqual(other);
    const merged = migrateLegacyMembership([
      legacy,
      { ...legacy, issuerId: "cik:0001790169", cik: "0001790169" },
    ]);
    expect(merged.migrated).toBe(true);
    expect(merged.entries).toHaveLength(1);
    expect(merged.entries[0]?.issuerId).toBe("cik:0001790169");
    expect(isTickerSaved("ZSTK", merged.entries, { ZSTK: "0001790169" })).toBe(true);
    expect(ciksForEntries(merged.entries)).toEqual(["0001790169"]);
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

  it("keeps select-all when adding a category grows the list", () => {
    const previous = ["A", "B", "C"];
    const selected = selectFiltered(new Set(), previous);
    const next = syncSelectionToCurrentList(selected, previous, ["A", "B", "C", "D", "E"]);
    expect([...next].sort()).toEqual(["A", "B", "C", "D", "E"]);
  });

  it("does not auto-select newcomers when only some rows were checked", () => {
    const previous = ["A", "B", "C"];
    const next = syncSelectionToCurrentList(new Set(["A", "B"]), previous, ["A", "B", "C", "D"]);
    expect([...next].sort()).toEqual(["A", "B"]);
  });

  it("keeps select-all when tightening and then widening the list", () => {
    const all20 = ["A", "B", "C", "D", "E"];
    const selected20 = selectFiltered(new Set(), all20);
    const afterCut = syncSelectionToCurrentList(selected20, all20, ["A", "B", "C"]);
    expect([...afterCut].sort()).toEqual(["A", "B", "C"]);
    const afterAdd = syncSelectionToCurrentList(afterCut, ["A", "B", "C"], all20);
    expect([...afterAdd].sort()).toEqual(all20);
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

  it("migrates a saved ZSTK zero-CIK membership entry and persists it", () => {
    const kv = createMemoryStore({
      [LAYER3_MEMBERSHIP_KEY]: JSON.stringify({
        version: 1,
        data: {
          entries: [
            {
              issuerId: "cik:0000000000",
              cik: "0000000000",
              tickers: ["ZSTK"],
              displayTicker: "ZSTK",
              name: "ZeroStack Corp.",
              exchange: "NASDAQ",
              sicIndustry: null,
              sicMajorGroup: null,
              addedAt: "2026-10-16T00:00:00.000Z",
              analysisStatus: "pending_implementation",
            },
          ],
        },
      }),
    });
    const store = new Layer3Store(kv);
    const loaded = store.loadMembership();
    expect(loaded.status).toBe("migrated");
    expect(loaded.entries).toEqual([
      expect.objectContaining({ issuerId: "cik:0001790169", cik: "0001790169", displayTicker: "ZSTK" }),
    ]);
    const persisted = JSON.parse(kv.getItem(LAYER3_MEMBERSHIP_KEY) ?? "{}");
    expect(persisted.data.entries[0].issuerId).toBe("cik:0001790169");
    expect(store.loadMembership()).toEqual({ entries: loaded.entries, status: "ok" });
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
    expect(layer2ToSearch(3, parsed.view, "?q=abc")).not.toContain("cik=");
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

describe("Phase 2 metric catalog (saved issuers only)", () => {
  const heiRow = {
    cik: "0000046619",
    tickers: ["HEI", "HEI-A"],
    displayTicker: "HEI",
    name: "HEICO Corporation",
    exchange: "NYSE",
    sicCode: "3724",
    sicIndustry: "3724 — Aircraft Engines",
    sicMajorGroup: "Transportation Equipment",
    extractionStatus: "extracted" as const,
    verificationStatus: "company_facts_only" as const,
    modelApplicability: "applicable" as const,
    scoringStatus: "not_implemented" as const,
    inputCompleteness: "ready" as const,
    status: "extracted" as const,
    currency: "USD",
    flags: [],
    extractionVersion: 1,
    growthSource: "not_yet_verified",
    scoring: null,
    layer1: {
      revenueTtm: 1,
      revenuePriorTtm: 1,
      revenueTtmGrowth: 0,
      revenueReason: null,
      revenueCurrency: "USD",
      earningsConcept: null,
      earningsStatus: null,
      source: "layer1_copy",
    },
    metrics: {
      ocf: { status: "extracted", reason: null, ttm: 100, previousTtm: 80, verification: "company_facts_only" },
      capex: { status: "extracted", reason: null, ttm: 20, previousTtm: 10, verification: "company_facts_only" },
      fcf: { status: "extracted", reason: null, ttm: 80, previousTtm: 70, verification: "derived" },
      operatingIncome: { status: "extracted", reason: null, ttm: 50, verification: "company_facts_only" },
      interestExpense: { status: "missing", reason: "no_concept", ttm: null, verification: "not_checked" },
      ebitda: { status: "missing", reason: "missing_depreciation_amortization", ttm: null, verification: "not_checked" },
      cash: { status: "extracted", reason: null, value: 25, verification: "company_facts_only" },
      shortTermDebt: { status: "missing", reason: "no_concept", value: null, verification: "not_checked" },
      longTermDebt: { status: "missing", reason: "no_concept", value: null, verification: "not_checked" },
      totalDebt: { status: "missing", reason: "missing_short_term_debt", value: null, verification: "not_checked" },
      netDebt: { status: "missing", reason: "missing_short_term_debt", value: null, verification: "not_checked" },
      noInterestBurden: false,
      growthSource: "not_yet_verified",
    },
  };

  it("shares one extracted row across HEI / HEI-A and ignores unsaved tickers", () => {
    const index = indexLayer3({
      schemaVersion: 1,
      extractionVersion: 1,
      generatedAt: "2026-10-16T00:00:00Z",
      cutoffNote: "test",
      scoring: null,
      counts: {
        issuers: 1,
        extracted: 1,
        pendingDataVerification: 0,
        pendingAnalysis: 0,
        modelNotApplicable: 0,
      },
      rows: [heiRow],
    });
    const hei: Layer3Entry = {
      issuerId: "cik:0000046619",
      cik: "0000046619",
      tickers: ["HEI", "HEI-A"],
      displayTicker: "HEI",
      name: "HEICO Corporation",
      exchange: "NYSE",
      sicIndustry: "3724 — Aircraft Engines",
      sicMajorGroup: "Transportation Equipment",
      addedAt: "2026-10-15T00:00:00.000Z",
      analysisStatus: "pending_implementation",
    };
    const loar: Layer3Entry = {
      ...hei,
      issuerId: "ticker:LOAR",
      cik: null,
      tickers: ["LOAR"],
      displayTicker: "LOAR",
      name: "Loar",
    };
    expect(metricsForEntry(hei, index)?.cik).toBe("0000046619");
    expect(metricsForEntry({ ...hei, tickers: ["HEI-A"], displayTicker: "HEI-A" }, index)?.metrics?.fcf.ttm).toBe(80);
    expect(metricsForEntry(loar, index)).toBeNull();
    expect(displayStatus(hei, metricsForEntry(hei, index), true)).toBe("extracted");
    expect(metricsForEntry(hei, index)?.verificationStatus).toBe("company_facts_only");
    expect(metricsForEntry(hei, index)?.scoringStatus).toBe("not_implemented");
    expect(displayStatus(loar, null, true)).toBe("pending_analysis");
    expect(displayStatus(loar, null, false)).toBe("pending_implementation");
    expect(metricValue({ ttm: null })).toBeNull();
    expect(metricValue({ value: null })).toBeNull();
    expect(metricValue({ ttm: 0 })).toBe(0);
    expect(metricValue({ value: 0 })).toBe(0);
  });

  it("addresses issuer metrics by CIK path and only lists saved CIKs", () => {
    expect(layer3IssuerFile("46619")).toBe("layer3/cik/0000046619.json");
    expect(ciksForEntries([
      {
        issuerId: "cik:0000046619",
        cik: "0000046619",
        tickers: ["HEI", "HEI-A"],
        displayTicker: "HEI",
        name: "HEICO",
        exchange: "NYSE",
        sicIndustry: null,
        sicMajorGroup: null,
        addedAt: "2026-10-16T00:00:00.000Z",
        analysisStatus: "pending_implementation",
      },
      {
        issuerId: "ticker:LOAR",
        cik: null,
        tickers: ["LOAR"],
        displayTicker: "LOAR",
        name: "Loar",
        exchange: "NYSE",
        sicIndustry: null,
        sicMajorGroup: null,
        addedAt: "2026-10-16T00:00:00.000Z",
        analysisStatus: "pending_implementation",
      },
    ])).toEqual(["0000046619"]);
    expect(LAYER3_INPUT_LABEL.ready).toMatch(/Phase 2 core inputs/);
    expect(LAYER3_INPUT_DETAIL.ready).toMatch(/not a complete 100-point scoring/);
    expect(LAYER3_INPUT_DETAIL.ready).toMatch(/not a statement-verification/);
  });
});
