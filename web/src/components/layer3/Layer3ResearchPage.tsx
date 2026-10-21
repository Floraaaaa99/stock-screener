import { useEffect, useMemo, useState } from "react";
import { loadLayer3Issuer } from "../../api";
import { flagText } from "../../lib/explain";
import { formatCompactMoney, formatDate, formatRatioPercent } from "../../lib/format";
import {
  LAYER3_EXTRACTION_LABEL,
  LAYER3_INPUT_LABEL,
  LAYER3_MODEL_LABEL,
  LAYER3_VERIFICATION_LABEL,
  normalizeCik,
  type Layer3Entry,
} from "../../lib/layer3";
import { formatSicIndustry } from "../../lib/screener";
import {
  LAYER3_RESEARCH_SECTIONS,
  displayAmount,
  displayKind,
  formatPeriodLabel,
  hasConceptScopeMismatch,
  issuerCurrency,
  latestFlowPeriod,
  periodKey,
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
  const overviewPeriods = [
    latestFlowPeriod(row?.metrics?.revenue),
    latestFlowPeriod(row?.metrics?.grossMargin),
    latestFlowPeriod(row?.metrics?.ocf),
    latestFlowPeriod(row?.metrics?.fcf),
  ];
  const sharedOverviewKey = overviewPeriods.every((p) => periodKey(p) && periodKey(p) === periodKey(overviewPeriods[0]))
    ? periodKey(overviewPeriods[0])
    : "";
  const sharedOverviewPeriod = sharedOverviewKey
    ? formatPeriodLabel(overviewPeriods[0])
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

  const industry = row?.sicIndustry || entry?.sicIndustry;
  const industryLabel = (() => {
    const formatted = industry ? formatSicIndustry(industry) : "";
    if (formatted && row?.sicCode && row.sicCode !== "0000" && !formatted.includes(row.sicCode)) {
      return `${formatted} · ${row.sicCode}`;
    }
    return formatted || (row?.sicCode && row.sicCode !== "0000" ? row.sicCode : "N/A");
  })();

  return (
    <section className="layer3 l3-research">
      <div className="panel l3-research-top">
        <header className="l3-research-header">
          <div className="l3-research-head-row">
            <button type="button" className="btn btn-small" onClick={onBack}>
              Back to list
            </button>
            <h2>
              <span className="l3-ticker">{ticker}</span> {name}
            </h2>
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
                    Remove
                  </button>
                )}
              </div>
            )}
          </div>
          <p className="l3-identity">
            {industryLabel}
            {extras.length > 0 ? ` · Also ${extras.join(", ")} (same issuer)` : ""}
            {row?.dataAsOf ? (
              <>
                {" · "}
                <span
                  title="Latest fiscal period-end in this issuer’s Layer 3 file. This is not the site-wide Screener updated time in the page header."
                >
                  Issuer reporting date {formatDate(row.dataAsOf)}
                </span>
              </>
            ) : null}
          </p>
          <details className="l3-data-details">
            <summary>Data details</summary>
            <dl className="l3-meta">
              <div>
                <dt>Source</dt>
                <dd>SEC Company Facts</dd>
              </div>
              <div>
                <dt>Schema / extract</dt>
                <dd>
                  {row?.schemaVersion != null ? `schema ${row.schemaVersion}` : "—"}
                  {row?.extractionVersion != null ? ` / extract ${row.extractionVersion}` : ""}
                </dd>
              </div>
              <div>
                <dt>Extraction</dt>
                <dd>
                  {row?.extractionStatus
                    ? LAYER3_EXTRACTION_LABEL[row.extractionStatus]
                    : state === "ready"
                      ? LAYER3_EXTRACTION_LABEL.pending_analysis
                      : "Loading"}
                </dd>
              </div>
              <div>
                <dt>Verification</dt>
                <dd>
                  {row?.verificationStatus
                    ? LAYER3_VERIFICATION_LABEL[row.verificationStatus]
                    : LAYER3_VERIFICATION_LABEL.not_checked}
                </dd>
              </div>
              <div>
                <dt>Model</dt>
                <dd>{row?.modelApplicability ? LAYER3_MODEL_LABEL[row.modelApplicability] : "—"}</dd>
              </div>
              <div>
                <dt>Inputs</dt>
                <dd>{row?.inputCompleteness ? LAYER3_INPUT_LABEL[row.inputCompleteness] : "—"}</dd>
              </div>
              <div>
                <dt>CIK</dt>
                <dd>{normalized}</dd>
              </div>
              <div>
                <dt>Currency</dt>
                <dd>{currency ?? "—"}</dd>
              </div>
            </dl>
          </details>
          {!entry && (
            <p className="l3-banner is-warn" role="status">
              This company is not on your Layer 3 list. Nothing was added.
            </p>
          )}
          {hasConceptScopeMismatch(row) && (
            <p className="l3-banner is-warn" role="status">
              Concept-scope mismatch: Gross Profit, Cost of Revenue, and Revenue do not share a compatible scope.
              Derived margins and inventory/payables ratios stay suppressed.
            </p>
          )}
          {(row?.flags ?? [])
            .filter((f) => f !== "concept_scope_mismatch" && f !== "financial_institution")
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
          <div className="error-panel" role="alert">
            <h3>Issuer file is not available</h3>
            <p>Could not load <code>layer3/cik/{normalized}.json</code>. Missing values are not replaced with zero.</p>
          </div>
        )}

        {state === "ready" && row && !entry && (
          <div className="l3-empty">
            <h3>Not on your Layer 3 list</h3>
            <p>Open a company from the saved research list. This page does not add issuers automatically.</p>
          </div>
        )}

        {state === "ready" && row && entry && (
          <section className="l3-overview" aria-labelledby="l3-overview-title">
            {row.extractionStatus === "insufficient_facts" && (
              <p className="l3-banner" role="status">
                Insufficient financial facts. Sections render as unavailable rather than fabricated amounts.
              </p>
            )}
            <div className="l3-overview-head">
              <h2 id="l3-overview-title">Financial overview</h2>
              {sharedOverviewPeriod && (
                <p className="muted l3-overview-period">TTM through {sharedOverviewPeriod}</p>
              )}
            </div>
            <div className="l3-cards">
              {(
                [
                  ["Revenue TTM", row.metrics?.revenue, false],
                  ["Gross margin TTM", row.metrics?.grossMargin, true],
                  ["OCF TTM", row.metrics?.ocf, false],
                  ["FCF TTM", row.metrics?.fcf, false],
                ] as const
              ).map(([title, metric, isRatio]) => {
                const empty =
                  displayAmount(metric) == null ||
                  displayKind(metric) === "missing" ||
                  displayKind(metric) === "suppressed";
                const ownPeriod = formatPeriodLabel(latestFlowPeriod(metric));
                const showOwnPeriod = !sharedOverviewPeriod && !!ownPeriod;
                return (
                  <MetricCard
                    key={title}
                    title={title}
                    metric={metric}
                    period={showOwnPeriod ? ownPeriod : null}
                    hint={title === "FCF TTM" ? metric?.formula : undefined}
                    value={
                      empty ? (
                        <Unavailable reason={metric?.reason} />
                      ) : isRatio ? (
                        formatRatioPercent(displayAmount(metric))
                      ) : (
                        formatCompactMoney(displayAmount(metric), currency)
                      )
                    }
                  />
                );
              })}
            </div>
          </section>
        )}
      </div>

      {state === "ready" && row && entry && (
        <>
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
