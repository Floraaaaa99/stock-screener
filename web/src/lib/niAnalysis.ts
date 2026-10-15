import type { Layer2Badge, Layer2Rate, Layer2Row } from "../types";
import { fiscalLabel, formatMillions, formatPercent } from "./format";

export const NI_RULES_VERSION = 1;

export const NI_PROF_ALL = "ni_all_profitable";
export const NI_PROF_ONE_LOSS = "ni_one_loss";
export const NI_PROF_MULTI_LOSS = "ni_two_or_three_loss";
export const NI_PROF_ALL_LOSS = "ni_all_loss";
export const NI_PROF_BREAKEVEN = "ni_contains_breakeven";
export const NI_PROF_INSUFFICIENT = "ni_insufficient_data";

export const NI_IMP_FOUR_YOY = "ni_four_yoy_improvements";
export const NI_IMP_TURNAROUND = "ni_latest_turnaround";
export const NI_IMP_TO_LOSS = "ni_latest_turned_to_loss";
export const NI_IMP_SEQ = "ni_four_quarter_sequential";

export const NI_PROFITABILITY_IDS = [
  NI_PROF_ALL,
  NI_PROF_ONE_LOSS,
  NI_PROF_MULTI_LOSS,
  NI_PROF_ALL_LOSS,
  NI_PROF_BREAKEVEN,
  NI_PROF_INSUFFICIENT,
] as const;

export const NI_IMPROVEMENT_IDS = [NI_IMP_FOUR_YOY, NI_IMP_TURNAROUND, NI_IMP_TO_LOSS, NI_IMP_SEQ] as const;

export const NI_PROF_LABELS: Record<string, string> = {
  [NI_PROF_ALL]: "All four profitable",
  [NI_PROF_ONE_LOSS]: "One loss quarter",
  [NI_PROF_MULTI_LOSS]: "Two or three loss quarters",
  [NI_PROF_ALL_LOSS]: "All four loss-making",
  [NI_PROF_BREAKEVEN]: "Contains break-even quarter",
  [NI_PROF_INSUFFICIENT]: "Insufficient NI data",
};

export const NI_IMP_LABELS: Record<string, string> = {
  [NI_IMP_FOUR_YOY]: "Four consecutive YoY improvements",
  [NI_IMP_TURNAROUND]: "Latest-quarter turnaround",
  [NI_IMP_TO_LOSS]: "Latest-quarter turned to loss",
  [NI_IMP_SEQ]: "Four-quarter sequential improvement",
};

export type NiQuarter = {
  label: string;
  end: string | null;
  value: number | null;
  display: number | null;
  verified: boolean;
  reason: string | null;
  url: string | null;
  form: string | null;
  check: string | null;
  priorValue: number | null;
  priorVerified: boolean;
  priorReason: string | null;
  yoyAbs: number | null;
  qoqAbs: number | null;
  qoqPrior: number | null;
};

export type NiAnalysis = {
  concept: string | null;
  quarters: NiQuarter[];
  ttm: number | null;
  ttmReason: string | null;
  profitableCount: number | null;
  lossCount: number | null;
  breakEvenCount: number | null;
  latestIsLoss: boolean | null;
  lossQuarters: string[];
  profitability: Layer2Badge[];
  improvement: Layer2Badge[];
  appliedProfitability: string[];
  appliedImprovement: string[];
  rulesVersion: number;
};

function money(v: number | null, currency: string | null): string {
  return formatMillions(v, currency);
}

function badge(id: string, labels: Record<string, string>, tooltip: string, applied: boolean): Layer2Badge {
  return { id, label: labels[id] ?? id, tooltip, applied, blockedByThreshold: false, rulesVersion: NI_RULES_VERSION };
}

function verifiedCurrent(rate: Layer2Rate | undefined): { ok: boolean; value: number | null; why: string | null } {
  if (!rate) return { ok: false, value: null, why: "missing_quarter" };
  if (rate.currentValue == null) return { ok: false, value: null, why: rate.reason ?? "missing_quarter" };
  if (rate.currentCheck !== "match") return { ok: false, value: rate.currentValue, why: rate.reason ?? "unverified" };
  return { ok: true, value: rate.currentValue, why: null };
}

function verifiedPrior(rate: Layer2Rate | undefined): { ok: boolean; value: number | null; why: string | null } {
  if (!rate) return { ok: false, value: null, why: "missing_quarter" };
  if (rate.otherValue == null) return { ok: false, value: null, why: rate.reason ?? "missing_quarter" };
  if (rate.otherCheck !== "match") return { ok: false, value: rate.otherValue, why: rate.reason ?? "unverified" };
  return { ok: true, value: rate.otherValue, why: null };
}

function labelOf(rate: Layer2Rate | undefined, fallback: string): string {
  if (!rate) return fallback;
  return rate.label ?? fiscalLabel(rate.fiscalYear, rate.fiscalQuarter);
}

/** Latest four NI amounts aligned to the revenue YoY window. Missing stays missing. */
export function analyzeNetIncome(row: Layer2Row): NiAnalysis {
  const currency = row.revenueCurrency;
  const yoy = row.earningsYoy ?? [];
  const qoq = row.earningsQoq ?? [];
  const qoqByEnd = new Map(qoq.filter((r) => r.end).map((r) => [r.end as string, r]));

  const quarters: NiQuarter[] = (row.yoy ?? []).map((rev, i) => {
    const ey = (rev.end && yoy.find((e) => e.end === rev.end)) || yoy[i];
    const eq = (rev.end && qoqByEnd.get(rev.end)) || qoq[i];
    const cur = verifiedCurrent(ey);
    const prior = verifiedPrior(ey);
    const qoqCur = verifiedCurrent(eq);
    const qoqPrior = verifiedPrior(eq);
    const yoyComparable = ey?.reason !== "incomparable_concept";
    const qoqComparable = eq?.reason !== "incomparable_concept";
    const yoyAbs =
      cur.ok && prior.ok && yoyComparable && cur.value != null && prior.value != null ? cur.value - prior.value : null;
    const qoqAbs =
      qoqCur.ok && qoqPrior.ok && qoqComparable && qoqCur.value != null && qoqPrior.value != null
        ? qoqCur.value - qoqPrior.value
        : null;
    return {
      label: labelOf(ey ?? rev, `Q${i + 1}`),
      end: rev.end,
      value: cur.ok ? cur.value : null,
      display: cur.ok ? cur.value : null,
      verified: cur.ok,
      reason: cur.ok ? null : cur.why,
      url: ey?.currentUrl ?? null,
      form: ey?.currentForm ?? null,
      check: ey?.currentCheck ?? null,
      priorValue: prior.ok && yoyComparable ? prior.value : null,
      priorVerified: prior.ok && yoyComparable,
      priorReason: !yoyComparable ? "incomparable_concept" : prior.ok ? null : prior.why,
      yoyAbs,
      qoqAbs,
      qoqPrior: qoqPrior.ok ? qoqPrior.value : null,
    };
  });

  const complete = quarters.length === 4 && quarters.every((q) => q.verified && q.value != null);
  const values = complete ? quarters.map((q) => q.value as number) : null;
  const profitableCount = values ? values.filter((v) => v > 0).length : null;
  const lossCount = values ? values.filter((v) => v < 0).length : null;
  const breakEvenCount = values ? values.filter((v) => v === 0).length : null;
  const lossQuarters = complete ? quarters.filter((q) => (q.value as number) < 0).map((q) => q.label) : [];
  const latestIsLoss = values ? values[3]! < 0 : null;
  const ttm = complete ? values!.reduce((a, b) => a + b, 0) : null;
  const ttmReason = complete ? null : "insufficient_ni_window";

  const listed = values ? values.map((v, i) => `${quarters[i]!.label} ${money(v, currency)}`).join(", ") : "";
  const countsTip = values
    ? `${profitableCount} profitable, ${lossCount} loss, ${breakEvenCount} break-even. ${listed}.`
    : `Need four verified standalone NI quarters in the revenue window; do not substitute older quarters. Have ${quarters.filter((q) => q.verified).length} of 4.`;

  const profitability: Layer2Badge[] = [];
  if (!complete) {
    profitability.push(badge(NI_PROF_INSUFFICIENT, NI_PROF_LABELS, `${countsTip} Rules v${NI_RULES_VERSION}.`, true));
  } else {
    const losses = lossCount as number;
    const primary =
      losses === 0 && (breakEvenCount as number) === 0
        ? NI_PROF_ALL
        : losses === 1
          ? NI_PROF_ONE_LOSS
          : losses === 4
            ? NI_PROF_ALL_LOSS
            : losses >= 2
              ? NI_PROF_MULTI_LOSS
              : null;
    if (primary) {
      const extra =
        primary === NI_PROF_ONE_LOSS || primary === NI_PROF_MULTI_LOSS || primary === NI_PROF_ALL_LOSS
          ? ` Loss quarters: ${lossQuarters.join(", ") || "none"}. Latest quarter is ${latestIsLoss ? "a loss" : "not a loss"}.`
          : ` Latest quarter is ${latestIsLoss ? "a loss" : "not a loss"}.`;
      profitability.push(badge(primary, NI_PROF_LABELS, `${countsTip}${extra} Rules v${NI_RULES_VERSION}.`, true));
    }
    if ((breakEvenCount as number) > 0) {
      profitability.push(
        badge(
          NI_PROF_BREAKEVEN,
          NI_PROF_LABELS,
          `${countsTip} Break-even quarters: ${quarters.filter((q) => q.value === 0).map((q) => q.label).join(", ")}. Rules v${NI_RULES_VERSION}.`,
          true,
        ),
      );
    }
  }

  const improvement: Layer2Badge[] = [];

  const yoyPairs = quarters.map((q) => ({ q, ok: q.verified && q.priorVerified && q.value != null && q.priorValue != null }));
  if (quarters.length === 4 && yoyPairs.every((p) => p.ok)) {
    const improved = quarters.every((q) => (q.value as number) > (q.priorValue as number));
    const detail = quarters
      .map((q) => `${q.label} ${money(q.value, currency)} vs ${money(q.priorValue, currency)} (Δ ${money(q.yoyAbs, currency)})`)
      .join("; ");
    improvement.push(
      badge(
        NI_IMP_FOUR_YOY,
        NI_IMP_LABELS,
        improved
          ? `Each of the latest four NI amounts is greater than the same fiscal quarter last year: ${detail}. Improvement is algebraic, including narrower losses. Rules v${NI_RULES_VERSION}.`
          : `Unmet. Need each of four NI amounts > same quarter last year. ${detail}. Not deterioration by itself. Rules v${NI_RULES_VERSION}.`,
        improved,
      ),
    );
  } else {
    improvement.push(
      badge(
        NI_IMP_FOUR_YOY,
        NI_IMP_LABELS,
        `Unavailable. Needs 8 verified comparable NI quarters (latest four and the same fiscal quarter one year earlier). Missing: ${quarters
          .filter((q) => !q.verified || !q.priorVerified)
          .map((q) => `${q.label}${q.reason ? ` (${q.reason})` : ""}${!q.priorVerified && q.priorReason ? ` prior ${q.priorReason}` : ""}`)
          .join(", ") || "aligned window"}. Rules v${NI_RULES_VERSION}.`,
        false,
      ),
    );
  }

  const prev = quarters[2];
  const latest = quarters[3];
  if (prev?.verified && latest?.verified && prev.value != null && latest.value != null) {
    const turn = prev.value < 0 && latest.value > 0;
    const toLoss = prev.value > 0 && latest.value < 0;
    const pair = `${prev.label} ${money(prev.value, currency)} → ${latest.label} ${money(latest.value, currency)} (Δ ${money((latest.value as number) - (prev.value as number), currency)})`;
    improvement.push(
      badge(
        NI_IMP_TURNAROUND,
        NI_IMP_LABELS,
        turn
          ? `Previous quarter NI < 0 and latest NI > 0: ${pair}. Rules v${NI_RULES_VERSION}.`
          : `Unmet. Need previous NI < 0 and latest NI > 0. Have ${pair}. Rules v${NI_RULES_VERSION}.`,
        turn,
      ),
    );
    improvement.push(
      badge(
        NI_IMP_TO_LOSS,
        NI_IMP_LABELS,
        toLoss
          ? `Previous quarter NI > 0 and latest NI < 0: ${pair}. Rules v${NI_RULES_VERSION}.`
          : `Unmet. Need previous NI > 0 and latest NI < 0. Have ${pair}. Rules v${NI_RULES_VERSION}.`,
        toLoss,
      ),
    );
  } else {
    const why = `Unavailable. Latest and previous quarter NI must both be verified. Latest: ${latest?.verified ? money(latest.value, currency) : latest?.reason ?? "missing"}; previous: ${prev?.verified ? money(prev.value, currency) : prev?.reason ?? "missing"}.`;
    improvement.push(badge(NI_IMP_TURNAROUND, NI_IMP_LABELS, `${why} Rules v${NI_RULES_VERSION}.`, false));
    improvement.push(badge(NI_IMP_TO_LOSS, NI_IMP_LABELS, `${why} Rules v${NI_RULES_VERSION}.`, false));
  }

  if (complete && values) {
    const seq = values[0]! < values[1]! && values[1]! < values[2]! && values[2]! < values[3]!;
    improvement.push(
      badge(
        NI_IMP_SEQ,
        NI_IMP_LABELS,
        seq
          ? `Latest four NI amounts increase strictly oldest→newest: ${listed}. Rules v${NI_RULES_VERSION}.`
          : `Unmet. Need three consecutive increases across ${listed}. Rules v${NI_RULES_VERSION}.`,
        seq,
      ),
    );
  } else {
    improvement.push(
      badge(
        NI_IMP_SEQ,
        NI_IMP_LABELS,
        `Unavailable. Needs four verified NI quarters in the revenue window. ${countsTip} Rules v${NI_RULES_VERSION}.`,
        false,
      ),
    );
  }

  return {
    concept: row.earningsConcept ?? null,
    quarters,
    ttm,
    ttmReason,
    profitableCount,
    lossCount,
    breakEvenCount,
    latestIsLoss,
    lossQuarters,
    profitability,
    improvement,
    appliedProfitability: profitability.filter((b) => b.applied).map((b) => b.id),
    appliedImprovement: improvement.filter((b) => b.applied).map((b) => b.id),
    rulesVersion: NI_RULES_VERSION,
  };
}

export function withNiAnalysis(row: Layer2Row): Layer2Row & { ni: NiAnalysis } {
  return { ...row, ni: analyzeNetIncome(row) };
}

export function niRuleStatus(b: Layer2Badge): "applied" | "unmet" | "unavailable" {
  if (b.applied) return "applied";
  return b.tooltip.startsWith("Unavailable") ? "unavailable" : "unmet";
}

export function formatNiChange(abs: number | null, prior: number | null, rate: number | null, currency: string | null): {
  text: string;
  title: string;
  kind: "pos" | "neg" | "na";
} {
  if (abs == null) {
    return { text: "N/A", title: "Absolute NI change unavailable (missing or unverified input).", kind: "na" };
  }
  const signed = abs > 0 ? `+${money(abs, currency).replace(/^−/, "")}` : money(abs, currency);
  const pct = prior != null && prior > 0 && rate != null ? ` (${formatPercent(rate)})` : "";
  const note =
    prior != null && prior <= 0
      ? "Percentage omitted because the comparison base is zero or negative."
      : "";
  return {
    text: `${signed}${pct}`,
    title: [note, prior != null ? `Prior ${money(prior, currency)}` : null].filter(Boolean).join(" "),
    kind: abs > 0 ? "pos" : abs < 0 ? "neg" : "na",
  };
}
