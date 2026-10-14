import { useEffect, useState } from "react";
import { formatCount } from "../lib/format";
import type { ViewState } from "../lib/screener";

interface Props {
  majorGroups: string[];
  industries: string[];
  currencies: string[];
  view: ViewState;
  disabled: boolean;
  resultCount: number;
  totalCount: number;
  onChange: (patch: Partial<ViewState>) => void;
  onReset: () => void;
}

export function Filters({
  majorGroups,
  industries,
  currencies,
  view,
  disabled,
  resultCount,
  totalCount,
  onChange,
  onReset,
}: Props) {
  const [query, setQuery] = useState(view.query);

  useEffect(() => setQuery(view.query), [view.query]);

  useEffect(() => {
    if (query === view.query) return;
    const t = window.setTimeout(() => onChange({ query }), 150);
    return () => window.clearTimeout(t);
  }, [query, view.query, onChange]);

  const active = Boolean(view.sicMajorGroup || view.sicIndustry || view.currency || view.query);

  return (
    <section className="panel filters" aria-label="Filters">
      <div className="field">
        <label htmlFor="sic-group">SEC SIC major group</label>
        <select
          id="sic-group"
          value={view.sicMajorGroup}
          disabled={disabled}
          onChange={(e) => onChange({ sicMajorGroup: e.target.value, sicIndustry: "" })}
        >
          <option value="">All SEC SIC major groups</option>
          {majorGroups.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </div>
      <div className="field">
        <label htmlFor="sic-industry">SEC SIC industry</label>
        <select
          id="sic-industry"
          value={view.sicIndustry}
          disabled={disabled}
          onChange={(e) => onChange({ sicIndustry: e.target.value })}
        >
          <option value="">{view.sicMajorGroup ? `All in ${view.sicMajorGroup}` : "All SEC SIC industries"}</option>
          {industries.map((i) => (
            <option key={i} value={i}>
              {i}
            </option>
          ))}
        </select>
      </div>
      {currencies.length > 0 && (
        <div className="field">
          <label htmlFor="currency">Revenue currency</label>
          <select id="currency" value={view.currency} disabled={disabled} onChange={(e) => onChange({ currency: e.target.value })}>
            <option value="">All currencies</option>
            {currencies.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </div>
      )}
      <div className="field field-search">
        <label htmlFor="search">Search</label>
        <input
          id="search"
          type="search"
          placeholder="Ticker, company, or SEC SIC"
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
