import { naReason } from "../lib/explain";
import { formatCompactMoney, formatDate, formatPercent } from "../lib/format";
import type { Layer2Rate, Layer2Row } from "../types";
import { CompanyDetailPanel } from "./CompanyDetail";

function RateTable({ title, rows, currency }: { title: string; rows: Layer2Rate[]; currency: string | null }) {
  return (
    <div className="table-scroll">
      <table className="quarters layer2-rates">
        <caption>{title} · oldest to newest · {currency ?? "reporting currency"}</caption>
        <thead>
          <tr>
            <th>Fiscal quarter</th>
            <th>Period end</th>
            <th className="num">Revenue</th>
            <th className="num">Prior used</th>
            <th className="num">Absolute change</th>
            <th className="num">Rate</th>
            <th>Filings</th>
            <th>Validation</th>
            <th>Reason</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((e) => (
            <tr key={`${e.kind}-${e.end}-${e.label}`}>
              <td>{e.label ?? "N/A"}</td>
              <td>{formatDate(e.end)}</td>
              <td className="num">{e.currentValue == null ? "N/A" : formatCompactMoney(e.currentValue, currency)}</td>
              <td className="num">{e.otherValue == null ? "N/A" : formatCompactMoney(e.otherValue, currency)}</td>
              <td className="num">{e.absoluteChange == null ? "N/A" : formatCompactMoney(e.absoluteChange, currency)}</td>
              <td className="num">{e.rate == null ? <span className="na">N/A</span> : formatPercent(e.rate)}</td>
              <td>
                {e.currentUrl ? (
                  <a href={e.currentUrl} target="_blank" rel="noreferrer">
                    {e.currentForm ?? "current"}
                  </a>
                ) : (
                  "—"
                )}
                {e.otherUrl && (
                  <>
                    {" / "}
                    <a href={e.otherUrl} target="_blank" rel="noreferrer">
                      {e.otherForm ?? "prior"}
                    </a>
                  </>
                )}
              </td>
              <td>
                {e.currentCheck ?? "—"} / {e.otherCheck ?? "—"}
              </td>
              <td>{e.reason ? naReason(e.reason) : "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function Layer2Detail({ row }: { row: Layer2Row }) {
  return (
    <div className="detail">
      <p className="note">
        Layer 2 uses Layer 1’s latest 8 consecutive comparable quarters (rules v{row.rulesVersion}). Revenue concept{" "}
        <code>{row.revenueConcept ?? "N/A"}</code> in {row.revenueCurrency ?? "N/A"}. QoQ does not affect YoY eligibility.
      </p>
      {row.dataReviewReasons.length > 0 && (
        <p className="na-reason">Data Review: {row.dataReviewReasons.map(naReason).join(" ")}</p>
      )}
      <RateTable title="Quarterly YoY" rows={row.yoy} currency={row.revenueCurrency} />
      <RateTable title="Quarterly QoQ" rows={row.qoq} currency={row.revenueCurrency} />
      <h3 className="layer2-l1-heading">Layer 1 quarterly window</h3>
      <CompanyDetailPanel ticker={row.ticker} />
    </div>
  );
}
