import { useEffect, useMemo, useState } from "react";
import { loadLayer3Issuer } from "../../api";
import { flagText } from "../../lib/explain";
import { fiscalLabel, formatCompactMoney, formatDate, formatRatioPercent } from "../../lib/format";
import { normalizeCik, statusLines, type Layer3Entry } from "../../lib/layer3";
import { formatSicIndustry } from "../../lib/screener";
import {
  LAYER3_RESEARCH_SECTIONS,
  displayAmount,
  displayKind,
  hasConceptScopeMismatch,
  issuerCurrency,
  latestFlowPeriod,
} from "../../lib/layer3Research";
import type { Layer3Row } from "../../types";
import { Layer3FinancialHealth } from "./Layer3FinancialHealth";
import { Layer3GrowthQuality } from "./Layer3GrowthQuality";
import { Layer3WorkingCapital } from "./Layer3WorkingCapital";
import { MetricCard, Unavailable } from "./ResearchChrome";

interface Props {
  cik: string;
  entries: Layer3Entry[];
  onBack: () => void;
  onRemove: (issuerId: string) => void;
}

export function Layer3ResearchPage({ cik, entries, onBack, onRemove }: Props) {
  const normalized = normalizeCik(cik);
  const entry = useMemo(
    () => entries.find((e) => normalizeCik(e.cik) === normalized) ?? null,
    [entries, normalized],
  );
  const [row, setRow] = useState<Layer3Row | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const [pendingRemove, setPendingRemove] = useState(false);
  const [active, setActive] = useState<(typeof LAYER3_RESEARCH_SECTIONS)[number]["id"]>("growth");

  useEffect(() => {
    if (!normalized) {
      setRow(null);
      setState("error");
      return;
    }
    let cancelled = false;
    setState("loading");
    loadLayer3Issuer(normalized).then((next) => {
      if (cancelled) return;
      setRow(next);
      setState(next ? "ready" : "error");
    });
    return () => {
      cancelled = true;
    };
  }, [normalized]);

  useEffect(() => {
    const ids = LAYER3_RESEARCH_SECTIONS.map((s) => s.id);
    const nodes = ids.map((id) => document.getElementById(id)).filter((n): n is HTMLElement => n != null);
    if (nodes.length === 0) return;
    const observer = new IntersectionObserver(
      (entriesObs) => {
        const visible = entriesObs
          .filter((e) => e.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
        const id = visible[0]?.target.id;
        if (id === "growth" || id === "health" || id === "working-capital") setActive(id);
      },
      { rootMargin: "-20% 0px -60% 0px", threshold: 0.1 },
    );
    for (const node of nodes) observer.observe(node);
    return () => observer.disconnect();
  }, [state]);

  const ticker = row?.displayTicker ?? entry?.displayTicker ?? "—";
  const name = row?.name ?? entry?.name ?? ticker;
  const currency = issuerCurrency(row);
  const extras = (row?.tickers ?? entry?.tickers ?? []).filter((t) => t !== ticker);
  const period = latestFlowPeriod(row?.metrics?.revenue ?? row?.metrics?.ocf);
  const overviewPeriod = period
    ? `${fiscalLabel(period.fiscalYear, period.fiscalQuarter)} · ${period.end ?? ""}`
    : row?.dataAsOf
      ? formatDate(row.dataAsOf)
      : null;

  const scrollTo = (id: (typeof LAYER3_RESEARCH_SECTIONS)[number]["id"]) => {
    setActive(id);
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  if (!normalized) {
    return (
      <section className="layer3">
        <div className="panel error-panel" role="alert">
          <h2>Invalid issuer</h2>
          <p>Layer 3 research requires a canonical CIK. Zero and unusable CIKs are not opened.</p>
          <button type="button" className="btn" onClick={onBack}>
            Back to Layer 3 list
          </button>
        </div>
      </section>
    );
  }

  return (
    <section className="layer3 l3-research">
      <header className="panel l3-research-header">
        <div className="l3-research-head-row">
          <button type="button" className="btn btn-small" onClick={onBack}>
            Back to Layer 3 list
          </button>
          {entry && (
            <div className="layer3-remove">
              {pendingRemove ? (
                <div className="remove-confirm">
                  <span className="muted">Remove {ticker}?</span>
                  <button
                    type="button"
                    className="btn btn-small danger"
                    onClick={() => {
                      onRemove(entry.issuerId);
                      setPendingRemove(false);
                    }}
                  >
                    Confirm remove
                  </button>
                  <button type="button" className="btn btn-small" onClick={() => setPendingRemove(false)}>
                    Cancel
                  </button>
                </div>
              ) : (
                <button type="button" className="btn btn-small" onClick={() => setPendingRemove(true)}>
                  Remove from Layer 3
                </button>
              )}
            </div>
          )}
        </div>
        <h2>
          <span className="l3-ticker">{ticker}</span> {name}
        </h2>
        {extras.length > 0 && <p className="share-class-note">Also {extras.join(", ")} — same SEC issuer</p>}
        <dl className="l3-meta">
          <div>
            <dt>Industry / SIC</dt>
            <dd>
              {(() => {
                const industry = row?.sicIndustry || entry?.sicIndustry;
                const formatted = industry ? formatSicIndustry(industry) : "";
                if (formatted && row?.sicCode && row.sicCode !== "0000" && !formatted.includes(row.sicCode)) {
                  return `${formatted} · ${row.sicCode}`;
                }
                return formatted || (row?.sicCode && row.sicCode !== "0000" ? row.sicCode : "N/A");
              })()}
            </dd>
          </div>
          <div>
            <dt>Latest reporting date</dt>
            <dd>{row?.dataAsOf ? formatDate(row.dataAsOf) : "N/A"}</dd>
          </div>
          <div>
            <dt>Data source</dt>
            <dd>
              SEC Company Facts
              {row?.schemaVersion != null ? ` · schema ${row.schemaVersion}` : ""}
              {row?.extractionVersion != null ? ` / extract ${row.extractionVersion}` : ""}
            </dd>
          </div>
        </dl>
        <ul className="layer3-status-stack detail-status">
          {statusLines(row, state === "ready" || state === "error").map((line) => (
            <li key={line.kind} className={`layer3-status is-${line.kind}`} title={line.title}>
              {line.label}
            </li>
          ))}
        </ul>
        {!entry && (
          <p className="l3-banner is-warn" role="status">
            This company is not on your Layer 3 list. Nothing was added.
          </p>
        )}
        {row?.modelApplicability === "not_applicable" && (
          <p className="l3-banner" role="status">
            Corporate FCF and net-debt definitions are not applicable for this issuer
            {row.flags?.includes("financial_institution") ? " (financial-institution SIC)" : ""}. Extracted figures
            may still appear; they are not a scoring result.
          </p>
        )}
        {hasConceptScopeMismatch(row) && (
          <p className="l3-banner is-warn" role="status">
            Concept-scope mismatch: Gross Profit, Cost of Revenue, and Revenue do not share a compatible scope.
            Derived margins and inventory/payables ratios stay suppressed. This is a data-quality flag, not an
            investment rating.
          </p>
        )}
        {(row?.flags ?? [])
          .filter((f) => f !== "concept_scope_mismatch")
          .filter((f) => !(f === "financial_institution" && row?.modelApplicability === "not_applicable"))
          .map((f) => (
            <p key={f} className="l3-banner" role="status">
              {flagText(f)}
            </p>
          ))}
      </header>

      {state === "loading" && (
        <p className="detail-loading" role="status">
          <span className="spinner" aria-hidden="true" /> Loading issuer file for CIK {normalized}…
        </p>
      )}

      {state === "error" && (
        <div className="panel error-panel" role="alert">
          <h3>Issuer file is not available</h3>
          <p>Could not load <code>layer3/cik/{normalized}.json</code>. Missing values are not replaced with zero.</p>
          <button type="button" className="btn" onClick={onBack}>
            Back to Layer 3 list
          </button>
        </div>
      )}

      {state === "ready" && row && !entry && (
        <div className="panel l3-empty">
          <h3>Not on your Layer 3 list</h3>
          <p>Open a company from the saved research list. This page does not add issuers automatically.</p>
          <button type="button" className="btn current" onClick={onBack}>
            Back to Layer 3 list
          </button>
        </div>
      )}

      {state === "ready" && row && entry && (
        <>
          {row.extractionStatus === "insufficient_facts" && (
            <p className="l3-banner" role="status">
              Insufficient financial facts. The three research sections render with unavailable metrics rather than
              fabricated amounts.
            </p>
          )}

          <section className="panel l3-overview" aria-labelledby="l3-overview-title">
            <h2 id="l3-overview-title">Financial overview</h2>
            <div className="l3-cards">
              <MetricCard
                title="Revenue TTM"
                metric={row.metrics?.revenue}
                period={overviewPeriod}
                value={
                  displayAmount(row.metrics?.revenue) == null ? (
                    <Unavailable reason={row.metrics?.revenue?.reason} />
                  ) : (
                    formatCompactMoney(displayAmount(row.metrics?.revenue), currency)
                  )
                }
              />
              <MetricCard
                title="Gross margin TTM"
                metric={row.metrics?.grossMargin}
                period={overviewPeriod}
                value={
                  displayKind(row.metrics?.grossMargin) === "missing" ||
                  displayKind(row.metrics?.grossMargin) === "suppressed" ||
                  displayAmount(row.metrics?.grossMargin) == null ? (
                    <Unavailable reason={row.metrics?.grossMargin?.reason} />
                  ) : (
                    formatRatioPercent(displayAmount(row.metrics?.grossMargin))
                  )
                }
              />
              <MetricCard
                title="OCF TTM"
                metric={row.metrics?.ocf}
                period={overviewPeriod}
                value={
                  displayAmount(row.metrics?.ocf) == null ? (
                    <Unavailable reason={row.metrics?.ocf?.reason} />
                  ) : (
                    formatCompactMoney(displayAmount(row.metrics?.ocf), currency)
                  )
                }
              />
              <MetricCard
                title="FCF TTM"
                metric={row.metrics?.fcf}
                period={overviewPeriod}
                hint={row.metrics?.fcf?.formula}
                value={
                  displayAmount(row.metrics?.fcf) == null ? (
                    <Unavailable reason={row.metrics?.fcf?.reason} />
                  ) : (
                    formatCompactMoney(displayAmount(row.metrics?.fcf), currency)
                  )
                }
              />
            </div>
          </section>

          <nav className="l3-sticky-nav" aria-label="Research sections">
            {LAYER3_RESEARCH_SECTIONS.map((section) => (
              <a
                key={section.id}
                href={`#${section.id}`}
                className={active === section.id ? "on" : ""}
                onClick={(ev) => {
                  ev.preventDefault();
                  scrollTo(section.id);
                }}
              >
                {section.label}
              </a>
            ))}
          </nav>

          <Layer3GrowthQuality row={row} currency={currency} />
          <Layer3FinancialHealth row={row} currency={currency} />
          <Layer3WorkingCapital row={row} currency={currency} />
        </>
      )}
    </section>
  );
}
