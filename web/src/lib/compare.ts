import type { Layer2Rate, Layer2Row } from "../types";
import { fiscalLabel } from "./format";

export type ComparisonRow = {
  key: string;
  label: string;
  end: string | null;
  revenue: number | null;
  earnings: number | null;
  revYoy: Layer2Rate | null;
  niYoy: Layer2Rate | null;
  revQoq: Layer2Rate | null;
  niQoq: Layer2Rate | null;
};

export type PriorYearRow = {
  key: string;
  label: string;
  revenue: number | null;
  earnings: number | null;
  url: string | null;
  form: string | null;
};

function byEnd(rates: Layer2Rate[] | undefined): Map<string, Layer2Rate> {
  const out = new Map<string, Layer2Rate>();
  for (const r of rates ?? []) {
    if (r.end) out.set(r.end, r);
  }
  return out;
}

function verifiedAmount(rate: Layer2Rate | undefined | null, side: "current" | "other"): number | null {
  if (!rate) return null;
  if (side === "current") {
    if (rate.currentCheck !== "match" || rate.currentValue == null) return null;
    return rate.currentValue;
  }
  if (rate.otherCheck !== "match" || rate.otherValue == null) return null;
  return rate.otherValue;
}

/** Latest four Layer 2 quarters, oldest to newest, with revenue and net income on one row. */
export function comparisonRows(row: Layer2Row): ComparisonRow[] {
  const niYoy = byEnd(row.earningsYoy);
  const niQoq = byEnd(row.earningsQoq);
  const qoq = byEnd(row.qoq);
  return (row.yoy ?? []).map((y, i) => {
    const end = y.end;
    const ni = (end && niYoy.get(end)) || (end && niQoq.get(end)) || null;
    return {
      key: end ?? y.label ?? `q-${i}`,
      label: y.label ?? fiscalLabel(y.fiscalYear, y.fiscalQuarter),
      end,
      revenue: y.currentValue,
      earnings: verifiedAmount(ni, "current"),
      revYoy: y,
      niYoy: end ? (niYoy.get(end) ?? null) : null,
      revQoq: end ? (qoq.get(end) ?? null) : null,
      niQoq: end ? (niQoq.get(end) ?? null) : null,
    };
  });
}

/** Same fiscal quarter last year — the YoY denominators, values only. */
export function priorYearRows(row: Layer2Row): PriorYearRow[] {
  const niYoy = byEnd(row.earningsYoy);
  return (row.yoy ?? []).map((y, i) => {
    const fy = y.fiscalYear != null ? y.fiscalYear - 1 : null;
    return {
      key: `prior-${y.end ?? y.label ?? i}`,
      label: fy && y.fiscalQuarter ? fiscalLabel(fy, y.fiscalQuarter) : "N/A",
      revenue: y.otherValue,
      earnings: y.end ? verifiedAmount(niYoy.get(y.end), "other") : null,
      url: y.otherUrl,
      form: y.otherForm,
    };
  });
}
