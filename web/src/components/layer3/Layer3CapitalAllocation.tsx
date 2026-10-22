import { useState } from "react";
import { fiscalLabel, formatCompactMoney } from "../../lib/format";
import {
  capitalLineTitle,
  cashReconciliationState,
  chartableFlowPoints,
  displayAmount,
  displayKind,
  latestFlowPeriod,
  type MetricKind,
} from "../../lib/layer3Research";
import type { Layer3DerivedMetric, Layer3FlowMetric, Layer3Row } from "../../types";
import { Layer3CashFlowDisclosure } from "./Layer3CashFlowDisclosure";
import { MethodNote, MetricCard, Unavailable, ViewToggle } from "./ResearchChrome";
import { SeriesView } from "./SeriesView";

function metricHint(metric: MetricKind | null | undefined): string | null {
  if (!metric) return null;
  if ("scopeNote" in metric && metric.scopeNote) return metric.scopeNote;
  return metric.formula ?? null;
}

function moneyCard(
  title: string,
  metric: MetricKind | null | undefined,
  currency: string | null,
  period: string | null,
  hint?: string | null,
) {
  const empty =
    displayAmount(metric) == null || displayKind(metric) === "missing" || displayKind(metric) === "suppressed";
  return (
    <MetricCard
      title={title}
      metric={metric}
      period={period}
      hint={hint ?? metricHint(metric)}
      value={empty ? <Unavailable reason={metric?.reason} /> : formatCompactMoney(displayAmount(metric), currency)}
    />
  );
}

export function Layer3CapitalAllocation({ row, currency }: { row: Layer3Row; currency: string | null }) {
  const m = row.metrics;
  const [horizon, setHorizon] = useState<"quarter" | "ttm">("quarter");
  const [block, setBlock] = useState<"inflows" | "outflows" | "sections">("inflows");
  const period = latestFlowPeriod(m?.ocf) ?? latestFlowPeriod(m?.investingCf) ?? latestFlowPeriod(m?.financingCf);
  const periodLabel = period ? `${fiscalLabel(period.fiscalYear, period.fiscalQuarter)} · ${period.end ?? ""}` : null;
  const pointsFor = (metric: Layer3FlowMetric | Layer3DerivedMetric | null | undefined) =>
    chartableFlowPoints(metric, horizon);
  const recon = cashReconciliationState(m?.cashCfIdentity);
  const issuanceTitle = capitalLineTitle("issuance", m?.debtIssuance);
  const repaymentTitle = capitalLineTitle("repayment", m?.debtRepayment);
  const netTitle = capitalLineTitle("net", m?.netDebtFinancing);

  return (
    <section id="capital-allocation" className="l3-section panel">
      <div className="l3-section-head">
        <h2 title="SEC cash-flow face lines first. Standardized research cards below are one Company Facts tag each and are not complete disclosure totals.">
          Capital Allocation & Cash Uses
        </h2>
      </div>

      <Layer3CashFlowDisclosure row={row} currency={currency} />

      <article className="l3-block">
        <header className="l3-block-head">
          <h3>Standardized research metrics (one tag each)</h3>
          <div className="l3-block-tools">
            <MethodNote>
              These cards are one US-GAAP Company Facts tag per category. They are not a complete SEC cash-flow
              disclosure and may omit other face lines. Investing CF and Financing CF are statement totals, not sums
              of the child cards. CapEx is the same F2 series. Missing stays unavailable, never zero.
            </MethodNote>
            <ViewToggle
              label="Capital allocation horizon"
              value={horizon}
              onChange={setHorizon}
              options={[
                { id: "quarter", label: "Quarterly" },
                { id: "ttm", label: "TTM" },
              ]}
            />
            <ViewToggle
              label="Capital allocation series"
              value={block}
              onChange={setBlock}
              options={[
                { id: "inflows", label: "Inflows" },
                { id: "outflows", label: "Outflows" },
                { id: "sections", label: "Investing / financing" },
              ]}
            />
          </div>
        </header>
        <div className="l3-cards">
          {moneyCard(issuanceTitle, m?.debtIssuance, currency, periodLabel, m?.debtIssuance?.scopeNote)}
          {moneyCard(repaymentTitle, m?.debtRepayment, currency, periodLabel, m?.debtRepayment?.scopeNote)}
          {moneyCard(netTitle, m?.netDebtFinancing, currency, periodLabel, m?.netDebtFinancing?.scopeNote)}
          {moneyCard("Equity issuance", m?.equityIssuance, currency, periodLabel)}
          {moneyCard("Asset sales", m?.assetSales, currency, periodLabel)}
          {moneyCard("Share repurchases", m?.shareRepurchases, currency, periodLabel)}
          {moneyCard("Dividends paid", m?.dividendsPaid, currency, periodLabel)}
          {moneyCard("Acquisitions", m?.acquisitions, currency, periodLabel)}
          {moneyCard("CapEx (same as F2)", m?.capex, currency, periodLabel, m?.capex?.formula)}
          {moneyCard("Investing CF", m?.investingCf, currency, periodLabel)}
          {moneyCard("Financing CF", m?.financingCf, currency, periodLabel)}
        </div>
        {block === "inflows" && (
          <SeriesView
            series={[
              { id: "issuance", label: issuanceTitle, points: pointsFor(m?.debtIssuance) },
              { id: "equity", label: "Equity issuance", points: pointsFor(m?.equityIssuance) },
              { id: "assets", label: "Asset sales", points: pointsFor(m?.assetSales) },
            ]}
            kind="bar"
            unit="money"
            currency={currency}
            caption="Inflow lines are separate SEC tags. A net financing tag is never charted as gross issuance."
          />
        )}
        {block === "outflows" && (
          <SeriesView
            series={[
              { id: "repay", label: repaymentTitle, points: pointsFor(m?.debtRepayment) },
              { id: "buyback", label: "Share repurchases", points: pointsFor(m?.shareRepurchases) },
              { id: "div", label: "Dividends paid", points: pointsFor(m?.dividendsPaid) },
              { id: "acq", label: "Acquisitions", points: pointsFor(m?.acquisitions) },
            ]}
            kind="bar"
            unit="money"
            currency={currency}
            caption="Outflow magnitudes are not added together here. CapEx remains the F2 series."
          />
        )}
        {block === "sections" && (
          <SeriesView
            series={[
              { id: "inv", label: "Investing CF", points: pointsFor(m?.investingCf) },
              { id: "fin", label: "Financing CF", points: pointsFor(m?.financingCf) },
              { id: "netdebt", label: netTitle, points: pointsFor(m?.netDebtFinancing) },
            ]}
            kind="bar"
            unit="money"
            currency={currency}
            caption="Section totals are reported net investing and financing lines, not a sum of the child cards."
          />
        )}
      </article>

      <article className="l3-block">
        <header className="l3-block-head">
          <h3>Cash-flow reconciliation</h3>
          <MethodNote>
            OCF + investing CF + financing CF is compared with the cash-flow statement change in cash. F3 Cash
            (CashAndCashEquivalentsAtCarryingValue) is a balance-sheet stock and may exclude restricted cash; it is
            never the reconciling amount. If the cash definition or period is not comparable, the result is
            Unavailable — not a reconciliation failure.
          </MethodNote>
        </header>
        {recon === "unavailable" && (
          <p className="l3-banner" role="status">
            Cash-flow reconciliation is unavailable. F3 cash was not substituted.
          </p>
        )}
        {recon === "mismatch" && (
          <p className="l3-banner is-warn" role="status">
            Comparable cash-flow totals and the cash-change line disagree. Values are preserved; this is not an F3 cash
            comparison.
          </p>
        )}
        <div className="l3-cards">
          {moneyCard("OCF (same as F2)", m?.ocf, currency, periodLabel)}
          {moneyCard("Investing CF", m?.investingCf, currency, periodLabel)}
          {moneyCard("Financing CF", m?.financingCf, currency, periodLabel)}
          {moneyCard("FX on cash", m?.fxOnCash, currency, periodLabel)}
          {moneyCard("Reported CF cash change", m?.cashChangeCf, currency, periodLabel)}
          <MetricCard
            title="Reconstructed cash change"
            metric={m?.cashCfIdentity}
            period={periodLabel}
            hint={m?.cashCfIdentity?.formula ?? m?.cashCfIdentity?.verificationNote}
            value={
              recon === "unavailable" ? (
                <Unavailable reason={m?.cashCfIdentity?.reason} />
              ) : (
                formatCompactMoney(displayAmount(m?.cashCfIdentity), currency)
              )
            }
          />
        </div>
      </article>
    </section>
  );
}
