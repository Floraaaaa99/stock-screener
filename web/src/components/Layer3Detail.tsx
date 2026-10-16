import { naReason } from "../lib/explain";
import { fiscalLabel, formatDate, formatMillions } from "../lib/format";
import { LAYER3_STATUS_DETAIL, LAYER3_STATUS_LABEL, type Layer3DisplayStatus } from "../lib/layer3";
import type { Layer3FlowMetric, Layer3Quarter, Layer3Row, Layer3StockMetric } from "../types";

function Money({ value, currency }: { value: number | null | undefined; currency: string | null | undefined }) {
  if (value == null) return <span className="na">N/A</span>;
  return <span className={value < 0 ? "neg" : value === 0 ? "zero" : ""}>{formatMillions(value, currency)}</span>;
}

function Reason({ reason }: { reason: string | null | undefined }) {
  if (!reason) return null;
  return <span className="muted"> {naReason(reason)}</span>;
}

function Filing({ url, form }: { url?: string | null; form?: string | null }) {
  if (!url) return <span className="muted">—</span>;
  return (
    <a href={url} target="_blank" rel="noreferrer">
      {form ?? "filing"}
    </a>
  );
}

function FlowBlock({ title, metric, currency }: { title: string; metric: Layer3FlowMetric | undefined; currency: string | null }) {
  if (!metric) return null;
  return (
    <section className="layer3-metric-block">
      <h4>{title}</h4>
      <dl className="detail-grid">
        <div>
          <dt>Current TTM</dt>
          <dd>
            <Money value={metric.ttm} currency={currency} />
            <Reason reason={metric.reason} />
          </dd>
        </div>
        <div>
          <dt>Previous TTM</dt>
          <dd>
            <Money value={metric.previousTtm ?? null} currency={currency} />
          </dd>
        </div>
        <div>
          <dt>XBRL concept</dt>
          <dd className="concept">{metric.concept ?? "N/A"}</dd>
        </div>
        <div>
          <dt>Verification</dt>
          <dd>{metric.verification.replace(/_/g, " ")}</dd>
        </div>
        {metric.formula && (
          <div>
            <dt>Formula</dt>
            <dd>{metric.formula}</dd>
          </div>
        )}
        {metric.signPolicy && (
          <div>
            <dt>Sign policy</dt>
            <dd>{metric.signPolicy.replace(/_/g, " ")}</dd>
          </div>
        )}
      </dl>
      {metric.verificationNote && <p className="muted">{metric.verificationNote}</p>}
      {metric.quarters && metric.quarters.length > 0 && <QuarterTable quarters={metric.quarters} currency={currency} />}
    </section>
  );
}

function QuarterTable({ quarters, currency }: { quarters: Layer3Quarter[]; currency: string | null }) {
  return (
    <div className="table-scroll">
      <table className="screener layer3-quarters">
        <thead>
          <tr>
            <th scope="col">Period</th>
            <th className="num" scope="col">
              Value
            </th>
            <th scope="col">Method</th>
            <th scope="col">Formula</th>
            <th scope="col">Filing</th>
          </tr>
        </thead>
        <tbody>
          {quarters.map((q) => (
            <tr key={`${q.end ?? ""}-${q.fiscalYear}-${q.fiscalQuarter}`}>
              <td>
                {fiscalLabel(q.fiscalYear, q.fiscalQuarter)}
                <div className="muted pending-sub">
                  {q.start ?? "—"} → {q.end ?? "—"}
                </div>
              </td>
              <td className="num">
                <Money value={q.value} currency={currency} />
              </td>
              <td>{q.method ?? "—"}</td>
              <td className="formula">{q.formula ?? "—"}</td>
              <td>
                <Filing url={q.url} form={q.form} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function StockBlock({ title, metric, currency }: { title: string; metric: Layer3StockMetric | undefined; currency: string | null }) {
  if (!metric) return null;
  return (
    <div>
      <dt>{title}</dt>
      <dd>
        <Money value={metric.value} currency={currency} />
        {metric.concept && <div className="muted concept">{metric.concept}</div>}
        {metric.end && <div className="muted">As of {formatDate(metric.end)}</div>}
        {metric.aggregation && <div className="muted">{metric.aggregation.replace(/_/g, " ")}</div>}
        {metric.formula && <div className="muted">{metric.formula}</div>}
        <Filing url={metric.url} form={metric.form} />
        <Reason reason={metric.reason} />
      </dd>
    </div>
  );
}

export function Layer3Detail({ row, status }: { row: Layer3Row | null; status: Layer3DisplayStatus }) {
  const currency = row?.currency ?? row?.layer1.revenueCurrency ?? null;
  const m = row?.metrics;
  return (
    <div className="detail layer3-detail">
      <p>
        <strong>{LAYER3_STATUS_LABEL[status]}.</strong> {LAYER3_STATUS_DETAIL[status]}
      </p>
      <p className="muted">Growth Source: Not Yet Verified. Scoring is not implemented in Phase 2.</p>
      {row?.layer1 && (
        <p className="muted">
          Layer 1 TTM revenue (copied, not recomputed): <Money value={row.layer1.revenueTtm} currency={row.layer1.revenueCurrency} />
          {row.layer1.earningsConcept ? ` · NI concept ${row.layer1.earningsConcept}` : ""}
        </p>
      )}
      {!m && <p className="muted">No extracted cash-flow or balance-sheet metrics for this issuer yet.</p>}
      {m && (
        <>
          <FlowBlock title="Operating cash flow" metric={m.ocf} currency={currency} />
          <FlowBlock title="Capital expenditures" metric={m.capex} currency={currency} />
          <FlowBlock title="Free cash flow" metric={m.fcf} currency={currency} />
          <FlowBlock title="Operating income" metric={m.operatingIncome} currency={currency} />
          <FlowBlock title="Interest expense" metric={m.interestExpense} currency={currency} />
          <FlowBlock title="EBITDA (when calculable)" metric={m.ebitda} currency={currency} />
          <section className="layer3-metric-block">
            <h4>Balance sheet (latest quarter-end)</h4>
            <dl className="detail-grid">
              <StockBlock title="Cash and cash equivalents" metric={m.cash} currency={currency} />
              <StockBlock title="Short-term debt" metric={m.shortTermDebt} currency={currency} />
              <StockBlock title="Long-term debt" metric={m.longTermDebt} currency={currency} />
              <StockBlock title="Total debt" metric={m.totalDebt} currency={currency} />
              <StockBlock title="Net debt" metric={m.netDebt} currency={currency} />
              <div>
                <dt>No interest burden</dt>
                <dd>{m.noInterestBurden ? "Yes — verified zero interest and zero debt" : "No"}</dd>
              </div>
            </dl>
          </section>
        </>
      )}
    </div>
  );
}
