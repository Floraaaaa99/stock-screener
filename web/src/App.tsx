import { useCallback, useEffect, useMemo, useState } from "react";
import { loadMeta, loadScreener } from "./api";
import { CoveragePanel } from "./components/CoveragePanel";
import { Filters } from "./components/Filters";
import { Footer } from "./components/Footer";
import { Header } from "./components/Header";
import { Pagination } from "./components/Pagination";
import { ScreenerTable } from "./components/ScreenerTable";
import {
  DEFAULT_VIEW,
  filterRows,
  industriesFor,
  pageCount,
  paginate,
  readViewFromSearch,
  sortRows,
  type SortKey,
  type ViewState,
  viewToSearch,
} from "./lib/screener";
import type { Meta, ScreenerRow } from "./types";

type LoadState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; meta: Meta; rows: ScreenerRow[] };

export default function App() {
  const [load, setLoad] = useState<LoadState>({ status: "loading" });
  const [view, setView] = useState<ViewState>(() => readViewFromSearch(window.location.search));
  const [expanded, setExpanded] = useState<string | null>(null);

  const fetchData = useCallback(() => {
    setLoad({ status: "loading" });
    Promise.all([loadMeta(), loadScreener()])
      .then(([meta, screener]) => setLoad({ status: "ready", meta, rows: screener.rows }))
      .catch((err: unknown) => setLoad({ status: "error", message: err instanceof Error ? err.message : String(err) }));
  }, []);

  useEffect(fetchData, [fetchData]);

  useEffect(() => {
    const url = `${window.location.pathname}${viewToSearch(view)}`;
    window.history.replaceState(null, "", url);
  }, [view]);

  useEffect(() => {
    const onPop = () => setView(readViewFromSearch(window.location.search));
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  const rows = load.status === "ready" ? load.rows : [];
  const meta = load.status === "ready" ? load.meta : null;

  const filtered = useMemo(
    () => filterRows(rows, { sector: view.sector, industry: view.industry, query: view.query }),
    [rows, view.sector, view.industry, view.query],
  );
  const sorted = useMemo(() => sortRows(filtered, view.sort, view.dir, view.query), [filtered, view.sort, view.dir, view.query]);
  const pages = pageCount(sorted.length);
  const page = Math.min(view.page, pages);
  const pageRows = useMemo(() => paginate(sorted, page), [sorted, page]);

  const sectors = meta ? Object.keys(meta.sectors) : [];
  const industries = meta ? industriesFor(meta.sectors, view.sector) : [];

  const update = (patch: Partial<ViewState>) => {
    setExpanded(null);
    setView((v) => ({ ...v, page: 1, ...patch }));
  };

  const onSort = (key: SortKey) => {
    setView((v) => ({
      ...v,
      sort: key,
      dir: v.sort === key ? (v.dir === "desc" ? "asc" : "desc") : "desc",
      page: 1,
    }));
  };

  return (
    <div className="app">
      <Header meta={meta} />
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

        {load.status !== "error" && (
          <>
            <Filters
              sectors={sectors}
              industries={industries}
              view={view}
              disabled={load.status === "loading"}
              resultCount={sorted.length}
              totalCount={rows.length}
              onChange={update}
              onReset={() => update({ ...DEFAULT_VIEW })}
            />
            <ScreenerTable
              loading={load.status === "loading"}
              rows={pageRows}
              view={view}
              expanded={expanded}
              onToggle={(t) => setExpanded((cur) => (cur === t ? null : t))}
              onSort={onSort}
              onClearFilters={() => update({ sector: "", industry: "", query: "" })}
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
