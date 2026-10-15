import { useCallback, useEffect, useMemo, useState } from "react";
import { loadLayer2, loadMeta, loadScreener } from "./api";
import { CoveragePanel } from "./components/CoveragePanel";
import { Filters } from "./components/Filters";
import { Footer } from "./components/Footer";
import { Header } from "./components/Header";
import { Layer2View } from "./components/Layer2View";
import { Pagination } from "./components/Pagination";
import { ScreenerTable } from "./components/ScreenerTable";
import { layer2ToSearch, readLayer2View, type Layer2View as Layer2ViewState } from "./lib/layer2";
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

function parseLocation(search: string): { layer: 1 | 2; layer1: ViewState; layer2: Layer2ViewState } {
  const parsed = readLayer2View(search);
  return {
    layer: parsed.layer,
    layer1: readViewFromSearch(search),
    layer2: parsed.view,
  };
}

export default function App() {
  const initial = parseLocation(window.location.search);
  const [load, setLoad] = useState<LoadState>({ status: "loading" });
  const [layer, setLayer] = useState<1 | 2>(initial.layer);
  const [view, setView] = useState<ViewState>(initial.layer1);
  const [layer2View, setLayer2View] = useState<Layer2ViewState>(initial.layer2);
  const [expanded, setExpanded] = useState<string | null>(null);

  const fetchData = useCallback(() => {
    setLoad({ status: "loading" });
    Promise.all([loadMeta(), loadScreener(), loadLayer2().catch(() => null)])
      .then(([meta, screener, layer2]) => setLoad({ status: "ready", meta, rows: screener.rows, layer2 }))
      .catch((err: unknown) => setLoad({ status: "error", message: err instanceof Error ? err.message : String(err) }));
  }, []);

  useEffect(fetchData, [fetchData]);

  useEffect(() => {
    const url = `${window.location.pathname}${layer === 2 ? layer2ToSearch(2, layer2View, "") : viewToSearch(view)}`;
    window.history.replaceState(null, "", url);
  }, [layer, view, layer2View]);

  useEffect(() => {
    const onPop = () => {
      const next = parseLocation(window.location.search);
      setLayer(next.layer);
      setView(next.layer1);
      setLayer2View(next.layer2);
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

  const onLayer = (next: 1 | 2) => {
    setLayer(next);
    setExpanded(null);
  };

  const clearFilters = () => update({ sicMajorGroup: "", sicIndustries: [], currency: "", query: "" });

  return (
    <div className="app">
      <Header meta={meta} layer={layer} onLayer={onLayer} />
      <main className="container">
        {load.status === "error" && (
          <div className="panel error-panel" role="alert">
            <h2>Could not load the dataset</h2>
            <p>{load.message}</p>
            <button type="button" className="btn" onClick={fetchData}>
              Try again
            </button>
          </div>
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
                onChange={updateLayer2}
                onToggle={(t) => setExpanded((cur) => (cur === t ? null : t))}
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
            <ScreenerTable
              loading={load.status === "loading"}
              rows={pageRows}
              view={view}
              expanded={expanded}
              onToggle={(t) => setExpanded((cur) => (cur === t ? null : t))}
              onSort={onSort}
              onClearFilters={clearFilters}
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
