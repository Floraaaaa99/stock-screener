/** Layer 3 research-page helpers. Presentation only — does not write JSON or call the pipeline. */

import { normalizeCik } from "./layer3";
import type {
  Layer3DerivedMetric,
  Layer3FlowMetric,
  Layer3Quarter,
  Layer3Row,
  Layer3StockHistoryPoint,
  Layer3StockMetric,
} from "../types";

export const LAYER3_RESEARCH_SECTIONS = [
  { id: "growth", label: "Growth Quality" },
  { id: "health", label: "Financial Health" },
  { id: "working-capital", label: "Working Capital" },
] as const;

export type Layer3ResearchSectionId = (typeof LAYER3_RESEARCH_SECTIONS)[number]["id"];

export function readLayer3Cik(search: string): string | null {
  const raw = search.startsWith("?") ? search.slice(1) : search;
  return normalizeCik(new URLSearchParams(raw).get("cik"));
}

export function layer3ToSearch(cik: string | null | undefined): string {
  const normalized = normalizeCik(cik);
  return normalized ? `?layer=3&cik=${normalized}` : "?layer=3";
}

export function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

export type MetricKind = Layer3FlowMetric | Layer3StockMetric | Layer3DerivedMetric;

export type DisplayKind = "reported" | "derived" | "missing" | "not_applicable" | "suppressed" | "extreme";

export function metricHasValue(metric: MetricKind | null | undefined): boolean {
  if (!metric) return false;
  if (metric.status === "missing" || metric.status === "not_applicable") return false;
  if ("ttm" in metric && isFiniteNumber(metric.ttm)) return true;
  if ("value" in metric && isFiniteNumber(metric.value)) return true;
  return false;
}

/** Display amount: TTM for flows, latest value for stocks. Missing is null, never 0. */
export function displayAmount(metric: MetricKind | null | undefined): number | null {
  if (!metric || metric.status === "missing" || metric.status === "not_applicable") return null;
  if ("ttm" in metric && metric.ttm !== undefined) {
    return isFiniteNumber(metric.ttm) ? metric.ttm : null;
  }
  if ("value" in metric && metric.value !== undefined) {
    return isFiniteNumber(metric.value) ? metric.value : null;
  }
  return null;
}

export function displayKind(metric: MetricKind | null | undefined): DisplayKind {
  if (!metric) return "missing";
  const flags = "qualityFlags" in metric ? metric.qualityFlags ?? [] : [];
  if (flags.includes("incompatible_inputs") || metric.status === "missing" && flags.includes("incompatible_inputs")) {
    return "suppressed";
  }
  if (metric.status === "not_applicable") return "not_applicable";
  if (metric.status === "missing") {
    return flags.includes("incompatible_inputs") ? "suppressed" : "missing";
  }
  if (flags.includes("extreme_ratio")) return "extreme";
  const method = metric.calculationMethod ?? "";
  if (method === "derived" || ("verification" in metric && metric.verification === "derived")) return "derived";
  return "reported";
}

export function displayKindLabel(kind: DisplayKind): string {
  switch (kind) {
    case "reported":
      return "Reported";
    case "derived":
      return "Derived";
    case "missing":
      return "Missing";
    case "not_applicable":
      return "Not applicable";
    case "suppressed":
      return "Suppressed";
    case "extreme":
      return "Extreme ratio";
  }
}

export function verificationLabel(verification: string | null | undefined): string {
  if (verification === "company_facts_only") return "Company Facts only — not statement-checked";
  if (verification === "derived") return "Derived — not statement-checked";
  return "Not statement-checked";
}

export interface ProvenanceFields {
  concept?: string | null;
  formula?: string | null;
  calculationMethod?: string | null;
  verification?: string | null;
  verificationNote?: string | null;
  identity?: string | null;
  qualityFlags?: string[];
  qualityNote?: string | null;
  reason?: string | null;
  status?: string | null;
  unit?: string | null;
  end?: string | null;
  accn?: string | null;
  form?: string | null;
  filed?: string | null;
  url?: string | null;
  fiscalYear?: number | null;
  fiscalQuarter?: number | null;
  start?: string | null;
  method?: string | null;
  unreliableTtm?: number | null;
  unreliableValue?: number | null;
}

export function metricProvenance(metric: MetricKind | null | undefined): ProvenanceFields {
  if (!metric) return { status: "missing" };
  return {
    concept: "concept" in metric ? metric.concept : null,
    formula: metric.formula,
    calculationMethod: metric.calculationMethod,
    verification: "verification" in metric ? metric.verification : null,
    verificationNote: "verificationNote" in metric ? metric.verificationNote : null,
    identity: "identity" in metric ? metric.identity : null,
    qualityFlags: "qualityFlags" in metric ? metric.qualityFlags : undefined,
    qualityNote: "qualityNote" in metric ? metric.qualityNote : null,
    reason: metric.reason,
    status: metric.status,
    unit: "unit" in metric ? metric.unit : null,
    end: "end" in metric ? metric.end : null,
    accn: "accn" in metric ? metric.accn : null,
    form: "form" in metric ? metric.form : null,
    filed: "filed" in metric ? metric.filed : null,
    url: "url" in metric ? metric.url : null,
    unreliableTtm: "unreliableTtm" in metric ? metric.unreliableTtm : null,
    unreliableValue: "unreliableValue" in metric ? metric.unreliableValue : null,
  };
}

export function quarterProvenance(q: Layer3Quarter | Layer3StockHistoryPoint): ProvenanceFields {
  return {
    concept: q.concept,
    formula: "formula" in q ? q.formula : null,
    calculationMethod: q.calculationMethod,
    verification: q.verification,
    reason: q.reason,
    status: "status" in q ? q.status : null,
    end: q.end,
    accn: q.accn,
    form: q.form,
    filed: q.filed,
    url: q.url,
    fiscalYear: q.fiscalYear,
    fiscalQuarter: q.fiscalQuarter,
    start: "start" in q ? q.start : null,
    method: "method" in q ? q.method : null,
  };
}

export function latestFlowPeriod(metric: Layer3FlowMetric | Layer3DerivedMetric | null | undefined): {
  fiscalYear: number | null;
  fiscalQuarter: number | null;
  end: string | null;
} | null {
  const q = (metric?.quarters ?? []).find((row) => isFiniteNumber(row.value) || row.end);
  if (!q) return null;
  return { fiscalYear: q.fiscalYear ?? null, fiscalQuarter: q.fiscalQuarter ?? null, end: q.end ?? null };
}

export type GrowthKind = "yoy" | "qoq";

export interface GrowthPair {
  current: Layer3Quarter;
  prior: Layer3Quarter | null;
  kind: GrowthKind;
  rate: number | null;
  absoluteChange: number | null;
  reason: string | null;
}

function fiscalKey(fy: number, fq: number): string {
  return `${fy}Q${fq}`;
}

function previousFiscalSlot(fy: number, fq: number): { fy: number; fq: number } {
  if (fq <= 1) return { fy: fy - 1, fq: 4 };
  return { fy, fq: fq - 1 };
}

export function compareFiscal(a: { fiscalYear?: number | null; fiscalQuarter?: number | null }, b: typeof a): number {
  const ay = a.fiscalYear ?? 0;
  const by = b.fiscalYear ?? 0;
  if (ay !== by) return ay - by;
  return (a.fiscalQuarter ?? 0) - (b.fiscalQuarter ?? 0);
}

function quarterUnit(q: Layer3Quarter, fallback: string | null | undefined): string | null {
  return (q as Layer3Quarter & { unit?: string | null }).unit ?? fallback ?? null;
}

/**
 * Pair standalone quarters for presentation YoY / QoQ.
 * Does not interpolate gaps, treat missing as zero, or write rates back to JSON.
 */
export function pairQuarterGrowth(
  quarters: readonly Layer3Quarter[] | null | undefined,
  kind: GrowthKind,
  currency?: string | null,
): GrowthPair[] {
  const labeled = (quarters ?? []).filter((q) => q.fiscalYear != null && q.fiscalQuarter != null);
  const byKey = new Map<string, Layer3Quarter>();
  for (const q of labeled) {
    const key = fiscalKey(q.fiscalYear as number, q.fiscalQuarter as number);
    const existing = byKey.get(key);
    if (!existing) {
      byKey.set(key, q);
      continue;
    }
    const preferNew = isFiniteNumber(q.value) && !isFiniteNumber(existing.value);
    const newerEnd = (q.end ?? "") > (existing.end ?? "");
    if (preferNew || (!isFiniteNumber(existing.value) && newerEnd) || (isFiniteNumber(q.value) && newerEnd)) {
      byKey.set(key, q);
    }
  }

  const ordered = [...byKey.values()].sort(compareFiscal);
  return ordered.map((current) => {
    const fy = current.fiscalYear as number;
    const fq = current.fiscalQuarter as number;
    const priorSlot = kind === "yoy" ? { fy: fy - 1, fq } : previousFiscalSlot(fy, fq);
    const prior = byKey.get(fiscalKey(priorSlot.fy, priorSlot.fq)) ?? null;
    if (!isFiniteNumber(current.value)) {
      return { current, prior, kind, rate: null, absoluteChange: null, reason: "missing_value" };
    }
    if (!prior || !isFiniteNumber(prior.value)) {
      return { current, prior, kind, rate: null, absoluteChange: null, reason: "no_comparable_quarter" };
    }
    const currentCcy = quarterUnit(current, currency);
    const priorCcy = quarterUnit(prior, currency);
    if (currentCcy && priorCcy && currentCcy !== priorCcy) {
      return { current, prior, kind, rate: null, absoluteChange: current.value - prior.value, reason: "currency_mismatch" };
    }
    const absoluteChange = current.value - prior.value;
    if (prior.value === 0) {
      return { current, prior, kind, rate: null, absoluteChange, reason: "prior_zero" };
    }
    if (prior.value < 0) {
      return { current, prior, kind, rate: null, absoluteChange, reason: "prior_not_positive" };
    }
    return {
      current,
      prior,
      kind,
      rate: (current.value / prior.value - 1) * 100,
      absoluteChange,
      reason: null,
    };
  });
}

export function chronologicalQuarters(quarters: readonly Layer3Quarter[] | null | undefined): Layer3Quarter[] {
  return [...(quarters ?? [])].sort((a, b) => {
    const byFiscal = compareFiscal(a, b);
    if (byFiscal !== 0) return byFiscal;
    return (a.end ?? "").localeCompare(b.end ?? "");
  });
}

export function chronologicalHistory(
  history: readonly Layer3StockHistoryPoint[] | null | undefined,
): Layer3StockHistoryPoint[] {
  return [...(history ?? [])].sort((a, b) => (a.end ?? "").localeCompare(b.end ?? ""));
}

export function ttmChange(metric: Layer3FlowMetric | Layer3DerivedMetric | null | undefined): {
  rate: number | null;
  absoluteChange: number | null;
  reason: string | null;
} {
  if (!metric) return { rate: null, absoluteChange: null, reason: "insufficient_ttm" };
  const current = isFiniteNumber(metric.ttm) ? metric.ttm : null;
  const previous = isFiniteNumber(metric.previousTtm) ? metric.previousTtm : null;
  const yoyReason = "ttmYoyReason" in metric ? metric.ttmYoyReason : null;
  if (current == null || previous == null) {
    return { rate: null, absoluteChange: null, reason: yoyReason ?? "insufficient_ttm" };
  }
  const absoluteChange = current - previous;
  if (isFiniteNumber(metric.ttmYoy)) {
    return { rate: metric.ttmYoy, absoluteChange, reason: null };
  }
  if (previous === 0) return { rate: null, absoluteChange, reason: yoyReason ?? "previous_ttm_zero" };
  if (previous < 0) return { rate: null, absoluteChange, reason: yoyReason ?? "previous_ttm_not_positive" };
  return { rate: null, absoluteChange, reason: yoyReason ?? "insufficient_ttm" };
}

export function issuerCurrency(row: Layer3Row | null | undefined): string | null {
  return row?.currency ?? row?.layer1.revenueCurrency ?? null;
}

export function issuerFlags(row: Layer3Row | null | undefined): string[] {
  return row?.flags ?? [];
}

export function hasConceptScopeMismatch(row: Layer3Row | null | undefined): boolean {
  if (!row) return false;
  if ((row.flags ?? []).includes("concept_scope_mismatch")) return true;
  const m = row.metrics;
  if (!m) return false;
  return (
    m.grossProfit?.identity === "concept_scope_mismatch" ||
    m.costOfRevenue?.identity === "concept_scope_mismatch" ||
    (m.grossMargin?.qualityFlags ?? []).includes("incompatible_inputs")
  );
}

export type ChartUnit = "money" | "percent" | "ratio" | "days" | "number";

export interface ChartPoint {
  key: string;
  label: string;
  sublabel?: string;
  value: number | null;
  reason?: string | null;
  provenance?: ProvenanceFields;
}

export function flowAmountPoints(metric: Layer3FlowMetric | Layer3DerivedMetric | null | undefined): ChartPoint[] {
  return chronologicalQuarters(metric?.quarters).map((q) => ({
    key: `${q.fiscalYear ?? ""}-${q.fiscalQuarter ?? ""}-${q.end ?? ""}`,
    label: q.fiscalYear && q.fiscalQuarter ? `FY${q.fiscalYear} Q${q.fiscalQuarter}` : (q.end ?? "—"),
    sublabel: q.end ?? undefined,
    value: isFiniteNumber(q.value) ? q.value : null,
    reason: q.reason ?? (isFiniteNumber(q.value) ? null : "missing_value"),
    provenance: quarterProvenance(q),
  }));
}

export function stockHistoryPoints(metric: Layer3StockMetric | null | undefined): ChartPoint[] {
  return chronologicalHistory(metric?.history).map((h) => ({
    key: `${h.end ?? ""}-${h.fiscalYear ?? ""}-${h.fiscalQuarter ?? ""}`,
    label: h.fiscalYear && h.fiscalQuarter ? `FY${h.fiscalYear} Q${h.fiscalQuarter}` : (h.end ?? "—"),
    sublabel: h.end ?? undefined,
    value: isFiniteNumber(h.value) ? h.value : null,
    reason: h.reason ?? (isFiniteNumber(h.value) ? null : "missing_value"),
    provenance: quarterProvenance(h),
  }));
}

export function growthRatePoints(pairs: readonly GrowthPair[]): ChartPoint[] {
  return pairs.map((p) => ({
    key: `${p.kind}-${p.current.fiscalYear}-${p.current.fiscalQuarter}-${p.current.end ?? ""}`,
    label:
      p.current.fiscalYear && p.current.fiscalQuarter
        ? `FY${p.current.fiscalYear} Q${p.current.fiscalQuarter}`
        : (p.current.end ?? "—"),
    sublabel: p.current.end ?? undefined,
    value: p.rate,
    reason: p.reason,
    provenance: quarterProvenance(p.current),
  }));
}

export function ttmPoints(metric: Layer3FlowMetric | Layer3DerivedMetric | null | undefined): ChartPoint[] {
  if (!metric) return [];
  return [
    {
      key: "previous-ttm",
      label: "Previous TTM",
      value: isFiniteNumber(metric.previousTtm) ? metric.previousTtm : null,
      reason: isFiniteNumber(metric.previousTtm) ? null : "insufficient_ttm",
    },
    {
      key: "current-ttm",
      label: "Current TTM",
      value: isFiniteNumber(metric.ttm) ? metric.ttm : null,
      reason: metric.reason ?? (isFiniteNumber(metric.ttm) ? null : "missing_value"),
      provenance: metricProvenance(metric),
    },
  ];
}
