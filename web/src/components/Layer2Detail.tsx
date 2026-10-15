import { comparisonRows, priorYearRows } from "../lib/compare";
import { naReason } from "../lib/explain";
import { formatDate, formatMillions, formatPercent } from "../lib/format";
import type { Layer2RowLive } from "../lib/layer2";
import { analyzeNetIncome, formatNiChange, niRuleStatus, type NiAnalysis, type NiQuarter } from "../lib/niAnalysis";
import type { Layer2Badge, Layer2Rate, Layer2Row } from "../types";
import { CategoryBadges } from "./CategoryBadges";

function Money({ value, currency }: { value: number | null; currency: string | null }) {
  if (value == null) return <span className="na">N/A</span>;
  return <span className={value < 0 ? "neg" : value === 0 ? "zero" : ""}>{formatMillions(value, currency)}</span>;
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

function NiChangeCell({
  abs,
  prior,
  rate,
  currency,
}: {
  abs: number | null;
  prior: number | null;
  rate: number | null;
  currency: string | null;
}) {
  const f = formatNiChange(abs, prior, rate, currency);
  return (
    <span className={f.kind === "pos" ? "pos" : f.kind === "neg" ? "neg" : "na"} title={f.title || undefined}>
      {f.text}
    </span>
  );
}

function FilingLink({ rate, kind }: { rate: Layer2Rate | null; kind: "Revenue" | "NI" }) {
  if (!rate?.currentUrl) return null;
  const tip = [
    kind,
    rate.currentCheck && `Validation: ${rate.currentCheck}`,
    rate.reason && naReason(rate.reason),
  ]
    .filter(Boolean)
    .join(" · ");
  return (
    <a href={rate.currentUrl} target="_blank" rel="noreferrer" title={tip}>
      {kind} {rate.currentForm ?? "filing"}
    </a>
  );
}

function Filings({ rev, ni }: { rev: Layer2Rate | null; ni: Layer2Rate | null }) {
  const revLink = <FilingLink rate={rev} kind="Revenue" />;
  const niLink = ni?.currentUrl && ni.currentUrl !== rev?.currentUrl ? <FilingLink rate={ni} kind="NI" /> : null;
  if (!revLink && !niLink) return <span className="muted">—</span>;
  return (
    <span className="filing-cell">
      {revLink}
      {niLink}
    </span>
  );
}

function statusLabel(status: ReturnType<typeof niRuleStatus>): string {
  if (status === "applied") return "Applied";
  if (status === "unavailable") return "Unavailable";
  return "Unmet";
}

function NiRuleList({ badges }: { badges: Layer2Badge[] }) {
  return (
    <ul className="ni-rules">
      {badges.map((b) => {
        const status = niRuleStatus(b);
        return (
          <li key={b.id} title={b.tooltip}>
            <span className={`ni-rule-status ${status}`}>{statusLabel(status)}</span>
            <span>{b.label}</span>
            <span className="muted ni-rule-tip">{b.tooltip}</span>
          </li>
        );
      })}
    </ul>
  );
}

function quarterFor(ni: NiAnalysis, end: string | null, i: number): NiQuarter | undefined {
  return (end && ni.quarters.find((q) => q.end === end)) || ni.quarters[i];
}

export function Layer2Detail({ row }: { row: Layer2Row | Layer2RowLive }) {
  const currency = row.revenueCurrency;
  const rows = comparisonRows(row);
  const prior = priorYearRows(row);
  const ni = "ni" in row && row.ni && "quarters" in row.ni ? (row.ni as NiAnalysis) : analyzeNetIncome(row);
  const hasEarnings = Boolean(row.earningsYoy?.length || row.earningsQoq?.length);

  return (
    <div className="detail">
      <p className="note">
        One row per quarter in Layer 1’s <strong>verified historical</strong> window (rules v{row.rulesVersion}).
        Revenue concept <code>{row.revenueConcept ?? "N/A"}</code>
        {hasEarnings && (
          <>
            ; net income <code>{row.earningsConcept ?? "N/A"}</code> (NI rules v{ni.rulesVersion}) is descriptive on
            Passed companies and does not change Passed / Watchlist
          </>
        )}
        . Amounts in {currency ?? "reporting currency"}. Unverified or missing NI is N/A, never zero. Hover a rate for
        the prior amount used.
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

      {row.bucket === "passed" && (
        <div className="ni-summary">
          <p>
            <strong>TTM Net Income</strong>{" "}
            {ni.ttm == null ? (
              <span className="na" title={ni.ttmReason ? naReason(ni.ttmReason) : undefined}>
                N/A
              </span>
            ) : (
              <span className={ni.ttm < 0 ? "neg" : ni.ttm > 0 ? "pos" : "zero"}>{formatMillions(ni.ttm, currency)}</span>
            )}
            <span className="muted">
              {" "}
              · sum of the same four quarters as revenue
              {ni.profitableCount != null &&
                ` · ${ni.profitableCount} profitable, ${ni.lossCount} loss, ${ni.breakEvenCount} break-even`}
              {ni.latestIsLoss ? " · latest quarter is a loss" : ""}
            </span>
          </p>
          <div className="ni-badge-block">
            <span className="k">Profitability</span>
            <CategoryBadges badges={ni.profitability} />
          </div>
          <div className="ni-badge-block">
            <span className="k">Profit improvement</span>
            <p className="muted ni-no-badge-note">
              No applied badge is not deterioration. Each rule is Applied, Unmet, or Unavailable from its own inputs.
            </p>
            <NiRuleList badges={ni.improvement} />
          </div>
        </div>
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
                <th className="num">NI YoY Δ</th>
                <th className="num">Rev QoQ</th>
                <th className="num">NI QoQ Δ</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => {
                const q = quarterFor(ni, r.end, i);
                return (
                  <tr key={r.key} className={q?.verified && q.display != null && q.display < 0 && i === rows.length - 1 ? "latest-loss-row" : undefined}>
                    <td>{r.label}</td>
                    <td>
                      {formatDate(r.end)}
                      <div className="filing-cell">
                        <Filings rev={r.revYoy} ni={r.niYoy} />
                      </div>
                    </td>
                    <td className="num">
                      <Money value={r.revenue} currency={currency} />
                    </td>
                    <td className="num">
                      {q?.verified ? (
                        <Money value={q.display} currency={currency} />
                      ) : (
                        <span className="na" title={q?.reason ? naReason(q.reason) : "N/A"}>
                          N/A
                        </span>
                      )}
                    </td>
                    <td className="num">
                      <RateCell rate={r.revYoy} currency={currency} />
                    </td>
                    <td className="num">
                      <NiChangeCell abs={q?.yoyAbs ?? null} prior={q?.priorValue ?? null} rate={r.niYoy?.rate ?? null} currency={currency} />
                    </td>
                    <td className="num">
                      <RateCell rate={r.revQoq} currency={currency} />
                    </td>
                    <td className="num">
                      <NiChangeCell abs={q?.qoqAbs ?? null} prior={q?.qoqPrior ?? null} rate={r.niQoq?.rate ?? null} currency={currency} />
                    </td>
                  </tr>
                );
              })}
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
