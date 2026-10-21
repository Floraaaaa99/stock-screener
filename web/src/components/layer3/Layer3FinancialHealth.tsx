import { useState } from "react";
import { fiscalLabel, formatCompactMoney, formatDate, formatRatio } from "../../lib/format";
import { displayAmount, displayKind, flowAmountPoints, latestFlowPeriod, stockHistoryPoints, ttmPoints } from "../../lib/layer3Research";
import type { Layer3Row } from "../../types";
import { MethodNote, MetricCard, Unavailable, ViewToggle } from "./ResearchChrome";
import { SeriesView } from "./SeriesView";

export function Layer3FinancialHealth({ row, currency }: { row: Layer3Row; currency: string | null }) {
  const m = row.metrics;
  const [f1, setF1] = useState<"quarter" | "ttm" | "conversion">("quarter");
  const [f2, setF2] = useState<"quarter" | "ttm" | "margin">("quarter");
  const [f3, setF3] = useState<"debt" | "current">("debt");
  const period = latestFlowPeriod(m?.ocf);
  const periodLabel = period ? `${fiscalLabel(period.fiscalYear, period.fiscalQuarter)} · ${period.end ?? ""}` : null;

  return (
    <section id="health" className="l3-section panel">
      <div className="l3-section-head">
        <h2 title="Earnings-to-cash conversion, reinvestment, liquidity, and debt. Balance-sheet figures are snapshots on a filing date and are never summed into a TTM.">
          Financial Health
        </h2>
      </div>

      <article className="l3-block is-first">
        <header className="l3-block-head">
          <h3>F1 — Earnings vs cash</h3>
          <div className="l3-block-tools">
            <MethodNote>
              Net income and operating cash flow on matching fiscal period ends. Cash conversion is OCF / Net Income
              when the base is positive.
            </MethodNote>
            <ViewToggle
            label="Earnings vs cash view"
            value={f1}
            onChange={setF1}
            options={[
              { id: "quarter", label: "Quarterly" },
              { id: "ttm", label: "TTM" },
              { id: "conversion", label: "Cash conversion" },
            ]}
            />
          </div>
        </header>
        {f1 === "quarter" && (
          <SeriesView
            series={[
              { id: "ni", label: "Net income", points: flowAmountPoints(m?.netIncome) },
              { id: "ocf", label: "Operating cash flow", points: flowAmountPoints(m?.ocf) },
            ]}
            kind="bar"
            unit="money"
            currency={currency}
          />
        )}
        {f1 === "ttm" && (
          <SeriesView
            series={[
              { id: "ni", label: "Net income TTM", points: ttmPoints(m?.netIncome) },
              { id: "ocf", label: "OCF TTM", points: ttmPoints(m?.ocf) },
            ]}
            kind="bar"
            unit="money"
            currency={currency}
          />
        )}
        {f1 === "conversion" && (
          <SeriesView
            series={[{ id: "cc", label: "Cash conversion", points: flowAmountPoints(m?.cashConversion) }]}
            kind="line"
            unit="ratio"
            currency={currency}
          />
        )}
      </article>

      <article className="l3-block">
        <header className="l3-block-head">
          <h3>F2 — Cash flow and reinvestment</h3>
          <div className="l3-block-tools">
            <MethodNote>
              Free cash flow is derived as OCF minus the magnitude of capital expenditures (CapEx stored as a positive
              outflow). This is the pipeline definition, not a filing face line.
            </MethodNote>
            <ViewToggle
            label="Cash flow view"
            value={f2}
            onChange={setF2}
            options={[
              { id: "quarter", label: "Quarterly" },
              { id: "ttm", label: "TTM" },
              { id: "margin", label: "FCF margin" },
            ]}
            />
          </div>
        </header>
        {f2 === "quarter" && (
          <SeriesView
            series={[
              { id: "ocf", label: "OCF", points: flowAmountPoints(m?.ocf) },
              { id: "capex", label: "CapEx (outflow)", points: flowAmountPoints(m?.capex) },
              { id: "fcf", label: "FCF", points: flowAmountPoints(m?.fcf) },
            ]}
            kind="bar"
            unit="money"
            currency={currency}
          />
        )}
        {f2 === "ttm" && (
          <SeriesView
            series={[
              { id: "ocf", label: "OCF TTM", points: ttmPoints(m?.ocf) },
              { id: "capex", label: "CapEx TTM", points: ttmPoints(m?.capex) },
              { id: "fcf", label: "FCF TTM", points: ttmPoints(m?.fcf) },
            ]}
            kind="bar"
            unit="money"
            currency={currency}
          />
        )}
        {f2 === "margin" && (
          <SeriesView
            series={[{ id: "fcfm", label: "FCF margin", points: flowAmountPoints(m?.fcfMargin) }]}
            kind="line"
            unit="ratio"
            currency={currency}
          />
        )}
      </article>

      <article className="l3-block">
        <header className="l3-block-head">
          <h3>F3 — Liquidity and debt</h3>
          <div className="l3-block-tools">
            <MethodNote>
              Historical balance-sheet snapshots, each labeled with its date. Current ratio is a latest-only derived
              value — it is not computed for earlier dates in the browser. These series are not TTM.
            </MethodNote>
            <ViewToggle
            label="Balance-sheet view"
            value={f3}
            onChange={setF3}
            options={[
              { id: "debt", label: "Cash and debt" },
              { id: "current", label: "Current accounts" },
            ]}
            />
          </div>
        </header>
        <div className="l3-cards">
          {(
            [
              ["Cash", m?.cash, m?.cash?.end],
              ["Short-term debt", m?.shortTermDebt, m?.shortTermDebt?.end],
              ["Long-term debt", m?.longTermDebt, m?.longTermDebt?.end],
              ["Total debt", m?.totalDebt, m?.totalDebt?.end],
              ["Net debt", m?.netDebt, m?.netDebt?.end],
              ["Current assets", m?.currentAssets, m?.currentAssets?.end],
              ["Current liabilities", m?.currentLiabilities, m?.currentLiabilities?.end],
            ] as const
          ).map(([title, metric, end]) => (
            <MetricCard
              key={title}
              title={title}
              metric={metric}
              period={end ? `As of ${formatDate(end)}` : periodLabel}
              value={formatCompactMoney(displayAmount(metric), currency)}
            />
          ))}
          <MetricCard
            title="Current ratio"
            metric={m?.currentRatio}
            period={m?.currentRatio?.end ? `As of ${formatDate(m.currentRatio.end)}` : periodLabel}
            value={
              displayKind(m?.currentRatio) === "missing" || displayKind(m?.currentRatio) === "suppressed" ? (
                <Unavailable reason={m?.currentRatio?.reason} />
              ) : (
                formatRatio(displayAmount(m?.currentRatio))
              )
            }
          />
        </div>
        <SeriesView
          series={
            f3 === "debt"
              ? [
                  { id: "cash", label: "Cash", points: stockHistoryPoints(m?.cash) },
                  { id: "total", label: "Total debt", points: stockHistoryPoints(m?.totalDebt) },
                  { id: "net", label: "Net debt", points: stockHistoryPoints(m?.netDebt) },
                ]
              : [
                  { id: "ca", label: "Current assets", points: stockHistoryPoints(m?.currentAssets) },
                  { id: "cl", label: "Current liabilities", points: stockHistoryPoints(m?.currentLiabilities) },
                ]
          }
          kind="line"
          unit="money"
          currency={currency}
        />
      </article>
    </section>
  );
}
