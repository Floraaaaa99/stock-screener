import { Fragment, useEffect, useMemo, useState } from "react";
import { loadLayer3Issuers } from "../api";
import { naReason } from "../lib/explain";
import { formatCompactMoney, formatDate } from "../lib/format";
import {
  ciksForEntries,
  indexLayer3Rows,
  metricsForEntry,
  metricValue,
  statusLines,
  type Layer3Entry,
} from "../lib/layer3";
import { formatSicIndustry } from "../lib/screener";
import type { Layer3FlowMetric, Layer3Row, Layer3StockMetric } from "../types";

interface Props {
  entries: Layer3Entry[];
  storageNotice: string | null;
  onRemove: (issuerId: string) => void;
  onOpenScreener: () => void;
  onOpenResearch: (cik: string) => void;
}

function MoneyCell({
  metric,
  currency,
}: {
  metric: Layer3FlowMetric | Layer3StockMetric | null | undefined;
  currency: string | null | undefined;
}) {
  const value = metricValue(metric);
  if (value == null) {
    const reason = metric && "reason" in metric ? metric.reason : null;
    return (
      <span className="na" title={naReason(reason) || "Not available — missing values are not replaced with zero"}>
        N/A
      </span>
    );
  }
  return <span className={value < 0 ? "neg" : value === 0 ? "zero" : ""}>{formatCompactMoney(value, currency)}</span>;
}

function StatusCell({ row, fileLoaded }: { row: Layer3Row | null; fileLoaded: boolean }) {
  return (
    <ul className="layer3-status-stack">
      {statusLines(row, fileLoaded).map((line) => (
        <li key={line.kind} className={`layer3-status is-${line.kind}`} title={line.title}>
          {line.label}
        </li>
      ))}
    </ul>
  );
}

export function Layer3View({ entries, storageNotice, onRemove, onOpenScreener, onOpenResearch }: Props) {
  const [pendingRemove, setPendingRemove] = useState<string | null>(null);
  const [issuerRows, setIssuerRows] = useState<Layer3Row[]>([]);
  const [metricsState, setMetricsState] = useState<"idle" | "loading" | "ready">("idle");
  const sorted = useMemo(
    () =>
      [...entries].sort((a, b) => {
        const byDate = b.addedAt.localeCompare(a.addedAt);
        return byDate !== 0 ? byDate : a.displayTicker.localeCompare(b.displayTicker);
      }),
    [entries],
  );
  const wantedCikList = useMemo(() => ciksForEntries(entries), [entries]);
  const wantedCiks = wantedCikList.join(",");
  useEffect(() => {
    const ciks = wantedCiks ? wantedCiks.split(",") : [];
    if (ciks.length === 0) {
      setIssuerRows([]);
      setMetricsState("ready");
      return;
    }
    let cancelled = false;
    setMetricsState("loading");
    loadLayer3Issuers(ciks).then((rows) => {
      if (cancelled) return;
      setIssuerRows(rows);
      setMetricsState("ready");
    });
    return () => {
      cancelled = true;
    };
  }, [wantedCiks]);
  const index = useMemo(() => indexLayer3Rows(issuerRows), [issuerRows]);
  const fileLoaded = metricsState === "ready";

  return (
    <section className="layer3">
      <div className="panel layer3-lead">
        <h2>My Layer 3 companies</h2>
        <p>
          This is a manually curated research list. Companies are added from the screener with checkboxes
          and <strong>Add to Layer 3</strong>. Nothing is enrolled from Layer 1 or Layer 2 automatically.
        </p>
        <p className="muted">
          Open a company to examine its financial research page. The browser downloads one CIK file per
          company on this list — not the full universe. Missing amounts stay N/A. There is no score,
          ranking, or investment recommendation.
        </p>
        <p className="muted">
          Cash-flow and balance-sheet figures are independently recalculated from SEC Company Facts XBRL.
          They are not statement-verified against the rendered 10-Q/10-K cash-flow or balance-sheet face.
          Layer 1 revenue and net income that matched an income-statement line remain a separate concept.
        </p>
        <p className="muted">
          <strong>Phase 2 core inputs present</strong> means TTM operating cash flow, TTM CapEx, and cash
          were extracted. It does not mean every 100-point scoring input is complete, and it is not a
          statement-verification result.
        </p>
        <p className="muted">
          The list is saved in this browser only. Clearing site data removes it. It is not synced across
          devices or accounts.
        </p>
        {storageNotice && (
          <p className="selection-storage" role="status">
            {storageNotice}
          </p>
        )}
      </div>

      {sorted.length === 0 ? (
        <div className="panel layer3-empty">
          <h3>No companies yet</h3>
          <p>
            Filter the screener, select tickers with the checkboxes, then click <strong>Add to Layer 3</strong>.
          </p>
          <button type="button" className="btn current" onClick={onOpenScreener}>
            Open TTM growth screener
          </button>
        </div>
      ) : (
        <section className="panel table-panel">
          {metricsState === "loading" && (
            <p className="detail-loading" role="status">
              <span className="spinner" aria-hidden="true" /> Loading extracted metrics for {wantedCikList.length}{" "}
              saved issuer{wantedCikList.length === 1 ? "" : "s"}…
            </p>
          )}
          <div className="table-scroll">
            <table className="screener layer3-table">
              <thead>
                <tr>
                  <th scope="col">Ticker</th>
                  <th scope="col">Company</th>
                  <th className="sic" scope="col">
                    SEC SIC industry
                  </th>
                  <th scope="col">Status</th>
                  <th className="num" scope="col">
                    TTM OCF
                  </th>
                  <th className="num" scope="col">
                    TTM CapEx
                  </th>
                  <th className="num" scope="col">
                    TTM FCF
                  </th>
                  <th className="num" scope="col">
                    TTM Op. income
                  </th>
                  <th className="num" scope="col">
                    Cash
                  </th>
                  <th className="num" scope="col">
                    Net debt
                  </th>
                  <th className="num" scope="col">
                    TTM interest
                  </th>
                  <th className="num" scope="col">
                    TTM EBITDA
                  </th>
                  <th scope="col">Added</th>
                  <th scope="col">Remove</th>
                </tr>
              </thead>
              <tbody>
                {sorted.map((e) => {
                  const extras = e.tickers.filter((t) => t !== e.displayTicker);
                  const row = metricsForEntry(e, index);
                  const currency = row?.currency ?? row?.layer1.revenueCurrency ?? null;
                  const m = row?.metrics;
                  return (
                    <Fragment key={e.issuerId}>
                      <tr
                        className="layer3-row row"
                        onClick={() => {
                          if (e.cik) onOpenResearch(e.cik);
                        }}
                      >
                        <td className="ticker">
                          {e.displayTicker}
                          {extras.length > 0 && (
                            <div className="share-class-note" title="Same SEC issuer; Layer 3 analysis is shared">
                              Also {extras.join(", ")}
                            </div>
                          )}
                        </td>
                        <td className="name" title={e.name}>
                          {e.name}
                        </td>
                        <td className="sic">{e.sicIndustry ? formatSicIndustry(e.sicIndustry) : "N/A"}</td>
                        <td>
                          <StatusCell row={row} fileLoaded={fileLoaded} />
                        </td>
                        <td className="num">
                          <MoneyCell metric={m?.ocf} currency={currency} />
                        </td>
                        <td className="num">
                          <MoneyCell metric={m?.capex} currency={currency} />
                        </td>
                        <td className="num">
                          <MoneyCell metric={m?.fcf} currency={currency} />
                        </td>
                        <td className="num">
                          <MoneyCell metric={m?.operatingIncome} currency={currency} />
                        </td>
                        <td className="num">
                          <MoneyCell metric={m?.cash} currency={currency} />
                        </td>
                        <td className="num">
                          <MoneyCell metric={m?.netDebt} currency={currency} />
                        </td>
                        <td className="num">
                          <MoneyCell metric={m?.interestExpense} currency={currency} />
                        </td>
                        <td className="num">
                          <MoneyCell metric={m?.ebitda} currency={currency} />
                        </td>
                        <td>{formatDate(e.addedAt)}</td>
                        <td className="layer3-remove" onClick={(ev) => ev.stopPropagation()}>
                          {pendingRemove === e.issuerId ? (
                            <div className="remove-confirm">
                              <span className="muted">Remove {e.displayTicker}?</span>
                              <button
                                type="button"
                                className="btn btn-small danger"
                                onClick={() => {
                                  onRemove(e.issuerId);
                                  setPendingRemove(null);
                                }}
                              >
                                Confirm remove
                              </button>
                              <button type="button" className="btn btn-small" onClick={() => setPendingRemove(null)}>
                                Cancel
                              </button>
                            </div>
                          ) : (
                            <button type="button" className="btn btn-small" onClick={() => setPendingRemove(e.issuerId)}>
                              Remove
                            </button>
                          )}
                        </td>
                      </tr>
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </section>
  );
}
