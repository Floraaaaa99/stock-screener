import { useState } from "react";
import { formatCompactMoney, formatDate, formatDays, formatPercent } from "../../lib/format";
import { displayAmount, displayKind, flowAmountPoints, stockHistoryPoints } from "../../lib/layer3Research";
import type { Layer3Row } from "../../types";
import { MetricCard, Unavailable, ViewToggle } from "./ResearchChrome";
import { SeriesView } from "./SeriesView";

export function Layer3WorkingCapital({ row, currency }: { row: Layer3Row; currency: string | null }) {
  const m = row.metrics;
  const [w1, setW1] = useState<"ar" | "revenue">("ar");
  const [w2, setW2] = useState<"inventory" | "cogs">("inventory");
  const inventoryKind = displayKind(m?.inventory);
  const inventoryNA = inventoryKind === "not_applicable";

  return (
    <section id="working-capital" className="l3-section panel">
      <h2>Working Capital</h2>
      <p className="muted">
        Whether growth requires more receivables, inventory, and operating working capital. Days-outstanding, stock
        YoY, OWC, and CCC are latest-only pipeline values — this page does not invent histories for them.
      </p>

      <article className="l3-block">
        <header className="l3-block-head">
          <div>
            <h3>W1 — Receivables and revenue</h3>
            <p className="muted">
              Accounts receivable is a balance-sheet stock; revenue is a period flow. They are charted separately so
              they are not treated as equivalent.
            </p>
          </div>
          <ViewToggle
            label="Receivables view"
            value={w1}
            onChange={setW1}
            options={[
              { id: "ar", label: "Accounts receivable" },
              { id: "revenue", label: "Revenue" },
            ]}
          />
        </header>
        <div className="l3-cards">
          <MetricCard
            title="AR YoY"
            metric={m?.arYoy}
            period={m?.arYoy?.end ? `As of ${formatDate(m.arYoy.end)}` : null}
            value={displayAmount(m?.arYoy) == null ? <Unavailable reason={m?.arYoy?.reason} /> : formatPercent(displayAmount(m?.arYoy))}
          />
          <MetricCard
            title="DSO"
            metric={m?.dso}
            hint={m?.dso?.formula}
            value={displayAmount(m?.dso) == null ? <Unavailable reason={m?.dso?.reason} /> : formatDays(displayAmount(m?.dso))}
          />
        </div>
        <SeriesView
          series={
            w1 === "ar"
              ? [{ id: "ar", label: "Accounts receivable", points: stockHistoryPoints(m?.accountsReceivable) }]
              : [{ id: "rev", label: "Revenue", points: flowAmountPoints(m?.revenue) }]
          }
          kind="bar"
          unit="money"
          currency={currency}
          caption={w1 === "ar" ? "Balance-sheet snapshots, not a TTM." : "Standalone quarterly revenue."}
        />
      </article>

      <article className="l3-block">
        <header className="l3-block-head">
          <div>
            <h3>W2 — Inventory and COGS</h3>
            <p className="muted">
              Missing inventory is not shown as zero. If inventory is not applicable to the reporting model, that
              state is shown explicitly.
            </p>
          </div>
          {!inventoryNA && (
            <ViewToggle
              label="Inventory view"
              value={w2}
              onChange={setW2}
              options={[
                { id: "inventory", label: "Inventory" },
                { id: "cogs", label: "COGS" },
              ]}
            />
          )}
        </header>
        {inventoryNA ? (
          <div className="l3-na-state">
            <p>
              <strong>Not applicable.</strong> No inventory concept is present in this issuer’s Company Facts.
            </p>
            <MetricCard title="Inventory" metric={m?.inventory} value={<Unavailable reason={m?.inventory?.reason} />} />
            <MetricCard title="DIO" metric={m?.dio} value={<Unavailable reason={m?.dio?.reason} />} />
          </div>
        ) : (
          <>
            <div className="l3-cards">
              <MetricCard
                title="Inventory YoY"
                metric={m?.inventoryYoy}
                period={m?.inventoryYoy?.end ? `As of ${formatDate(m.inventoryYoy.end)}` : null}
                value={
                  displayAmount(m?.inventoryYoy) == null ? (
                    <Unavailable reason={m?.inventoryYoy?.reason} />
                  ) : (
                    formatPercent(displayAmount(m?.inventoryYoy))
                  )
                }
              />
              <MetricCard
                title="DIO"
                metric={m?.dio}
                value={displayAmount(m?.dio) == null ? <Unavailable reason={m?.dio?.reason} /> : formatDays(displayAmount(m?.dio))}
              />
              <MetricCard
                title="Latest inventory"
                metric={m?.inventory}
                period={m?.inventory?.end ? `As of ${formatDate(m.inventory.end)}` : null}
                value={formatCompactMoney(displayAmount(m?.inventory), currency)}
              />
            </div>
            <SeriesView
              series={
                w2 === "inventory"
                  ? [{ id: "inv", label: "Inventory", points: stockHistoryPoints(m?.inventory) }]
                  : [{ id: "cogs", label: "Cost of revenue", points: flowAmountPoints(m?.costOfRevenue) }]
              }
              kind="bar"
              unit="money"
              currency={currency}
            />
          </>
        )}
      </article>

      <article className="l3-block">
        <header className="l3-block-head">
          <div>
            <h3>W3 — Payables and cash conversion cycle</h3>
            <p className="muted">
              CCC = DSO + DIO − DPO, using the pipeline’s aligned inputs. Concept-scope conflicts and extreme ratios
              keep their quality flags; they are not turned into clean scores.
            </p>
          </div>
        </header>
        <div className="l3-cards">
          <MetricCard
            title="Accounts payable"
            metric={m?.accountsPayable}
            period={m?.accountsPayable?.end ? `As of ${formatDate(m.accountsPayable.end)}` : null}
            value={formatCompactMoney(displayAmount(m?.accountsPayable), currency)}
          />
          <MetricCard
            title="DPO"
            metric={m?.dpo}
            value={displayAmount(m?.dpo) == null ? <Unavailable reason={m?.dpo?.reason} /> : formatDays(displayAmount(m?.dpo))}
          />
          <MetricCard
            title="DSO"
            metric={m?.dso}
            value={displayAmount(m?.dso) == null ? <Unavailable reason={m?.dso?.reason} /> : formatDays(displayAmount(m?.dso))}
          />
          <MetricCard
            title="DIO"
            metric={m?.dio}
            value={displayAmount(m?.dio) == null ? <Unavailable reason={m?.dio?.reason} /> : formatDays(displayAmount(m?.dio))}
          />
          <MetricCard
            title="Cash conversion cycle"
            metric={m?.cashConversionCycle}
            hint={m?.cashConversionCycle?.formula ?? "DSO + DIO − DPO"}
            value={
              displayAmount(m?.cashConversionCycle) == null ? (
                <Unavailable reason={m?.cashConversionCycle?.reason} />
              ) : (
                formatDays(displayAmount(m?.cashConversionCycle))
              )
            }
          />
          <MetricCard
            title="Operating working capital"
            metric={m?.operatingWorkingCapital}
            period={m?.operatingWorkingCapital?.end ? `As of ${formatDate(m.operatingWorkingCapital.end)}` : null}
            hint={m?.operatingWorkingCapital?.formula}
            value={
              displayAmount(m?.operatingWorkingCapital) == null ? (
                <Unavailable reason={m?.operatingWorkingCapital?.reason} />
              ) : (
                formatCompactMoney(displayAmount(m?.operatingWorkingCapital), currency)
              )
            }
          />
        </div>
        <SeriesView
          series={[{ id: "ap", label: "Accounts payable", points: stockHistoryPoints(m?.accountsPayable) }]}
          kind="bar"
          unit="money"
          currency={currency}
          caption="Accounts payable snapshots. DSO, DIO, DPO, CCC, and OWC stay latest-only."
        />
      </article>
    </section>
  );
}
