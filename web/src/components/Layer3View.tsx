import { useState } from "react";
import { formatDate } from "../lib/format";
import { formatSicIndustry } from "../lib/screener";
import type { Layer3Entry } from "../lib/layer3";

interface Props {
  entries: Layer3Entry[];
  storageNotice: string | null;
  onRemove: (issuerId: string) => void;
  onOpenScreener: () => void;
}

export function Layer3View({ entries, storageNotice, onRemove, onOpenScreener }: Props) {
  const [pendingRemove, setPendingRemove] = useState<string | null>(null);
  const sorted = [...entries].sort((a, b) => {
    const byDate = b.addedAt.localeCompare(a.addedAt);
    return byDate !== 0 ? byDate : a.displayTicker.localeCompare(b.displayTicker);
  });

  return (
    <section className="layer3">
      <div className="panel layer3-lead">
        <h2>My Layer 3 companies</h2>
        <p>
          This is a manually curated research list. Companies are added from the screener with checkboxes
          and <strong>Add to Layer 3</strong>. Nothing is enrolled from Layer 1 or Layer 2 automatically.
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
                  <th scope="col">Added</th>
                  <th scope="col">Analysis</th>
                  <th scope="col">Remove</th>
                </tr>
              </thead>
              <tbody>
                {sorted.map((e) => {
                  const extras = e.tickers.filter((t) => t !== e.displayTicker);
                  return (
                    <tr key={e.issuerId} className="layer3-row">
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
                      <td>{formatDate(e.addedAt)}</td>
                      <td>
                        <span className="pending-status" title="Financial-quality scoring is not implemented in Phase 1">
                          Analysis Not Yet Available
                        </span>
                        <div className="muted pending-sub">Pending Implementation</div>
                      </td>
                      <td className="layer3-remove">
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
