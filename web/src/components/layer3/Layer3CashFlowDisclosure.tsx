import { useMemo, useState } from "react";
import { formatExactMoney } from "../../lib/format";
import type { Layer3DisclosureGroup, Layer3DisclosureLine, Layer3Row } from "../../types";
import { Unavailable } from "./ResearchChrome";

const FILTERS = [
  { id: "all", label: "All lines" },
  { id: "capex", label: "CapEx" },
  { id: "debtFinancing", label: "Debt financing" },
  { id: "shareRepurchases", label: "Share repurchases" },
  { id: "dividends", label: "Dividends" },
  { id: "acquisitions", label: "Acquisitions" },
] as const;

type FilterId = (typeof FILTERS)[number]["id"];

function kindLabel(kind: string | undefined): string {
  if (kind === "asReported") return "As reported";
  if (kind === "calculated") return "Calculated";
  return "Unavailable";
}

function periodHint(months?: number | null, end?: string | null): string | null {
  if (!months && !end) return null;
  const bits = [months ? `${months}M YTD` : null, end ?? null].filter(Boolean);
  return bits.join(" · ") || null;
}

function amountCell(
  kind: string | undefined,
  value: number | null | undefined,
  currency: string | null,
  reason?: string | null,
  formula?: string | null,
) {
  if (kind === "unavailable" || value == null) {
    return <Unavailable reason={reason ?? "missing_prior_ytd"} />;
  }
  return (
    <span title={formula ?? kindLabel(kind)}>
      {formatExactMoney(value, currency)}
    </span>
  );
}

function visibleLines(group: Layer3DisclosureGroup, filter: FilterId): Layer3DisclosureLine[] {
  if (filter === "all") return group.lines;
  return group.lines.filter((line) => line.role !== "line" || line.identity === filter);
}

export function Layer3CashFlowDisclosure({ row, currency }: { row: Layer3Row; currency: string | null }) {
  const cash = row.disclosures?.cashFlow;
  const [filter, setFilter] = useState<FilterId>("all");
  const identities = cash?.identities ?? {};
  const groups = useMemo(() => cash?.groups ?? [], [cash]);

  if (!cash) {
    return (
      <article className="l3-block is-first">
        <header className="l3-block-head">
          <h3>SEC cash-flow disclosure</h3>
        </header>
        <p className="l3-series-caption">
          The face cash-flow statement has not been extracted for this issuer yet. Standardized
          research metrics below are one US-GAAP tag each and are not a complete disclosure
          breakdown.
        </p>
      </article>
    );
  }

  const filing = cash.filing;
  const period = periodHint(cash.period?.months, cash.period?.end);

  return (
    <article className="l3-block is-first">
      <header className="l3-block-head">
        <h3>SEC cash-flow disclosure</h3>
      </header>
      <p className="l3-series-caption">
        Lines and amounts come from the original cash-flow statement
        {filing?.title ? ` (${filing.title})` : ""}. As reported is the face column
        {period ? ` (${period})` : ""}. Calculated is a standalone quarter from comparable YTD
        filings. Missing prior YTD stays Unavailable, not zero. Section totals are the reported
        totals, not a sum of children.
      </p>
      {cash.status === "stale" && (
        <p className="l3-banner is-warn" role="status">
          Showing the face from {filing?.form ?? "a prior filing"}
          {filing?.filed ? ` filed ${filing.filed}` : ""}. This is not the latest 10-Q/10-K
          {cash.targetAccn ? ` (${cash.targetAccn}` : ""}
          {cash.targetFiled ? ` filed ${cash.targetFiled}` : ""}
          {cash.targetAccn ? ")" : ""}.
        </p>
      )}
      {cash.status === "unavailable" && (
        <p className="l3-banner" role="status">
          The latest 10-Q/10-K cash-flow face could not be read
          {cash.targetAccn ? ` (${cash.targetAccn})` : ""}. Standardized research metrics below
          are one tag each and are not a complete disclosure breakdown.
        </p>
      )}
      <p className="l3-disclosure-links">
        {filing?.statementUrl && (
          <a href={filing.statementUrl} target="_blank" rel="noreferrer">
            Cash-flow statement
          </a>
        )}
        {filing?.indexUrl && (
          <a href={filing.indexUrl} target="_blank" rel="noreferrer">
            SEC filing
          </a>
        )}
        {(cash.noteLinks ?? []).map((link) => (
          <a key={link.url} href={link.url} target="_blank" rel="noreferrer">
            {link.title}
          </a>
        ))}
      </p>
      <div className="l3-view-toggle" role="group" aria-label="Disclosure category filter">
        {FILTERS.map((opt) => (
          <button
            key={opt.id}
            type="button"
            className={`btn btn-small ${filter === opt.id ? "current" : ""}`}
            aria-pressed={filter === opt.id}
            onClick={() => setFilter(opt.id)}
          >
            {opt.label}
          </button>
        ))}
      </div>
      {filter === "capex" && cash.capex?.note && (
        <p className="l3-banner" role="status">
          {cash.capex.note}
        </p>
      )}
      {filter === "acquisitions" && cash.acquisitions?.note && (
        <p className="l3-banner" role="status">
          {cash.acquisitions.note}
        </p>
      )}
      {groups.map((group) => {
        const lines = visibleLines(group, filter);
        const hasMatch = lines.some((line) => line.role === "line");
        if (filter !== "all" && !hasMatch) return null;
        return (
          <details
            key={group.id}
            className="l3-disclosure-group"
            open={filter !== "all" || group.id === "operating" || group.id === "investing" || group.id === "financing"}
          >
            <summary>
              {group.label}
              {group.reportedTotal?.value != null && (
                <span className="l3-disclosure-total">
                  {" "}
                  Reported total {formatExactMoney(group.reportedTotal.value, currency)}
                </span>
              )}
            </summary>
            <div className="l3-disclosure-table-wrap">
              <table className="l3-disclosure-table">
                <caption className="visually-hidden">{group.label} cash-flow lines</caption>
                <thead>
                  <tr>
                    <th scope="col">Disclosed line</th>
                    <th scope="col">As reported</th>
                    <th scope="col">Standalone quarter</th>
                    <th scope="col">Category</th>
                  </tr>
                </thead>
                <tbody>
                  {lines.map((line) => (
                    <tr key={`${line.order}-${line.concept}`} className={`is-${line.role}`}>
                      <th scope="row">
                        {line.label}
                        <div className="l3-disclosure-concept">{line.concept}</div>
                      </th>
                      <td>
                        {line.role === "header" ? (
                          ""
                        ) : (
                          <>
                            <div className="l3-kind">{kindLabel(line.asReported.kind)}</div>
                            {amountCell(line.asReported.kind, line.asReported.value, currency)}
                          </>
                        )}
                      </td>
                      <td>
                        {line.role === "line" ? (
                          <>
                            <div className="l3-kind">{kindLabel(line.standaloneQuarter.kind)}</div>
                            {amountCell(
                              line.standaloneQuarter.kind,
                              line.standaloneQuarter.value,
                              currency,
                              line.standaloneQuarter.reason,
                              line.standaloneQuarter.formula,
                            )}
                          </>
                        ) : (
                          ""
                        )}
                      </td>
                      <td>
                        {line.identity ? identities[line.identity] ?? line.identity : line.role === "line" ? "As disclosed" : ""}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
        );
      })}
    </article>
  );
}

