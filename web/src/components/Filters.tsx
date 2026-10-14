import { useEffect, useState } from "react";
import { formatCount } from "../lib/format";
import type { ViewState } from "../lib/screener";

interface Props {
  sectors: string[];
  industries: string[];
  view: ViewState;
  disabled: boolean;
  resultCount: number;
  totalCount: number;
  onChange: (patch: Partial<ViewState>) => void;
  onReset: () => void;
}

export function Filters({ sectors, industries, view, disabled, resultCount, totalCount, onChange, onReset }: Props) {
  const [query, setQuery] = useState(view.query);

  useEffect(() => setQuery(view.query), [view.query]);

  useEffect(() => {
    if (query === view.query) return;
    const t = window.setTimeout(() => onChange({ query }), 150);
    return () => window.clearTimeout(t);
  }, [query, view.query, onChange]);

  const active = Boolean(view.sector || view.industry || view.query);

  return (
    <section className="panel filters" aria-label="Filters">
      <div className="field">
        <label htmlFor="sector">Sector</label>
        <select
          id="sector"
          value={view.sector}
          disabled={disabled}
          onChange={(e) => onChange({ sector: e.target.value, industry: "" })}
        >
          <option value="">All sectors</option>
          {sectors.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </div>
      <div className="field">
        <label htmlFor="industry">Industry</label>
        <select
          id="industry"
          value={view.industry}
          disabled={disabled}
          onChange={(e) => onChange({ industry: e.target.value })}
        >
          <option value="">{view.sector ? `All ${view.sector} industries` : "All industries"}</option>
          {industries.map((i) => (
            <option key={i} value={i}>
              {i}
            </option>
          ))}
        </select>
      </div>
      <div className="field field-search">
        <label htmlFor="search">Search</label>
        <input
          id="search"
          type="search"
          placeholder="Ticker or company name"
          value={query}
          disabled={disabled}
          autoComplete="off"
          spellCheck={false}
          onChange={(e) => setQuery(e.target.value)}
        />
      </div>
      <div className="filters-meta">
        <span className="result-count" aria-live="polite">
          {disabled ? "Loading…" : `${formatCount(resultCount)} of ${formatCount(totalCount)} companies`}
        </span>
        {active && (
          <button type="button" className="btn btn-link" onClick={onReset}>
            Clear filters
          </button>
        )}
      </div>
    </section>
  );
}
