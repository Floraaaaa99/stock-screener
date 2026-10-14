import type { ScreenerRow } from "../types";

export const PAGE_SIZE = 50;

export type SortKey = "ttmCurrent" | "ttmPrevious" | "ttmGrowth";
export type SortDir = "asc" | "desc";

export const SORT_KEYS: SortKey[] = ["ttmCurrent", "ttmPrevious", "ttmGrowth"];
export const AMOUNT_SORTS: SortKey[] = ["ttmCurrent", "ttmPrevious"];

export interface Filters {
  sicMajorGroup: string;
  sicIndustry: string;
  currency: string;
  query: string;
}

export interface ViewState extends Filters {
  sort: SortKey;
  dir: SortDir;
  page: number;
}

export const DEFAULT_VIEW: ViewState = {
  sicMajorGroup: "",
  sicIndustry: "",
  currency: "",
  query: "",
  sort: "ttmGrowth",
  dir: "desc",
  page: 1,
};

export function normalize(s: string): string {
  return s.toLowerCase().normalize("NFKD").replace(/[\u0300-\u036f]/g, "").trim();
}

export function filterRows(rows: ScreenerRow[], f: Filters): ScreenerRow[] {
  const q = normalize(f.query);
  return rows.filter((r) => {
    if (f.sicMajorGroup && r.sicMajorGroup !== f.sicMajorGroup) return false;
    if (f.sicIndustry && r.sicIndustry !== f.sicIndustry) return false;
    if (f.currency && r.revenueCurrency !== f.currency) return false;
    if (q) {
      const ticker = r.ticker.toLowerCase();
      if (!ticker.startsWith(q) && !normalize(r.name).includes(q) && !(r.sicIndustry && normalize(r.sicIndustry).includes(q)))
        return false;
    }
    return true;
  });
}

/** Ticker-prefix matches rank above name matches when searching. */
export function searchRank(row: ScreenerRow, query: string): number {
  const q = normalize(query);
  if (!q) return 0;
  const t = row.ticker.toLowerCase();
  if (t === q) return 0;
  if (t.startsWith(q)) return 1;
  return 2;
}

function currencyRank(code: string | null | undefined): string {
  if (!code) return "zzz";
  if (code === "USD") return "0";
  return `1${code}`;
}

/** Sort by a numeric column; N/A (null) values always come last regardless of direction.
 *  Amount sorts (TTM revenue) are grouped by currency so USD and EUR are never ranked as one series. */
export function sortRows(rows: ScreenerRow[], key: SortKey, dir: SortDir, query = ""): ScreenerRow[] {
  const mult = dir === "asc" ? 1 : -1;
  const byAmount = AMOUNT_SORTS.includes(key);
  return [...rows].sort((a, b) => {
    if (query) {
      const ra = searchRank(a, query);
      const rb = searchRank(b, query);
      if (ra !== rb) return ra - rb;
    }
    if (byAmount) {
      const ca = currencyRank(a.revenueCurrency);
      const cb = currencyRank(b.revenueCurrency);
      if (ca !== cb) return ca.localeCompare(cb);
    }
    const va = a[key];
    const vb = b[key];
    const na = va === null || va === undefined || !Number.isFinite(va);
    const nb = vb === null || vb === undefined || !Number.isFinite(vb);
    if (na && nb) return a.ticker.localeCompare(b.ticker);
    if (na) return 1;
    if (nb) return -1;
    if (va !== vb) return ((va as number) - (vb as number)) * mult;
    return a.ticker.localeCompare(b.ticker);
  });
}

export function mixedCurrencies(rows: ScreenerRow[]): boolean {
  const codes = new Set(rows.map((r) => r.revenueCurrency).filter((c): c is string => Boolean(c)));
  return codes.size > 1;
}

export function pageCount(total: number, size = PAGE_SIZE): number {
  return Math.max(1, Math.ceil(total / size));
}

export function paginate<T>(rows: T[], page: number, size = PAGE_SIZE): T[] {
  const p = Math.min(Math.max(1, page), pageCount(rows.length, size));
  return rows.slice((p - 1) * size, p * size);
}

export function industriesFor(groups: Record<string, string[]>, major: string): string[] {
  if (major) return groups[major] ?? [];
  return [...new Set(Object.values(groups).flat())].sort((a, b) => a.localeCompare(b));
}

export function readViewFromSearch(search: string): ViewState {
  const p = new URLSearchParams(search);
  const sort = p.get("sort") as SortKey | null;
  const dir = p.get("dir");
  const page = Number(p.get("page"));
  return {
    sicMajorGroup: p.get("sicGroup") ?? "",
    sicIndustry: p.get("sic") ?? "",
    currency: p.get("ccy") ?? "",
    query: p.get("q") ?? "",
    sort: sort && SORT_KEYS.includes(sort) ? sort : DEFAULT_VIEW.sort,
    dir: dir === "asc" || dir === "desc" ? dir : DEFAULT_VIEW.dir,
    page: Number.isInteger(page) && page > 0 ? page : 1,
  };
}

export function viewToSearch(v: ViewState): string {
  const p = new URLSearchParams();
  if (v.sicMajorGroup) p.set("sicGroup", v.sicMajorGroup);
  if (v.sicIndustry) p.set("sic", v.sicIndustry);
  if (v.currency) p.set("ccy", v.currency);
  if (v.query) p.set("q", v.query);
  if (v.sort !== DEFAULT_VIEW.sort || v.dir !== DEFAULT_VIEW.dir) {
    p.set("sort", v.sort);
    p.set("dir", v.dir);
  }
  if (v.page > 1) p.set("page", String(v.page));
  const s = p.toString();
  return s ? `?${s}` : "";
}
