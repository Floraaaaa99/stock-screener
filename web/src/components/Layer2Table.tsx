import { Fragment } from "react";
import { naReason } from "../lib/explain";
import { formatMillions, formatPercent } from "../lib/format";
import type { Layer2RowLive } from "../lib/layer2";
import type { NiQuarter } from "../lib/niAnalysis";
import { formatSicIndustry } from "../lib/screener";
import type { Layer2Rate } from "../types";
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

function NiAmounts({ quarters, currency }: { quarters: NiQuarter[]; currency: string | null }) {
  if (quarters.length === 0) return <span className="na">N/A</span>;
  const last = quarters.length - 1;
  return (
    <span className="rate-stack">
      {quarters.map((q, i) => {
        const loss = q.display != null && q.display < 0;
        const cls = q.display == null ? "na" : loss ? "neg" : q.display === 0 ? "zero" : "pos";
        const tip = [
          q.label,
          q.end,
          q.reason ? naReason(q.reason) : q.display == null ? "N/A" : formatMillions(q.display, currency),
          i === last && loss ? "Latest quarter is a loss" : null,
        ]
          .filter(Boolean)
          .join(" · ");
        return (
          <span key={q.end ?? q.label} className={`rate-chip ${cls} ${i === last && loss ? "latest-loss" : ""}`} title={tip}>
            <span className="rate-lab">{q.label}</span>
            {q.display == null ? "N/A" : formatMillions(q.display, currency)}
          </span>
        );
      })}
    </span>
  );
}

export function Layer2Table({
  loading,
  rows,
  expanded,
  onToggle,
  onClearFilters,
  showNi = false,
}: {
  loading: boolean;
  rows: Layer2RowLive[];
  expanded: string | null;
  onToggle: (ticker: string) => void;
  onClearFilters: () => void;
  showNi?: boolean;
}) {
  const cols = showNi ? 12 : 8;
  return (
    <section className="panel table-panel">
      <div className="table-scroll">
        <table className="screener layer2-table">
          <thead>
            <tr>
              <th>Ticker</th>
              <th>Company</th>
              <th className="sic">SEC SIC industry</th>
              <th className="num">TTM Revenue Growth</th>
              <th title="Oldest to newest; fiscal labels and period-end dates">Latest four YoY</th>
              <th title="Oldest to newest; descriptive only">Latest four QoQ</th>
              {showNi && (
                <>
                  <th className="num">TTM Net Income</th>
                  <th title="Oldest to newest; unverified amounts are N/A">Latest four NI</th>
                  <th>Profitability</th>
                  <th>Profit improvement</th>
                </>
              )}
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
                      <td className="sic">{r.sicIndustry ? formatSicIndustry(r.sicIndustry) : "N/A"}</td>
                      <td className="num">
                        {r.ttmGrowth == null ? <span className="na">N/A</span> : <span className={r.ttmGrowth > 0 ? "pos" : r.ttmGrowth < 0 ? "neg" : ""}>{formatPercent(r.ttmGrowth)}</span>}
                      </td>
                      <td>
                        <Rates rows={r.yoy} />
                      </td>
                      <td>
                        <Rates rows={r.qoq} />
                      </td>
                      {showNi && (
                        <>
                          <td className="num">
                            {r.ni.ttm == null ? (
                              <span className="na" title={r.ni.ttmReason ?? "N/A"}>
                                N/A
                              </span>
                            ) : (
                              <span className={r.ni.ttm < 0 ? "neg" : r.ni.ttm > 0 ? "pos" : ""}>
                                {formatMillions(r.ni.ttm, r.revenueCurrency)}
                              </span>
                            )}
                          </td>
                          <td>
                            <NiAmounts quarters={r.ni.quarters} currency={r.revenueCurrency} />
                          </td>
                          <td>
                            <CategoryBadges badges={r.ni.profitability} />
                          </td>
                          <td>
                            <CategoryBadges badges={r.ni.improvement.filter((b) => b.applied)} />
                          </td>
                        </>
                      )}
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
