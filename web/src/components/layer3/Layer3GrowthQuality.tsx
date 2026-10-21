import { useMemo, useState } from "react";
import { fiscalLabel, formatCompactMoney, formatExactMoney, formatPercent } from "../../lib/format";
import {
  flowAmountPoints,
  growthRatePoints,
  latestFlowPeriod,
  pairQuarterGrowth,
  ttmChange,
} from "../../lib/layer3Research";
import type { Layer3Row } from "../../types";
import { MethodNote, MetricCard, Unavailable, ViewToggle } from "./ResearchChrome";
import { SeriesView } from "./SeriesView";

export function Layer3GrowthQuality({ row, currency }: { row: Layer3Row; currency: string | null }) {
  const m = row.metrics;
  const [g1, setG1] = useState<"amount" | "yoy" | "qoq">("amount");
  const [g2, setG2] = useState<"revenue" | "income" | "margin">("revenue");
  const [g3, setG3] = useState<"ttm" | "yoy">("ttm");
  const revenue = m?.revenue;
  const yoy = useMemo(() => pairQuarterGrowth(revenue?.quarters, "yoy", currency), [revenue, currency]);
  const qoq = useMemo(() => pairQuarterGrowth(revenue?.quarters, "qoq", currency), [revenue, currency]);
  const revPeriod = latestFlowPeriod(revenue);
  const periodLabel = revPeriod ? `${fiscalLabel(revPeriod.fiscalYear, revPeriod.fiscalQuarter)} · ${revPeriod.end ?? ""}` : null;

  const g1Series =
    g1 === "amount"
      ? [{ id: "revenue", label: "Revenue", points: flowAmountPoints(revenue) }]
      : [
          {
            id: g1,
            label: g1 === "yoy" ? "Revenue YoY" : "Revenue QoQ",
            points: growthRatePoints(g1 === "yoy" ? yoy : qoq),
          },
        ];

  const g2Series =
    g2 === "revenue"
      ? [
          { id: "revenue", label: "Revenue", points: flowAmountPoints(m?.revenue) },
          { id: "gp", label: "Gross profit", points: flowAmountPoints(m?.grossProfit) },
        ]
      : g2 === "income"
        ? [
            { id: "oi", label: "Operating income", points: flowAmountPoints(m?.operatingIncome) },
            { id: "ni", label: "Net income", points: flowAmountPoints(m?.netIncome) },
          ]
        : [
            { id: "gm", label: "Gross margin", points: flowAmountPoints(m?.grossMargin) },
            { id: "om", label: "Operating margin", points: flowAmountPoints(m?.operatingMargin) },
            { id: "nm", label: "Net margin", points: flowAmountPoints(m?.netMargin) },
          ];

  const g3Metrics = [
    { id: "revenue", label: "Revenue", metric: m?.revenue },
    { id: "oi", label: "Operating income", metric: m?.operatingIncome },
    { id: "ni", label: "Net income", metric: m?.netIncome },
  ] as const;

  return (
    <section id="growth" className="l3-section panel">
      <div className="l3-section-head">
        <h2 title="Revenue, profitability, and operating performance over the latest standalone quarters. Growth rates are not classified as good or bad.">
          Growth Quality
        </h2>
      </div>

      <article className="l3-block is-first">
        <header className="l3-block-head">
          <h3>G1 — Revenue trend</h3>
          <div className="l3-block-tools">
            <MethodNote>
              Latest 8 standalone fiscal quarters. YoY pairs the same fiscal quarter last year. QoQ pairs the previous
              standalone quarter. Missing quarters stay unavailable and are not replaced with zero. A zero or negative
              comparison base is Unavailable; the dollar change is in the table. YoY/QoQ pairing is presentation-only.
            </MethodNote>
            <ViewToggle
              label="Revenue view"
              value={g1}
              onChange={setG1}
              options={[
                { id: "amount", label: "Amount" },
                { id: "yoy", label: "YoY %" },
                { id: "qoq", label: "QoQ %" },
              ]}
            />
          </div>
        </header>
        <SeriesView
          series={g1Series}
          kind={g1 === "amount" ? "bar" : "line"}
          unit={g1 === "amount" ? "money" : "percent"}
          currency={currency}
          tableCaption="Revenue history"
        />
        {g1 !== "amount" && (
          <p className="muted">
            Dollar changes when a rate is unavailable:{" "}
            {(g1 === "yoy" ? yoy : qoq)
              .filter((p) => p.rate == null && p.absoluteChange != null)
              .slice(-3)
              .map((p) => `${fiscalLabel(p.current.fiscalYear, p.current.fiscalQuarter)} ${formatExactMoney(p.absoluteChange, currency)}`)
              .join(" · ") || "none in the latest quarters"}
            .
          </p>
        )}
      </article>

      <article className="l3-block">
        <header className="l3-block-head">
          <h3>G2 — Profitability</h3>
          <div className="l3-block-tools">
            <MethodNote>
              Related amounts share one axis. Margins are a separate percent view so dollars and ratios are not mixed.
              Derived margins stay unavailable when inputs conflict.
            </MethodNote>
            <ViewToggle
              label="Profitability view"
              value={g2}
              onChange={setG2}
              options={[
                { id: "revenue", label: "Revenue & GP" },
                { id: "income", label: "Operating results" },
                { id: "margin", label: "Margin" },
              ]}
            />
          </div>
        </header>
        <SeriesView series={g2Series} kind="line" unit={g2 === "margin" ? "ratio" : "money"} currency={currency} />
      </article>

      <article className="l3-block">
        <header className="l3-block-head">
          <h3>G3 — Growth efficiency</h3>
          <div className="l3-block-tools">
            <MethodNote>
              TTM year-over-year comes from the issuer file. When the comparison base is not positive, the percentage
              is withheld and the dollar change is shown instead. Quarterly YoY is a UI pairing of corresponding
              fiscal quarters.
            </MethodNote>
            <ViewToggle
              label="Growth efficiency view"
              value={g3}
              onChange={setG3}
              options={[
                { id: "ttm", label: "TTM YoY" },
                { id: "yoy", label: "Quarterly YoY" },
              ]}
            />
          </div>
        </header>
        {g3 === "ttm" ? (
          <>
            <div className="l3-cards">
              {g3Metrics.map((item) => {
                const change = ttmChange(item.metric);
                return (
                  <MetricCard
                    key={item.id}
                    title={`${item.label} TTM YoY`}
                    metric={item.metric}
                    period={periodLabel}
                    value={
                      change.rate != null ? (
                        formatPercent(change.rate)
                      ) : change.absoluteChange != null ? (
                        <span>
                          <Unavailable reason={change.reason} />
                          <span className="muted"> · Δ {formatCompactMoney(change.absoluteChange, currency)}</span>
                        </span>
                      ) : (
                        <Unavailable reason={change.reason} />
                      )
                    }
                  />
                );
              })}
            </div>
            <SeriesView
              series={[
                {
                  id: "ttm-yoy",
                  label: "TTM YoY %",
                  points: g3Metrics.map((item) => ({
                    key: item.id,
                    label: item.label,
                    value: ttmChange(item.metric).rate,
                    reason: ttmChange(item.metric).reason,
                  })),
                },
              ]}
              kind="bar"
              unit="percent"
              currency={currency}
            />
          </>
        ) : (
          <SeriesView
            series={g3Metrics.map((item) => ({
              id: item.id,
              label: item.label,
              points: growthRatePoints(pairQuarterGrowth(item.metric?.quarters, "yoy", currency)),
            }))}
            kind="line"
            unit="percent"
            currency={currency}
          />
        )}
      </article>
    </section>
  );
}
