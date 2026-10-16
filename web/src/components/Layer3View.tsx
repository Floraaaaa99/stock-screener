import { Fragment, useMemo, useState } from "react";
import { naReason } from "../lib/explain";
import { formatCompactMoney, formatDate } from "../lib/format";
import {
  LAYER3_STATUS_LABEL,
  displayStatus,
  metricsForEntry,
  metricValue,
  type Layer3Entry,
  type Layer3Index,
} from "../lib/layer3";
import { formatSicIndustry } from "../lib/screener";
import type { Layer3File, Layer3FlowMetric, Layer3StockMetric } from "../types";
import { Layer3Detail } from "./Layer3Detail";

interface Props {
  entries: Layer3Entry[];
  catalog: Layer3File | null;
  index: Layer3Index;
  storageNotice: string | null;
  onRemove: (issuerId: string) => void;
  onOpenScreener: () => void;
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

function StatusCell({ status }: { status: keyof typeof LAYER3_STATUS_LABEL }) {
  return (
    <span className={`layer3-status is-${status}`} title={LAYER3_STATUS_LABEL[status]}>
      {LAYER3_STATUS_LABEL[status]}
    </span>
  );
}

export function Layer3View({ entries, catalog, index, storageNotice, onRemove, onOpenScreener }: Props) {
  const [pendingRemove, setPendingRemove] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
  const sorted = useMemo(
    () =>
      [...entries].sort((a, b) => {
        const byDate = b.addedAt.localeCompare(a.addedAt);
        return byDate !== 0 ? byDate : a.displayTicker.localeCompare(b.displayTicker);
      }),
    [entries],
  );
  const fileLoaded = catalog != null;

  return (
    <section className="layer3">
      <div className="panel layer3-lead">
        <h2>My Layer 3 companies</h2>
        <p>
          This is a manually curated research list. Companies are added from the screener with checkboxes
          and <strong>Add to Layer 3</strong>. Nothing is enrolled from Layer 1 or Layer 2 automatically.
        </p>
        <p className="muted">
          Phase 2 extracts SEC cash-flow and balance-sheet metrics for saved issuers only. Missing or
          unverified amounts stay N/A. The 100-point score is not implemented yet. Growth Source: Not Yet
          Verified.
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
                  const status = displayStatus(e, row, fileLoaded);
                  const currency = row?.currency ?? row?.layer1.revenueCurrency ?? null;
                  const m = row?.metrics;
                  const open = expanded === e.issuerId;
                  return (
                    <Fragment key={e.issuerId}>
                      <tr
                        className={`layer3-row row ${open ? "open" : ""}`}
                        onClick={() => setExpanded(open ? null : e.issuerId)}
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
                          <StatusCell status={status} />
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
                                  if (expanded === e.issuerId) setExpanded(null);
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
                      {open && (
                        <tr className="detail-row">
                          <td colSpan={14}>
                            <Layer3Detail row={row} status={status} />
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
      )}
    </section>
  );
}
