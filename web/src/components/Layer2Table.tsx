import { Fragment } from "react";
import { naReason } from "../lib/explain";
import { formatPercent } from "../lib/format";
import type { Layer2Rate, Layer2Row } from "../types";
import { CategoryBadges } from "./CategoryBadges";
import { Layer2Detail } from "./Layer2Detail";
import { QoqChart } from "./QoqChart";

function Rates({ rows }: { rows: Layer2Rate[] }) {
  return (
    <span className="rate-stack">
      {rows.map((e) => (
        <span key={`${e.label}-${e.end}`} className={`rate-chip ${e.rate == null ? "na" : e.rate > 0 ? "pos" : e.rate < 0 ? "neg" : ""}`} title={`${e.label ?? ""} ending ${e.end ?? ""}: ${e.reason ? naReason(e.reason) : formatPercent(e.rate)}`}>
          <span className="rate-lab">{e.label ?? "—"}</span>
          {e.rate == null ? "N/A" : formatPercent(e.rate)}
        </span>
      ))}
    </span>
  );
}

export function Layer2Table({
  loading,
  rows,
  expanded,
  onToggle,
  onClearFilters,
}: {
  loading: boolean;
  rows: Layer2Row[];
  expanded: string | null;
  onToggle: (ticker: string) => void;
  onClearFilters: () => void;
}) {
  const cols = 8;
  return (
    <section className="panel table-panel">
      <div className="table-scroll">
        <table className="screener layer2-table">
          <thead>
            <tr>
              <th>Ticker</th>
              <th>Company</th>
              <th>SEC SIC industry</th>
              <th className="num">TTM Revenue Growth</th>
              <th title="Oldest to newest; fiscal labels and period-end dates">Latest four YoY</th>
              <th title="Oldest to newest; descriptive only">Latest four QoQ</th>
              <th>QoQ category</th>
              <th>QoQ trend</th>
            </tr>
          </thead>
          <tbody>
            {loading &&
              Array.from({ length: 6 }, (_, i) => (
                <tr key={i} className="skeleton-row">
                  {Array.from({ length: cols }, (_, j) => (
                    <td key={j}>
                      <span className="skeleton" />
                    </td>
                  ))}
                </tr>
              ))}
            {!loading && rows.length === 0 && (
              <tr>
                <td colSpan={cols} className="empty">
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
                        <button type="button" className="expand" aria-expanded={open} onClick={(e) => { e.stopPropagation(); onToggle(r.ticker); }}>
                          <span className="chev">▸</span>
                          {r.ticker}
                        </button>
                      </td>
                      <td className="name" title={r.name}>
                        {r.name}
                        {r.freshness?.status === "verified_lagging" && r.freshness.latestVerified && (
                          <div className="freshness-chip warn" title={r.freshness.message ?? ""}>
                            Verified through {r.freshness.latestVerified.label} · newer filing may exist
                          </div>
                        )}
                      </td>
                      <td className="sic">{r.sicIndustry ?? "N/A"}</td>
                      <td className="num">
                        {r.ttmGrowth == null ? <span className="na">N/A</span> : <span className={r.ttmGrowth > 0 ? "pos" : r.ttmGrowth < 0 ? "neg" : ""}>{formatPercent(r.ttmGrowth)}</span>}
                      </td>
                      <td>
                        <Rates rows={r.yoy} />
                      </td>
                      <td>
                        <Rates rows={r.qoq} />
                      </td>
                      <td>
                        <CategoryBadges badges={r.badges} />
                      </td>
                      <td>
                        <QoqChart rates={r.qoq} />
                      </td>
                    </tr>
                    {open && (
                      <tr className="detail-row">
                        <td colSpan={cols}>
                          <Layer2Detail row={r} />
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
