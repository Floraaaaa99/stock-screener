import type { Layer2Badge, Layer2Bucket, Layer2Row } from "../types";
import { normalize } from "./screener";

export const RULES_VERSION = 3;

export const TABS: { id: Layer2Bucket; label: string }[] = [
  { id: "passed", label: "Passed" },
  { id: "watchlist", label: "Watchlist" },
  { id: "data_review", label: "Data Review" },
  { id: "ttm_nonpositive", label: "TTM ≤ 0" },
];

export const CAT_STABLE = "stable_sequential_growth";
export const CAT_ACCEL = "accelerating_sequential_growth";
export const CAT_JUMP = "recent_qoq_jump";
export const CAT_FOUR_POS = "four_consecutive_positive_qoq";
export const CAT_VOL = "qoq_volatility";
export const CAT_DECLINE = "latest_quarter_revenue_decline";
export const CAT_OTHER = "other_flat";
export const CAT_UNABLE = "unable_to_classify";

export const CAT_LABELS: Record<string, string> = {
  [CAT_STABLE]: "Stable sequential growth",
  [CAT_ACCEL]: "Accelerating sequential growth",
  [CAT_JUMP]: "Recent QoQ jump",
  [CAT_FOUR_POS]: "Four consecutive quarters of positive QoQ",
  [CAT_VOL]: "QoQ volatility",
  [CAT_DECLINE]: "Latest-quarter revenue decline",
  [CAT_OTHER]: "Other / flat",
  [CAT_UNABLE]: "Unable to classify",
};

export const OBJECTIVE_CATS = [CAT_FOUR_POS, CAT_ACCEL, CAT_VOL, CAT_DECLINE, CAT_OTHER, CAT_UNABLE];
export const THRESHOLD_CATS = [CAT_STABLE, CAT_JUMP];

export interface Layer2Thresholds {
  stableSpreadPp: number | null;
  recentJumpPp: number | null;
}

export interface Layer2View {
  tab: Layer2Bucket;
  sicMajorGroup: string;
  sicIndustry: string;
  query: string;
  categories: string[];
  stableSpreadPp: number | null;
  recentJumpPp: number | null;
  page: number;
}

export const DEFAULT_LAYER2_VIEW: Layer2View = {
  tab: "passed",
  sicMajorGroup: "",
  sicIndustry: "",
  query: "",
  categories: [],
  stableSpreadPp: null,
  recentJumpPp: null,
  page: 1,
};

function fmt(rate: number | null): string {
  if (rate === null || !Number.isFinite(rate)) return "N/A";
  const sign = rate > 0 ? "+" : rate < 0 ? "−" : "";
  return `${sign}${Math.abs(rate).toFixed(4)}%`;
}

function badge(id: string, tooltip: string, applied: boolean, blocked = false): Layer2Badge {
  return { id, label: CAT_LABELS[id] ?? id, tooltip, applied, blockedByThreshold: blocked, rulesVersion: RULES_VERSION };
}

type Four = [number | null, number | null, number | null, number | null];

/** Client-side QoQ badges so threshold inputs can be chosen without rebuilding. */
export function classifyQoqBadges(rates: (number | null)[], t: Layer2Thresholds): Layer2Badge[] {
  const r = [...rates, null, null, null, null].slice(0, 4) as Four;
  const latest = r[3];
  const preceding: [number | null, number | null, number | null] = [r[0], r[1], r[2]];
  const complete = r.every((x) => x !== null && Number.isFinite(x));
  const allPositive = complete && r.every((x) => (x as number) > 0);
  const badges: Layer2Badge[] = [];

  if (allPositive) {
    badges.push(
      badge(CAT_FOUR_POS, `All four QoQ rates are strictly > 0% oldest→newest: ${r.map(fmt).join(", ")}. Rules v${RULES_VERSION}.`, true),
    );
  }

  if (allPositive && r[0]! < r[1]! && r[1]! < r[2]! && r[2]! < r[3]!) {
    badges.push(
      badge(CAT_ACCEL, `All four QoQ rates > 0% and strictly increasing oldest→newest: ${r.map(fmt).join(", ")}. Rules v${RULES_VERSION}.`, true),
    );
  }

  if (t.stableSpreadPp === null) {
    badges.push(
      badge(
        CAT_STABLE,
        "Stable sequential growth requires all four QoQ > 0% and (max − min) ≤ a configured spread in percentage points. Threshold not configured.",
        false,
        true,
      ),
    );
  } else if (allPositive) {
    const nums = r as number[];
    const spread = Math.max(...nums) - Math.min(...nums);
    if (spread <= t.stableSpreadPp) {
      badges.push(
        badge(
          CAT_STABLE,
          `All four QoQ > 0% and spread ${spread.toFixed(4)} pp ≤ ${t.stableSpreadPp} pp: ${nums.map(fmt).join(", ")}. Rules v${RULES_VERSION}.`,
          true,
        ),
      );
    }
  }

  if (t.recentJumpPp === null) {
    badges.push(
      badge(
        CAT_JUMP,
        "Recent QoQ jump requires latest QoQ − max(preceding three) ≥ a configured jump in percentage points. Threshold not configured.",
        false,
        true,
      ),
    );
  } else if (complete && latest !== null) {
    const gap = latest - Math.max(...(preceding as number[]));
    if (gap >= t.recentJumpPp) {
      badges.push(
        badge(
          CAT_JUMP,
          `Latest QoQ ${fmt(latest)} minus max of preceding three (${preceding.map(fmt).join(", ")}) is ${gap.toFixed(4)} pp ≥ ${t.recentJumpPp} pp. Rules v${RULES_VERSION}.`,
          true,
        ),
      );
    }
  }

  if (complete) {
    const signs = r.filter((x) => x !== 0).map((x) => ((x as number) > 0 ? 1 : -1));
    const changes = signs.slice(1).filter((s, i) => s !== signs[i]).length;
    if (changes >= 2) {
      badges.push(badge(CAT_VOL, `Sign changes (ignoring exact zeros) = ${changes} ≥ 2 across QoQ ${r.map(fmt).join(", ")}. Rules v${RULES_VERSION}.`, true));
    }
  }

  if (latest !== null && latest < 0) {
    badges.push(badge(CAT_DECLINE, `Latest QoQ ${fmt(latest)} is < 0%. Earlier quarters are not required. Rules v${RULES_VERSION}.`, true));
  }

  const applied = badges.filter((b) => b.applied);
  const thresholdsPending = badges.some((b) => b.blockedByThreshold);
  if (complete && applied.length === 0 && !thresholdsPending) {
    badges.push(badge(CAT_OTHER, `All four QoQ rates are present (${r.map(fmt).join(", ")}) but no other category rule matched. Rules v${RULES_VERSION}.`, true));
  }
  if (applied.length === 0 && !badges.some((b) => b.id === CAT_OTHER && b.applied)) {
    if (!complete && !(latest !== null && latest < 0)) {
      badges.push(badge(CAT_UNABLE, `Insufficient valid QoQ data to apply an objective category rule. Rules v${RULES_VERSION}.`, true));
    }
  }
  return badges;
}

export function withLiveBadges(row: Layer2Row, t: Layer2Thresholds): Layer2Row {
  const badges = classifyQoqBadges(
    row.qoq.map((q) => q.rate),
    t,
  );
  return { ...row, badges, appliedCategories: badges.filter((b) => b.applied).map((b) => b.id) };
}

export function countsFor(rows: Layer2Row[]): Record<Layer2Bucket, number> {
  const c: Record<Layer2Bucket, number> = { passed: 0, watchlist: 0, data_review: 0, ttm_nonpositive: 0 };
  for (const r of rows) c[r.bucket] += 1;
  return c;
}

export function filterLayer2(
  rows: Layer2Row[],
  tab: Layer2Bucket,
  f: { sicMajorGroup: string; sicIndustry: string; query: string; categories: string[] },
): Layer2Row[] {
  const q = normalize(f.query);
  return rows.filter((r) => {
    if (r.bucket !== tab) return false;
    if (f.sicMajorGroup && r.sicMajorGroup !== f.sicMajorGroup) return false;
    if (f.sicIndustry && r.sicIndustry !== f.sicIndustry) return false;
    if (f.categories.length && !f.categories.some((id) => r.appliedCategories.includes(id))) return false;
    if (q) {
      const ticker = r.ticker.toLowerCase();
      if (!ticker.startsWith(q) && !normalize(r.name).includes(q) && !(r.sicIndustry && normalize(r.sicIndustry).includes(q)))
        return false;
    }
    return true;
  });
}

function parseNum(raw: string | null): number | null {
  if (raw === null || raw === "") return null;
  const n = Number(raw);
  return Number.isFinite(n) ? n : null;
}

export function readLayer2View(search: string): { layer: 1 | 2; view: Layer2View } {
  const p = new URLSearchParams(search);
  const layer: 1 | 2 = p.get("layer") === "2" ? 2 : 1;
  const tab = p.get("tab") as Layer2Bucket | null;
  const cats = (p.get("cat") ?? "").split(",").filter(Boolean);
  return {
    layer,
    view: {
      tab: TABS.some((t) => t.id === tab) ? (tab as Layer2Bucket) : "passed",
      sicMajorGroup: p.get("sicGroup") ?? "",
      sicIndustry: p.get("sic") ?? "",
      query: p.get("q") ?? "",
      categories: cats,
      stableSpreadPp: parseNum(p.get("spread")),
      recentJumpPp: parseNum(p.get("jump")),
      page: Math.max(1, Number(p.get("page")) || 1),
    },
  };
}

export function layer2ToSearch(layer: 1 | 2, v: Layer2View, layer1Search: string): string {
  if (layer !== 2) return layer1Search;
  const p = new URLSearchParams();
  p.set("layer", "2");
  if (v.tab !== "passed") p.set("tab", v.tab);
  if (v.sicMajorGroup) p.set("sicGroup", v.sicMajorGroup);
  if (v.sicIndustry) p.set("sic", v.sicIndustry);
  if (v.query) p.set("q", v.query);
  if (v.categories.length) p.set("cat", v.categories.join(","));
  if (v.stableSpreadPp !== null) p.set("spread", String(v.stableSpreadPp));
  if (v.recentJumpPp !== null) p.set("jump", String(v.recentJumpPp));
  if (v.page > 1) p.set("page", String(v.page));
  const s = p.toString();
  return s ? `?${s}` : "?layer=2";
}

export function tabHint(id: Layer2Bucket): string {
  if (id === "passed") return "TTM revenue growth > 0% and all four quarterly YoY rates strictly > 0%.";
  if (id === "watchlist") return "TTM revenue growth > 0% and all four YoY rates are valid, but at least one is ≤ 0%.";
  if (id === "data_review") return "Required quarterly data is missing, unverified, incomparable, or a prior-year denominator is ≤ 0.";
  return "Layer 1 TTM revenue growth is valid and ≤ 0%. These are not Data Review.";
}
