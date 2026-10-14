import { Fragment } from "react";
import { naReason } from "../lib/explain";
import { formatCompactMoney, formatPercent } from "../lib/format";
import type { SortKey, ViewState } from "../lib/screener";
import type { ScreenerRow } from "../types";
import { CompanyDetailPanel } from "./CompanyDetail";

interface Props {
  loading: boolean;
  rows: ScreenerRow[];
  view: ViewState;
  expanded: string | null;
  onToggle: (ticker: string) => void;
  onSort: (key: SortKey) => void;
  onClearFilters: () => void;
}

const COLUMNS = 8;

function SortHeader({ label, k, view, onSort, title }: { label: string; k: SortKey; view: ViewState; onSort: (k: SortKey) => void; title?: string }) {
  const active = view.sort === k;
  const aria = active ? (view.dir === "asc" ? "ascending" : "descending") : "none";
  return (
    <th className="num" aria-sort={aria} scope="col">
      <button type="button" className={`sort ${active ? "active" : ""}`} onClick={() => onSort(k)} title={title ?? `Sort by ${label}`}>
        {label}
        <span className="sort-icon" aria-hidden="true">
          {active ? (view.dir === "asc" ? "▲" : "▼") : "↕"}
        </span>
      </button>
    </th>
  );
}

function NA({ reason }: { reason: string | null }) {
  return (
    <span className="na" title={naReason(reason) || "Not available"}>
      N/A
    </span>
  );
}

function Growth({ row }: { row: ScreenerRow }) {
  if (row.ttmGrowth === null) return <NA reason={row.naReason} />;
  const cls = row.ttmGrowth > 0 ? "pos" : row.ttmGrowth < 0 ? "neg" : "";
  return <span className={`growth ${cls}`}>{formatPercent(row.ttmGrowth)}</span>;
}

function SicCell({ row, field }: { row: ScreenerRow; field: "sicMajorGroup" | "sicIndustry" }) {
  const value = row[field];
  if (!value) return <NA reason={row.sicCode ? null : "no_sic"} />;
  return (
    <span className="sic" title={row.sicCode ? `SEC SIC ${row.sicCode}` : "SEC SIC"}>
      {value}
    </span>
  );
}

export function ScreenerTable({ loading, rows, view, expanded, onToggle, onSort, onClearFilters }: Props) {
  return (
    <section className="panel table-panel">
      <div className="table-scroll">
        <table className="screener">
          <thead>
            <tr>
              <th scope="col">Ticker</th>
              <th scope="col">Company</th>
              <th scope="col">Exchange</th>
              <th scope="col">SEC SIC major group</th>
              <th scope="col">SEC SIC industry</th>
              <SortHeader label="Current TTM Revenue" k="ttmCurrent" view={view} onSort={onSort} title="Sum of the latest 4 quarters, in the reporting currency" />
              <SortHeader label="Previous TTM Revenue" k="ttmPrevious" view={view} onSort={onSort} title="Sum of the 4 quarters before those, in the reporting currency" />
              <SortHeader label="TTM Revenue Growth YoY" k="ttmGrowth" view={view} onSort={onSort} title="Current TTM ÷ Previous TTM − 1. Default sort: descending, N/A last." />
            </tr>
          </thead>
          <tbody>
            {loading &&
              Array.from({ length: 8 }, (_, i) => (
                <tr key={`sk-${i}`} className="skeleton-row" aria-hidden="true">
                  {Array.from({ length: COLUMNS }, (_, j) => (
                    <td key={j}>
                      <span className="skeleton" />
                    </td>
                  ))}
                </tr>
              ))}
            {!loading && rows.length === 0 && (
              <tr>
                <td colSpan={COLUMNS} className="empty">
                  <p>No companies match these filters.</p>
                  <button type="button" className="btn" onClick={onClearFilters}>
                    Clear filters
                  </button>
                </td>
              </tr>
            )}
            {!loading &&
              rows.map((r) => {
                const open = expanded === r.ticker;
                return (
                  <Fragment key={r.ticker}>
                    <tr className={`row ${open ? "open" : ""}`} onClick={() => onToggle(r.ticker)}>
                      <td className="ticker">
                        <button
                          type="button"
                          className="expand"
                          aria-expanded={open}
                          aria-controls={`detail-${r.ticker}`}
                          aria-label={`${open ? "Hide" : "Show"} quarterly revenue for ${r.ticker}`}
                          onClick={(e) => {
                            e.stopPropagation();
                            onToggle(r.ticker);
                          }}
                        >
                          <span className="chev" aria-hidden="true">
                            ▸
                          </span>
                          {r.ticker}
                        </button>
                      </td>
                      <td className="name" title={r.name}>
                        {r.name}
                        {r.type === "adr" && <span className="tag">ADR</span>}
                      </td>
                      <td>{r.exchange}</td>
                      <td>
                        <SicCell row={r} field="sicMajorGroup" />
                      </td>
                      <td>
                        <SicCell row={r} field="sicIndustry" />
                      </td>
                      <td className="num">
                        {r.ttmCurrent === null ? <NA reason={r.naReason} /> : formatCompactMoney(r.ttmCurrent, r.revenueCurrency)}
                      </td>
                      <td className="num">
                        {r.ttmPrevious === null ? <NA reason={r.naReason} /> : formatCompactMoney(r.ttmPrevious, r.revenueCurrency)}
                      </td>
                      <td className="num">
                        <Growth row={r} />
                      </td>
                    </tr>
                    {open && (
                      <tr className="detail-row" id={`detail-${r.ticker}`}>
                        <td colSpan={COLUMNS}>
                          <CompanyDetailPanel ticker={r.ticker} />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
