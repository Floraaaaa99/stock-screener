import { comparisonRows, priorYearRows } from "../lib/compare";
import { naReason } from "../lib/explain";
import { formatDate, formatMillions, formatPercent } from "../lib/format";
import type { Layer2Rate, Layer2Row } from "../types";

function Money({ value, currency }: { value: number | null; currency: string | null }) {
  if (value == null) return <span className="na">N/A</span>;
  return <span className={value < 0 ? "neg" : ""}>{formatMillions(value, currency)}</span>;
}

function RateCell({ rate, currency }: { rate: Layer2Rate | null; currency: string | null }) {
  if (!rate) return <span className="na">N/A</span>;
  const prior = rate.otherValue == null ? null : `Prior: ${formatMillions(rate.otherValue, currency)}`;
  const tip = [prior, rate.reason ? naReason(rate.reason) : null].filter(Boolean).join(" · ");
  if (rate.rate == null) {
    return (
      <span className="na" title={tip || undefined}>
        N/A
      </span>
    );
  }
  const cls = rate.rate > 0 ? "pos" : rate.rate < 0 ? "neg" : "";
  return (
    <span className={cls} title={tip || undefined}>
      {formatPercent(rate.rate)}
    </span>
  );
}

function FilingCell({ rate }: { rate: Layer2Rate | null }) {
  if (!rate?.currentUrl) return <span className="muted">—</span>;
  const tip = [rate.currentCheck && `Validation: ${rate.currentCheck}`, rate.reason && naReason(rate.reason)]
    .filter(Boolean)
    .join(" · ");
  return (
    <a href={rate.currentUrl} target="_blank" rel="noreferrer" title={tip || undefined}>
      {rate.currentForm ?? "filing"}
    </a>
  );
}

export function Layer2Detail({ row }: { row: Layer2Row }) {
  const currency = row.revenueCurrency;
  const rows = comparisonRows(row);
  const prior = priorYearRows(row);
  const hasEarnings = Boolean(row.earningsYoy?.length || row.earningsQoq?.length);

  return (
    <div className="detail">
      <p className="note">
        One row per quarter in Layer 1’s <strong>verified historical</strong> window (rules v{row.rulesVersion}).
        Revenue concept <code>{row.revenueConcept ?? "N/A"}</code>
        {hasEarnings && (
          <>
            ; net income <code>{row.earningsConcept ?? "N/A"}</code> is detail only and does not change Passed /
            Watchlist
          </>
        )}
        . Amounts in {currency ?? "reporting currency"}. Hover a rate for the prior amount used.
      </p>
      {row.freshness?.status === "verified_lagging" && row.freshness.message && (
        <p className="freshness-banner" role="note">
          <strong>Freshness warning.</strong> {row.freshness.message}
        </p>
      )}
      {row.freshness?.status === "current" && row.freshness.message && (
        <p className="freshness-ok" role="note">
          {row.freshness.message}
        </p>
      )}
      {row.dataReviewReasons.length > 0 && (
        <p className="na-reason">Data Review: {row.dataReviewReasons.map(naReason).join(" ")}</p>
      )}

      {rows.length > 0 ? (
        <div className="table-scroll">
          <table className="quarters compare-table">
            <caption>Latest four quarters · oldest to newest · {currency ?? "reporting currency"}</caption>
            <thead>
              <tr>
                <th>Fiscal quarter</th>
                <th>Period end</th>
                <th className="num">Revenue</th>
                <th className="num">Net income</th>
                <th className="num">Rev YoY</th>
                <th className="num">NI YoY</th>
                <th className="num">Rev QoQ</th>
                <th className="num">NI QoQ</th>
                <th>Filing</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.key}>
                  <td>{r.label}</td>
                  <td>{formatDate(r.end)}</td>
                  <td className="num">
                    <Money value={r.revenue} currency={currency} />
                  </td>
                  <td className="num">
                    <Money value={r.earnings} currency={currency} />
                  </td>
                  <td className="num">
                    <RateCell rate={r.revYoy} currency={currency} />
                  </td>
                  <td className="num">
                    <RateCell rate={r.niYoy} currency={currency} />
                  </td>
                  <td className="num">
                    <RateCell rate={r.revQoq} currency={currency} />
                  </td>
                  <td className="num">
                    <RateCell rate={r.niQoq} currency={currency} />
                  </td>
                  <td>
                    <FilingCell rate={r.revYoy} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="muted">No sequential-growth window is available for this company.</p>
      )}

      {prior.some((p) => p.revenue != null || p.earnings != null) && (
        <details className="prior-year">
          <summary>Prior-year quarters used for YoY</summary>
          <div className="table-scroll">
            <table className="quarters compare-prior">
              <caption>Same fiscal quarter last year · values only</caption>
              <thead>
                <tr>
                  <th>Fiscal quarter</th>
                  <th className="num">Revenue</th>
                  <th className="num">Net income</th>
                  <th>Filing</th>
                </tr>
              </thead>
              <tbody>
                {prior.map((p) => (
                  <tr key={p.key}>
                    <td>{p.label}</td>
                    <td className="num">
                      <Money value={p.revenue} currency={currency} />
                    </td>
                    <td className="num">
                      <Money value={p.earnings} currency={currency} />
                    </td>
                    <td>
                      {p.url ? (
                        <a href={p.url} target="_blank" rel="noreferrer">
                          {p.form ?? "filing"}
                        </a>
                      ) : (
                        <span className="muted">—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}
    </div>
  );
}
