import { useCallback, useMemo } from "react";
import { formatCount } from "../lib/format";
import {
  CAT_JUMP,
  CAT_LABELS,
  CAT_STABLE,
  OBJECTIVE_CATS,
  THRESHOLD_CATS,
  TABS,
  countsFor,
  filterLayer2,
  tabHint,
  withLiveBadges,
  type Layer2View as View,
} from "../lib/layer2";
import { industriesFor, pageCount, paginate, type ViewState } from "../lib/screener";
import type { Layer2File, Meta } from "../types";
import { Filters } from "./Filters";
import { Layer2Table } from "./Layer2Table";
import { Pagination } from "./Pagination";

interface Props {
  file: Layer2File;
  meta: Meta;
  view: View;
  expanded: string | null;
  loading?: boolean;
  onChange: (patch: Partial<View>) => void;
  onToggle: (ticker: string) => void;
}

export function Layer2View({ file, meta, view, expanded, loading = false, onChange, onToggle }: Props) {
  const thresholds = { stableSpreadPp: view.stableSpreadPp, recentJumpPp: view.recentJumpPp };
  const rows = useMemo(() => file.rows.map((r) => withLiveBadges(r, thresholds)), [file.rows, view.stableSpreadPp, view.recentJumpPp]);
  const counts = useMemo(() => countsFor(rows), [rows]);
  const filtered = useMemo(
    () =>
      filterLayer2(rows, view.tab, {
        sicMajorGroup: view.sicMajorGroup,
        sicIndustry: view.sicIndustry,
        query: view.query,
        categories: view.categories,
      }),
    [rows, view],
  );
  const pages = pageCount(filtered.length);
  const page = Math.min(view.page, pages);
  const pageRows = useMemo(() => paginate(filtered, page), [filtered, page]);
  const majorGroups = Object.keys(meta.sicMajorGroups);
  const industries = industriesFor(meta.sicMajorGroups, view.sicMajorGroup);
  const catOptions = [...OBJECTIVE_CATS, ...THRESHOLD_CATS];

  const onFilterChange = useCallback(
    (patch: Partial<ViewState>) => {
      const next: Partial<View> = {};
      if (patch.sicMajorGroup !== undefined) next.sicMajorGroup = patch.sicMajorGroup;
      if (patch.sicIndustry !== undefined) next.sicIndustry = patch.sicIndustry;
      if (patch.query !== undefined) next.query = patch.query;
      onChange(next);
    },
    [onChange],
  );

  const toggleCat = (id: string) => {
    const next = view.categories.includes(id) ? view.categories.filter((c) => c !== id) : [...view.categories, id];
    onChange({ categories: next });
  };

  const catDisabled = (id: string) =>
    (id === CAT_STABLE && view.stableSpreadPp === null) || (id === CAT_JUMP && view.recentJumpPp === null);

  return (
    <>
      <p className="layer2-lead">
        Sequential growth (Layer 2) starts from Layer 1’s latest eight consecutive, comparable, filing-validated
        quarters (verified historical data, not a live EDGAR scan). Passed requires TTM revenue growth &gt; 0% and four
        strictly positive quarterly YoY rates (deceleration is allowed). Watchlist is the same data quality with at
        least one YoY ≤ 0%. Companies with valid TTM growth ≤ 0% are listed separately and are not Data Review. QoQ is
        descriptive and never removes a company. A freshness warning appears when the next fiscal quarter was past its
        typical filing window at the dataset as-of date. Rules v{file.rulesVersion}.
      </p>
      <div className="layer2-settings panel">
        <div className="field">
          <label htmlFor="spread">Stable QoQ spread (percentage points)</label>
          <input
            id="spread"
            type="number"
            step="any"
            placeholder="Threshold not configured"
            value={view.stableSpreadPp ?? ""}
            onChange={(e) => {
              const n = Number(e.target.value);
              onChange({ stableSpreadPp: e.target.value === "" || !Number.isFinite(n) ? null : n });
            }}
          />
        </div>
        <div className="field">
          <label htmlFor="jump">Recent QoQ jump (percentage points)</label>
          <input
            id="jump"
            type="number"
            step="any"
            placeholder="Threshold not configured"
            value={view.recentJumpPp ?? ""}
            onChange={(e) => {
              const n = Number(e.target.value);
              onChange({ recentJumpPp: e.target.value === "" || !Number.isFinite(n) ? null : n });
            }}
          />
        </div>
        <p className="muted settings-note">
          Stable sequential growth and Recent QoQ jump stay inactive until you enter thresholds. Other categories use
          objective rules immediately. Values are not converted across currencies.
        </p>
      </div>
      <Filters
        majorGroups={majorGroups}
        industries={industries}
        currencies={[]}
        view={{
          sicMajorGroup: view.sicMajorGroup,
          sicIndustry: view.sicIndustry,
          currency: "",
          query: view.query,
          sort: "ttmGrowth",
          dir: "desc",
          page: view.page,
        }}
        disabled={loading}
        resultCount={filtered.length}
        totalCount={counts[view.tab]}
        onChange={onFilterChange}
        onReset={() => onChange({ sicMajorGroup: "", sicIndustry: "", query: "", categories: [] })}
      />
      <div className="cat-filter" aria-label="QoQ category filter">
        <span className="k">Category (match any)</span>
        {catOptions.map((id) => (
          <label key={id} className={`cat-opt ${catDisabled(id) ? "disabled" : ""}`}>
            <input
              type="checkbox"
              checked={view.categories.includes(id)}
              disabled={loading || catDisabled(id)}
              onChange={() => toggleCat(id)}
            />
            {CAT_LABELS[id]}
            {catDisabled(id) && <span className="muted"> · Threshold not configured</span>}
          </label>
        ))}
      </div>
      <div className="tabs" role="tablist" aria-label="Layer 2 buckets">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            role="tab"
            aria-selected={view.tab === t.id}
            className={`tab ${view.tab === t.id ? "on" : ""}`}
            title={tabHint(t.id)}
            onClick={() => onChange({ tab: t.id })}
          >
            {t.label} <span className="tab-count">{formatCount(counts[t.id])}</span>
          </button>
        ))}
      </div>
      <p className="muted tab-hint">{tabHint(view.tab)}</p>
      <Layer2Table
        loading={loading}
        rows={pageRows}
        expanded={expanded}
        onToggle={onToggle}
        onClearFilters={() => onChange({ sicMajorGroup: "", sicIndustry: "", query: "", categories: [] })}
      />
      {!loading && filtered.length > 0 && (
        <Pagination
          page={page}
          pages={pages}
          total={filtered.length}
          onPage={(p) => {
            onChange({ page: p });
            window.scrollTo({ top: 0, behavior: "smooth" });
          }}
        />
      )}
    </>
  );
}
