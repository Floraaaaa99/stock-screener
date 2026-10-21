import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { loadIssuers, loadLayer2, loadMeta, loadScreener } from "./api";
import { CoveragePanel } from "./components/CoveragePanel";
import { Filters } from "./components/Filters";
import { Footer } from "./components/Footer";
import { Header } from "./components/Header";
import { Layer2View } from "./components/Layer2View";
import { Layer3ResearchPage } from "./components/layer3/Layer3ResearchPage";
import { Layer3View } from "./components/Layer3View";
import { Pagination } from "./components/Pagination";
import { ScreenerTable } from "./components/ScreenerTable";
import { SelectionBar } from "./components/SelectionBar";
import { type Layer2View as Layer2ViewState, type LayerId, layer2ToSearch, readLayer2View } from "./lib/layer2";
import {
  addSelectedToMembership,
  headerCheckState,
  isTickerSaved,
  removeIssuer,
  sameTickerSet,
  syncSelectionToCurrentList,
  selectedAlreadySavedCount,
  toggleFilteredSelection,
  toggleTicker,
  type AddToLayer3Result,
  type Layer3CatalogRow,
  type Layer3Entry,
} from "./lib/layer3";
import { layer3ToSearch, readLayer3Cik } from "./lib/layer3Research";
import { Layer3Store, browserKvStore, storageBanner, type StorageStatus } from "./lib/layer3Storage";
import {
  DEFAULT_VIEW,
  filterRows,
  industriesFor,
  mixedCurrencies,
  pageCount,
  paginate,
  readViewFromSearch,
  sortRows,
  type SortKey,
  type ViewState,
  viewToSearch,
} from "./lib/screener";
import type { Layer2File, Meta, ScreenerRow } from "./types";

type LoadState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; meta: Meta; rows: ScreenerRow[]; layer2: Layer2File | null };

const layer3Store = new Layer3Store(browserKvStore());

function worstStorageStatus(...statuses: StorageStatus[]): StorageStatus {
  if (statuses.includes("unavailable")) return "unavailable";
  if (statuses.includes("recovered")) return "recovered";
  if (statuses.includes("migrated")) return "migrated";
  if (statuses.includes("ok")) return "ok";
  return "empty";
}

function parseLocation(search: string): {
  layer: LayerId;
  layer1: ViewState;
  layer2: Layer2ViewState;
  researchCik: string | null;
} {
  const parsed = readLayer2View(search);
  return {
    layer: parsed.layer,
    layer1: readViewFromSearch(search),
    layer2: parsed.view,
    researchCik: parsed.layer === 3 ? readLayer3Cik(search) : null,
  };
}

export default function App() {
  const initial = parseLocation(window.location.search);
  const initialLayer3 = layer3Store.loadSelection();
  const initialMembership = layer3Store.loadMembership();
  const [load, setLoad] = useState<LoadState>({ status: "loading" });
  const [layer, setLayer] = useState<LayerId>(initial.layer);
  const [researchCik, setResearchCik] = useState<string | null>(initial.researchCik);
  const [view, setView] = useState<ViewState>(initial.layer1);
  const [layer2View, setLayer2View] = useState<Layer2ViewState>(initial.layer2);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(() => new Set(initialLayer3.tickers));
  const [membership, setMembership] = useState<Layer3Entry[]>(() => initialMembership.entries);
  const [storageStatus, setStorageStatus] = useState<StorageStatus>(() =>
    worstStorageStatus(initialLayer3.status, initialMembership.status),
  );
  const [cikByTicker, setCikByTicker] = useState<Record<string, string | null>>({});
  const [lastAdd, setLastAdd] = useState<AddToLayer3Result | null>(null);

  const fetchData = useCallback(() => {
    setLoad({ status: "loading" });
    Promise.all([
      loadMeta(),
      loadScreener(),
      loadLayer2().catch(() => null),
      loadIssuers(),
    ])
      .then(([meta, screener, layer2, issuers]) => {
        setCikByTicker(issuers);
        setLoad({ status: "ready", meta, rows: screener.rows, layer2 });
      })
      .catch((err: unknown) => setLoad({ status: "error", message: err instanceof Error ? err.message : String(err) }));
  }, []);

  useEffect(fetchData, [fetchData]);

  useEffect(() => {
    const search =
      layer === 3 ? layer3ToSearch(researchCik) : layer === 2 ? layer2ToSearch(2, layer2View, "") : viewToSearch(view);
    window.history.replaceState(null, "", `${window.location.pathname}${search}`);
  }, [layer, view, layer2View, researchCik]);

  useEffect(() => {
    const onPop = () => {
      const next = parseLocation(window.location.search);
      setLayer(next.layer);
      setView(next.layer1);
      setLayer2View(next.layer2);
      setResearchCik(next.researchCik);
      setExpanded(null);
    };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  const rows = load.status === "ready" ? load.rows : [];
  const meta = load.status === "ready" ? load.meta : null;

  const filtered = useMemo(
    () =>
      filterRows(rows, {
        sicMajorGroup: view.sicMajorGroup,
        sicIndustries: view.sicIndustries,
        currency: view.currency,
        query: view.query,
      }),
    [rows, view.sicMajorGroup, view.sicIndustries, view.currency, view.query],
  );
  const sorted = useMemo(() => sortRows(filtered, view.sort, view.dir, view.query), [filtered, view.sort, view.dir, view.query]);
  const pages = pageCount(sorted.length);
  const page = Math.min(view.page, pages);
  const pageRows = useMemo(() => paginate(sorted, page), [sorted, page]);
  const mixed = useMemo(() => mixedCurrencies(filtered), [filtered]);
  const filteredTickers = useMemo(() => sorted.map((r) => r.ticker), [sorted]);
  const layer1HeaderState = headerCheckState(selected, filteredTickers);

  const catalog = useMemo<Layer3CatalogRow[]>(
    () =>
      rows.map((r) => ({
        ticker: r.ticker,
        name: r.name,
        exchange: r.exchange,
        sicIndustry: r.sicIndustry,
        sicMajorGroup: r.sicMajorGroup,
      })),
    [rows],
  );

  const savedTickers = useMemo(() => {
    const out = new Set<string>();
    for (const row of rows) {
      if (isTickerSaved(row.ticker, membership, cikByTicker)) out.add(row.ticker);
    }
    for (const entry of membership) {
      for (const ticker of entry.tickers) out.add(ticker);
    }
    return out;
  }, [rows, membership, cikByTicker]);

  const alreadySavedSelected = useMemo(
    () => selectedAlreadySavedCount([...selected], membership, cikByTicker),
    [selected, membership, cikByTicker],
  );
  const notice = storageBanner(storageStatus);

  const persistSelection = (next: Set<string>) => {
    setSelected(next);
    const status = layer3Store.saveSelection([...next]);
    if (status === "unavailable") setStorageStatus("unavailable");
  };

  const persistSynced = useCallback((previousTickers: string[], currentTickers: string[]) => {
    setSelected((prev) => {
      const next = syncSelectionToCurrentList(prev, previousTickers, currentTickers);
      if (sameTickerSet(prev, next)) return prev;
      const status = layer3Store.saveSelection([...next]);
      if (status === "unavailable") setStorageStatus("unavailable");
      return next;
    });
  }, []);

  const previousTickersRef = useRef<string[] | null>(null);
  useEffect(() => {
    if (layer !== 1 || load.status !== "ready" || rows.length === 0) return;
    const previous = previousTickersRef.current;
    previousTickersRef.current = filteredTickers;
    if (previous === null) return;
    persistSynced(previous, filteredTickers);
  }, [layer, load.status, rows.length, view.sicMajorGroup, view.sicIndustries, view.currency, view.query, filteredTickers, persistSynced]);

  const persistMembership = (next: Layer3Entry[]) => {
    setMembership(next);
    const status = layer3Store.saveMembership(next);
    if (status === "unavailable") setStorageStatus("unavailable");
  };

  const majorGroups = meta ? Object.keys(meta.sicMajorGroups) : [];
  const industries = meta ? industriesFor(meta.sicMajorGroups, view.sicMajorGroup) : [];
  const currencies = meta?.currencies ?? [];

  const update = (patch: Partial<ViewState>) => {
    setExpanded(null);
    setView((v) => ({ ...v, page: 1, ...patch }));
  };

  const updateLayer2 = (patch: Partial<Layer2ViewState>) => {
    setExpanded(null);
    setLayer2View((v) => ({ ...v, page: 1, ...patch }));
  };

  const onSort = (key: SortKey) => {
    setView((v) => ({
      ...v,
      sort: key,
      dir: v.sort === key ? (v.dir === "desc" ? "asc" : "desc") : "desc",
      page: 1,
    }));
  };

  const onLayer = (next: LayerId) => {
    setLayer(next);
    setExpanded(null);
    setResearchCik(null);
  };

  const clearFilters = () => update({ sicMajorGroup: "", sicIndustries: [], currency: "", query: "" });

  const onToggleSelect = (ticker: string, checked: boolean) => {
    persistSelection(toggleTicker(selected, ticker, checked));
  };

  const onToggleFiltered = (tickers: string[]) => {
    persistSelection(toggleFilteredSelection(selected, tickers));
  };

  const onAddToLayer3 = () => {
    const { entries, result } = addSelectedToMembership(membership, [...selected], cikByTicker, catalog);
    persistMembership(entries);
    setLastAdd(result);
  };

  const selectionBar = (
    <SelectionBar
      selectedCount={selected.size}
      alreadySavedCount={alreadySavedSelected}
      filteredCount={filteredTickers.length}
      lastResult={lastAdd}
      storageNotice={notice}
      onClear={() => persistSelection(new Set())}
      onAdd={onAddToLayer3}
      onOpenLayer3={() => onLayer(3)}
    />
  );

  return (
    <div className="app">
      <Header
        meta={meta}
        layer={layer}
        layer3Count={membership.length}
        onLayer={onLayer}
        researchOpen={layer === 3 && researchCik != null}
      />
      <main className={layer === 3 && researchCik != null ? "container is-research" : "container"}>
        {load.status === "error" && (
          <div className="panel error-panel" role="alert">
            <h2>Could not load the dataset</h2>
            <p>{load.message}</p>
            <button type="button" className="btn" onClick={fetchData}>
              Try again
            </button>
          </div>
        )}

        {load.status !== "error" && layer === 3 && researchCik && (
          <Layer3ResearchPage
            cik={researchCik}
            entries={membership}
            onBack={() => setResearchCik(null)}
            onRemove={(issuerId) => {
              persistMembership(removeIssuer(membership, issuerId));
              setResearchCik(null);
            }}
          />
        )}

        {load.status !== "error" && layer === 3 && !researchCik && (
          <Layer3View
            entries={membership}
            storageNotice={notice}
            onRemove={(issuerId) => persistMembership(removeIssuer(membership, issuerId))}
            onOpenScreener={() => onLayer(1)}
            onOpenResearch={(cik) => setResearchCik(cik)}
          />
        )}

        {load.status !== "error" && layer === 2 && (
          <>
            {load.status === "ready" && !load.layer2 && (
              <div className="panel error-panel" role="alert">
                <h2>Sequential growth dataset is not available</h2>
                <p>Layer 2 is built from Layer 1’s validated company JSON after the TTM dataset is written.</p>
                <button type="button" className="btn" onClick={fetchData}>
                  Try again
                </button>
              </div>
            )}
            {load.status === "ready" && load.layer2 && meta && (
              <Layer2View
                file={load.layer2}
                meta={meta}
                view={layer2View}
                expanded={expanded}
                selected={selected}
                savedTickers={savedTickers}
                onChange={updateLayer2}
                onToggle={(t) => setExpanded((cur) => (cur === t ? null : t))}
                onToggleSelect={onToggleSelect}
                onToggleFiltered={onToggleFiltered}
                onSyncSelection={persistSynced}
                selectedCount={selected.size}
                alreadySavedCount={alreadySavedSelected}
                lastAdd={lastAdd}
                storageNotice={notice}
                onClearSelection={() => persistSelection(new Set())}
                onAddToLayer3={onAddToLayer3}
                onOpenLayer3={() => onLayer(3)}
              />
            )}
            {load.status === "loading" && (
              <div className="panel table-panel" role="status">
                <p className="detail-loading">
                  <span className="spinner" aria-hidden="true" /> Loading sequential growth…
                </p>
              </div>
            )}
          </>
        )}

        {load.status !== "error" && layer === 1 && (
          <>
            <Filters
              majorGroups={majorGroups}
              industries={industries}
              currencies={currencies}
              view={view}
              disabled={load.status === "loading"}
              resultCount={sorted.length}
              totalCount={rows.length}
              onChange={update}
              onReset={() => update({ ...DEFAULT_VIEW })}
            />
            {mixed && (
              <div className="currency-banner" role="note">
                Revenue is shown in each company's SEC reporting currency, labeled on every amount. Amounts are
                <strong> not converted</strong>. Sorting Current or Previous TTM groups currencies (USD first) so
                figures in different currencies are never ranked as one series. TTM growth is a ratio and can be
                compared across currencies.
              </div>
            )}
            {selectionBar}
            <ScreenerTable
              loading={load.status === "loading"}
              rows={pageRows}
              view={view}
              expanded={expanded}
              selected={selected}
              savedTickers={savedTickers}
              headerState={layer1HeaderState}
              filteredCount={filteredTickers.length}
              onToggle={(t) => setExpanded((cur) => (cur === t ? null : t))}
              onSort={onSort}
              onClearFilters={clearFilters}
              onToggleSelect={onToggleSelect}
              onToggleFiltered={() => onToggleFiltered(filteredTickers)}
            />
            {load.status === "ready" && sorted.length > 0 && (
              <Pagination
                page={page}
                pages={pages}
                total={sorted.length}
                onPage={(p) => {
                  setExpanded(null);
                  setView((v) => ({ ...v, page: p }));
                  window.scrollTo({ top: 0, behavior: "smooth" });
                }}
              />
            )}
            {meta && <CoveragePanel meta={meta} />}
          </>
        )}
      </main>
      <Footer meta={meta} />
    </div>
  );
}
