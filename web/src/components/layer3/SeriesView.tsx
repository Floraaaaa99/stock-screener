import { useId, useMemo, useState } from "react";
import { naReason } from "../../lib/explain";
import { formatCompactMoney, formatDate, formatDays, formatExactMoney, formatPercent, formatRatio, formatRatioPercent } from "../../lib/format";
import type { ChartPoint, ChartUnit } from "../../lib/layer3Research";
import { ProvenancePanel, Unavailable } from "./ResearchChrome";

export interface SeriesSpec {
  id: string;
  label: string;
  points: ChartPoint[];
}

const SERIES_COLORS = ["#2563eb", "#64748b", "#6d28d9", "#0f766e"];

function formatChartTick(value: number, unit: ChartUnit, currency: string | null | undefined): string {
  if (unit === "money") return formatCompactMoney(value, currency);
  if (unit === "percent") return formatPercent(value);
  if (unit === "ratio") return formatRatioPercent(value);
  if (unit === "days") return formatDays(value);
  return value.toLocaleString("en-US", { maximumFractionDigits: 2 });
}

export function formatResearchValue(
  value: number | null | undefined,
  unit: ChartUnit,
  currency?: string | null,
  exact = false,
): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "N/A";
  if (unit === "money") return exact ? formatExactMoney(value, currency) : formatCompactMoney(value, currency);
  if (unit === "percent") return formatPercent(value);
  if (unit === "ratio") return exact ? `${value}` : formatRatioPercent(value);
  if (unit === "days") return exact ? `${value} days` : formatDays(value);
  return formatRatio(value);
}

function chartY(value: number, unit: ChartUnit): number {
  return unit === "ratio" ? value * 100 : value;
}

export function SeriesView({
  series,
  kind,
  unit,
  currency,
  caption,
  tableCaption,
}: {
  series: SeriesSpec[];
  kind: "bar" | "line";
  unit: ChartUnit;
  currency?: string | null;
  caption?: string;
  tableCaption?: string;
}) {
  const gid = useId();
  const [open, setOpen] = useState(false);
  const labels = useMemo(() => {
    const seen = new Map<string, ChartPoint>();
    for (const s of series) {
      for (const p of s.points) {
        if (!seen.has(p.key)) seen.set(p.key, p);
      }
    }
    return [...seen.values()];
  }, [series]);

  const numeric = series.flatMap((s) => s.points.map((p) => (p.value == null ? null : chartY(p.value, unit))));
  const known = numeric.filter((n): n is number => n != null && Number.isFinite(n));
  const lo = known.length ? Math.min(0, ...known) : 0;
  const hi = known.length ? Math.max(0, ...known) : 1;
  const span = hi - lo || 1;
  const width = 720;
  const height = 220;
  const padL = 64;
  const padR = 12;
  const padT = 12;
  const padB = 44;
  const innerW = width - padL - padR;
  const innerH = height - padT - padB;
  const yFor = (v: number) => padT + innerH - ((v - lo) / span) * innerH;
  const zeroY = yFor(0);
  const ticks = [hi, hi / 2 + lo / 2, lo];
  const groupCount = Math.max(1, labels.length);
  const groupW = innerW / groupCount;
  const barW = Math.max(4, Math.min(18, (groupW * 0.7) / Math.max(1, series.length)));

  return (
    <div className="l3-series">
      {caption && <p className="muted l3-series-caption">{caption}</p>}
      {known.length === 0 ? (
        <p className="muted">No historical values are available for this view.</p>
      ) : (
        <div className="l3-chart-wrap">
          <svg className="l3-chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label={tableCaption ?? "Financial series"}>
            <line x1={padL} x2={width - padR} y1={zeroY} y2={zeroY} className="l3-chart-zero" />
            {ticks.map((t, i) => (
              <g key={`${gid}-t-${i}`}>
                <line x1={padL} x2={width - padR} y1={yFor(t)} y2={yFor(t)} className="l3-chart-grid" />
                <text x={padL - 6} y={yFor(t) + 4} className="l3-chart-tick" textAnchor="end">
                  {formatChartTick(unit === "ratio" ? t / 100 : t, unit, currency)}
                </text>
              </g>
            ))}
            {kind === "bar" &&
              series.map((s, si) =>
                labels.map((label, li) => {
                  const point = s.points.find((p) => p.key === label.key);
                  if (point?.value == null || !Number.isFinite(point.value)) return null;
                  const yv = chartY(point.value, unit);
                  const x = padL + li * groupW + groupW / 2 + (si - (series.length - 1) / 2) * (barW + 2) - barW / 2;
                  const y = yv >= 0 ? yFor(yv) : zeroY;
                  const h = Math.abs(yFor(yv) - zeroY);
                  return (
                    <rect
                      key={`${s.id}-${label.key}`}
                      x={x}
                      y={y}
                      width={barW}
                      height={Math.max(h, 1)}
                      fill={SERIES_COLORS[si % SERIES_COLORS.length]}
                      opacity={0.9}
                    >
                      <title>
                        {s.label}: {formatResearchValue(point.value, unit, currency, true)}
                      </title>
                    </rect>
                  );
                }),
              )}
            {kind === "line" &&
              series.map((s, si) => {
                const color = SERIES_COLORS[si % SERIES_COLORS.length];
                const segs: string[] = [];
                let d = "";
                labels.forEach((label, li) => {
                  const point = s.points.find((p) => p.key === label.key);
                  const x = padL + li * groupW + groupW / 2;
                  if (point?.value == null || !Number.isFinite(point.value)) {
                    if (d) segs.push(d);
                    d = "";
                    return;
                  }
                  const y = yFor(chartY(point.value, unit));
                  d += `${d ? " L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`;
                });
                if (d) segs.push(d);
                return (
                  <g key={s.id}>
                    {segs.map((path, i) => (
                      <path key={i} d={path} fill="none" stroke={color} strokeWidth="2" />
                    ))}
                    {labels.map((label, li) => {
                      const point = s.points.find((p) => p.key === label.key);
                      if (point?.value == null || !Number.isFinite(point.value)) return null;
                      const x = padL + li * groupW + groupW / 2;
                      const y = yFor(chartY(point.value, unit));
                      return (
                        <circle key={`${s.id}-${label.key}`} cx={x} cy={y} r="3" fill={color}>
                          <title>
                            {s.label}: {formatResearchValue(point.value, unit, currency, true)}
                          </title>
                        </circle>
                      );
                    })}
                  </g>
                );
              })}
            {labels.map((label, li) => (
              <text
                key={label.key}
                x={padL + li * groupW + groupW / 2}
                y={height - 16}
                className="l3-chart-x"
                textAnchor="middle"
              >
                {label.label}
              </text>
            ))}
          </svg>
          {series.length > 1 && (
            <ul className="l3-legend">
              {series.map((s, i) => (
                <li key={s.id}>
                  <span className="l3-swatch" style={{ background: SERIES_COLORS[i % SERIES_COLORS.length] }} />
                  {s.label}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
      <button type="button" className="btn btn-small" onClick={() => setOpen((v) => !v)} aria-expanded={open}>
        {open ? "Hide exact values" : "Show exact values"}
      </button>
      {open && (
        <div className="table-scroll">
          <table className="screener l3-series-table">
            <caption className="muted">
              {tableCaption ?? "Exact extracted values. Missing periods stay blank and are not replaced with zero."}
            </caption>
            <thead>
              <tr>
                <th scope="col">Period</th>
                <th scope="col">Date</th>
                {series.map((s) => (
                  <th key={s.id} className="num" scope="col">
                    {s.label}
                  </th>
                ))}
                <th scope="col">Source</th>
              </tr>
            </thead>
            <tbody>
              {[...labels].reverse().map((label) => {
                const first = series.map((s) => s.points.find((p) => p.key === label.key)).find(Boolean);
                return (
                  <tr key={label.key}>
                    <td>{label.label}</td>
                    <td>{label.sublabel ? `${label.sublabel} (${formatDate(label.sublabel)})` : "—"}</td>
                    {series.map((s) => {
                      const point = s.points.find((p) => p.key === label.key);
                      const value = point?.value ?? null;
                      return (
                        <td key={s.id} className="num">
                          {value == null ? (
                            <Unavailable reason={point?.reason} />
                          ) : (
                            <span className={value < 0 ? "neg" : value === 0 ? "zero" : ""}>
                              {formatResearchValue(value, unit, currency, true)}
                            </span>
                          )}
                          {point?.reason && value == null && (
                            <div className="muted pending-sub">{naReason(point.reason)}</div>
                          )}
                        </td>
                      );
                    })}
                    <td>
                      {first?.provenance ? (
                        <details className="l3-prov">
                          <summary>Source</summary>
                          <ProvenancePanel fields={first.provenance} />
                        </details>
                      ) : (
                        "—"
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
