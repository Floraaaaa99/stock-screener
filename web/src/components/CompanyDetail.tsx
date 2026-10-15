import { useEffect, useState } from "react";
import { loadCompany } from "../api";
import { CONCEPT_STATUS, flagText, naReason } from "../lib/explain";
import { fiscalLabel, formatDate, formatMillions } from "../lib/format";
import { formatSicIndustry } from "../lib/screener";
import type { CompanyDetail, QuarterEntry, ReportedQuarter } from "../types";

type State = { status: "loading" } | { status: "error"; message: string } | { status: "ready"; data: CompanyDetail };

export function CompanyDetailPanel({ ticker }: { ticker: string }) {
  const [state, setState] = useState<State>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setState({ status: "loading" });
    loadCompany(ticker)
      .then((data) => !cancelled && setState({ status: "ready", data }))
      .catch((err: unknown) => !cancelled && setState({ status: "error", message: err instanceof Error ? err.message : String(err) }));
    return () => {
      cancelled = true;
    };
  }, [ticker, attempt]);

  if (state.status === "loading") {
    return (
      <div className="detail detail-loading" role="status">
        <span className="spinner" aria-hidden="true" /> Loading quarterly revenue for {ticker}…
      </div>
    );
  }
  if (state.status === "error") {
    return (
      <div className="detail detail-error" role="alert">
        Could not load details for {ticker}: {state.message}{" "}
        <button type="button" className="btn btn-small" onClick={() => setAttempt((a) => a + 1)}>
          Retry
        </button>
      </div>
    );
  }
  return <Detail data={state.data} />;
}

function shortConcept(c: string | null | undefined): string {
  if (!c) return "N/A";
  return c
    .replace("RevenueFromContractWithCustomerExcludingAssessedTax", "RevenueFromContractWithCustomer (excl. tax)")
    .replace("RevenueFromContractWithCustomerIncludingAssessedTax", "RevenueFromContractWithCustomer (incl. tax)");
}

function CheckBadge({ q }: { q: ReportedQuarter }) {
  const c = q.check;
  if (!c) return <span className="badge muted">Not checked</span>;
  const tip = [c.statement_label && `Statement line: ${c.statement_label}`, c.detail].filter(Boolean).join("\n");
  if (c.status === "match") {
    return (
      <a className="badge ok" href={c.url} target="_blank" rel="noreferrer" title={tip || "Matches the filing's income statement"}>
        ✓ Matches filing
      </a>
    );
  }
  if (c.status === "mismatch") {
    return (
      <a className="badge warn" href={c.url} target="_blank" rel="noreferrer" title={tip}>
        ⚠ Differs from filing
      </a>
    );
  }
  return (
    <span className="badge muted" title={c.detail}>
      Not verifiable
    </span>
  );
}

function TtmBadge({ role }: { role: QuarterEntry["ttm"] }) {
  if (role === "current") return <span className="badge ttm-current">Current TTM</span>;
  if (role === "previous") return <span className="badge ttm-previous">Previous TTM</span>;
  return null;
}

function NetIncomeCell({ q, currency }: { q: ReportedQuarter | undefined; currency: string | null }) {
  if (!q) return <span className="na">N/A</span>;
  return <span className={q.value < 0 ? "neg" : ""}>{formatMillions(q.value, currency)}</span>;
}

function QuarterRow({
  q,
  currency,
  earnings,
}: {
  q: QuarterEntry;
  currency: string | null;
  earnings?: ReportedQuarter;
}) {
  const label = fiscalLabel(q.fiscalYear, q.fiscalQuarter);
  if (q.missing) {
    return (
      <tr className={`q-row q-${q.ttm ?? "older"} q-missing`}>
        <td>{label}</td>
        <td>
          ≈ {formatDate(q.start)} – {formatDate(q.end)}
        </td>
        <td className="num">
          <span className="na">N/A</span>
        </td>
        <td className="num">
          <NetIncomeCell q={earnings} currency={currency} />
        </td>
        <td>
          <TtmBadge role={q.ttm} />
        </td>
        <td colSpan={3} className="muted">
          No revenue figure for this quarter in SEC Company Facts.
        </td>
      </tr>
    );
  }
  return (
    <tr className={`q-row q-${q.ttm ?? "older"}`}>
      <td>
        {label}
        {q.labelInferred && (
          <span className="hint" title="Fiscal label inferred from neighbouring quarters (no filing for this period in Company Facts)">
            *
          </span>
        )}
      </td>
      <td>
        {formatDate(q.start)} – {formatDate(q.end)}
      </td>
      <td className={`num ${q.value < 0 ? "neg" : ""}`}>{formatMillions(q.value, currency)}</td>
      <td className="num">
        <NetIncomeCell q={earnings} currency={currency} />
      </td>
      <td>
        <TtmBadge role={q.ttm} />
      </td>
      <td>
        <span className={`method ${q.method}`}>{q.method === "reported" ? "Reported" : "Derived"}</span>{" "}
        <span className="formula" title={q.sources.map((s) => `${s.sign > 0 ? "+" : "−"} ${s.form} ${s.start}…${s.end}`).join("\n")}>
          {q.formula}
        </span>
        {q.restated && (
          <span className="badge warn-soft" title="A later filing revised this figure; the revised value is shown.">
            Restated
          </span>
        )}
        {q.flags.includes("negative_value") && <span className="badge warn-soft">Negative</span>}
      </td>
      <td>
        <a href={q.url} target="_blank" rel="noreferrer">
          {q.form}
        </a>{" "}
        <span className="muted">filed {formatDate(q.filed)}</span>
      </td>
      <td>
        <CheckBadge q={q} />
      </td>
    </tr>
  );
}

function Detail({ data }: { data: CompanyDetail }) {
  const rev = data.revenue;
  const quarters = rev?.quarters ?? [];
  const currency = rev?.currency ?? data.earnings?.currency ?? "USD";
  const earningsByEnd = new Map(
    (data.earnings?.quarters ?? [])
      .filter((q): q is ReportedQuarter => !q.missing && Boolean(q.end))
      .map((q) => [q.end, q]),
  );
  const sc = rev?.statementCheck;
  const flags = (rev?.flags ?? []).filter((f) => f !== data.ttm.reason);
  const edgar = data.cik ? `https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=${data.cik}&type=10-&dateb=&owner=include&count=40` : null;

  return (
    <div className="detail">
      <div className="detail-grid">
        <div>
          <span className="k">Revenue source</span>
          <span className="v">
            {rev?.concept ? (
              <>
                SEC XBRL <code>{shortConcept(rev.concept)}</code>
                {rev.conceptStatus && <span className="muted"> — {CONCEPT_STATUS[rev.conceptStatus] ?? rev.conceptStatus}</span>}
              </>
            ) : (
              <span className="muted">{naReason(data.ttm.reason)}</span>
            )}
          </span>
        </div>
        <div>
          <span className="k">Latest income statement</span>
          <span className="v">
            {sc && sc.url && (sc.status === "verified" || sc.status === "verified_value") ? (
              <a href={sc.url} target="_blank" rel="noreferrer">
                ✓ {sc.form} for period ending {formatDate(sc.period_end)} matches
              </a>
            ) : sc && sc.url ? (
              <a href={sc.url} target="_blank" rel="noreferrer">
                {sc.status.replace(/_/g, " ")}
              </a>
            ) : (
              <span className="muted">N/A</span>
            )}
          </span>
        </div>
        <div>
          <span className="k">SEC company</span>
          <span className="v">
            {edgar ? (
              <a href={edgar} target="_blank" rel="noreferrer">
                {data.secName} (CIK {data.cik})
              </a>
            ) : (
              <span className="muted">No CIK match</span>
            )}
          </span>
        </div>
        <div>
          <span className="k">SEC SIC</span>
          <span className="v">
            {data.sic?.label ? (
              <>
                {formatSicIndustry(data.sic.label)}
                {data.sic.majorGroup && <span className="muted"> — {data.sic.majorGroup}</span>}
                <span className="muted"> ({data.sic.source || "SEC EDGAR submissions"})</span>
              </>
            ) : (
              <span className="muted">{naReason("no_sic") || "No SEC SIC code"}</span>
            )}
          </span>
        </div>
        <div>
          <span className="k">Revenue currency</span>
          <span className="v">{data.ttm.currency || rev?.currency || <span className="muted">N/A</span>}</span>
        </div>
      </div>

      {data.ttm.reason && <p className="na-reason">TTM growth N/A: {naReason(data.ttm.reason)}</p>}
      {rev?.conceptNote && <p className="note">{rev.conceptNote}</p>}

      {quarters.length > 0 ? (
        <div className="table-scroll">
          <table className="quarters">
            <caption>
              Latest {quarters.length} fiscal quarters, newest first
              {currency ? ` · amounts in ${currency} (unconverted)` : ""}
            </caption>
            <thead>
              <tr>
                <th scope="col">Fiscal quarter</th>
                <th scope="col">Reporting period</th>
                <th scope="col" className="num">
                  Revenue
                </th>
                <th scope="col" className="num">
                  Net income
                </th>
                <th scope="col">TTM window</th>
                <th scope="col">How obtained</th>
                <th scope="col">SEC filing</th>
                <th scope="col">Verification</th>
              </tr>
            </thead>
            <tbody>
              {quarters.map((q) => (
                <QuarterRow key={q.end} q={q} currency={currency} earnings={earningsByEnd.get(q.end)} />
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="muted">No quarterly revenue is available for this company.</p>
      )}

      {flags.length > 0 && (
        <ul className="flags">
          {flags.map((f) => (
            <li key={f}>{flagText(f)}</li>
          ))}
        </ul>
      )}

      {rev && rev.candidates.length > 1 && (
        <details className="candidates">
          <summary>Revenue concepts considered ({rev.candidates.length})</summary>
          <table>
            <thead>
              <tr>
                <th scope="col">XBRL concept</th>
                <th scope="col">Latest period</th>
                <th scope="col" className="num">
                  Latest value
                </th>
                <th scope="col">On income statement as</th>
                <th scope="col">Agreement</th>
              </tr>
            </thead>
            <tbody>
              {rev.candidates.map((c) => (
                <tr key={c.concept} className={c.selected ? "selected" : ""}>
                  <td>
                    <code>{shortConcept(c.concept)}</code> {c.selected && <span className="badge ok">Used</span>}
                  </td>
                  <td>{formatDate(c.latestEnd)}</td>
                  <td className="num">{formatMillions(c.latestValue, currency)}</td>
                  <td>{c.statementLabel ?? <span className="muted">—</span>}</td>
                  <td>
                    {c.comparedWith
                      ? c.overlaps === 0
                        ? "No overlapping quarters"
                        : c.disagreements === 0
                          ? `Agrees on ${c.overlaps} quarters`
                          : `Differs on ${c.disagreements} of ${c.overlaps} quarters`
                      : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      )}
    </div>
  );
}
