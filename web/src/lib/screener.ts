import type { ScreenerRow } from "../types";

export const PAGE_SIZE = 50;

export type SortKey = "marketCap" | "price" | "ttmCurrent" | "ttmPrevious" | "ttmGrowth";
export type SortDir = "asc" | "desc";

export const SORT_KEYS: SortKey[] = ["marketCap", "price", "ttmCurrent", "ttmPrevious", "ttmGrowth"];

export interface Filters {
  sector: string;
  industry: string;
  query: string;
}

export interface ViewState extends Filters {
  sort: SortKey;
  dir: SortDir;
  page: number;
}

export const DEFAULT_VIEW: ViewState = {
  sector: "",
  industry: "",
  query: "",
  sort: "marketCap",
  dir: "desc",
  page: 1,
};

export function normalize(s: string): string {
  return s.toLowerCase().normalize("NFKD").replace(/[\u0300-\u036f]/g, "").trim();
}

export function filterRows(rows: ScreenerRow[], f: Filters): ScreenerRow[] {
  const q = normalize(f.query);
  return rows.filter((r) => {
    if (f.sector && r.sector !== f.sector) return false;
    if (f.industry && r.industry !== f.industry) return false;
    if (q) {
      const ticker = r.ticker.toLowerCase();
      if (!ticker.startsWith(q) && !normalize(r.name).includes(q)) return false;
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

/** Sort by a numeric column; N/A (null) values always come last regardless of direction. */
export function sortRows(rows: ScreenerRow[], key: SortKey, dir: SortDir, query = ""): ScreenerRow[] {
  const mult = dir === "asc" ? 1 : -1;
  return [...rows].sort((a, b) => {
    if (query) {
      const ra = searchRank(a, query);
      const rb = searchRank(b, query);
      if (ra !== rb) return ra - rb;
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

export function pageCount(total: number, size = PAGE_SIZE): number {
  return Math.max(1, Math.ceil(total / size));
}

export function paginate<T>(rows: T[], page: number, size = PAGE_SIZE): T[] {
  const p = Math.min(Math.max(1, page), pageCount(rows.length, size));
  return rows.slice((p - 1) * size, p * size);
}

export function industriesFor(sectors: Record<string, string[]>, sector: string): string[] {
  if (sector) return sectors[sector] ?? [];
  return [...new Set(Object.values(sectors).flat())].sort((a, b) => a.localeCompare(b));
}

export function readViewFromSearch(search: string): ViewState {
  const p = new URLSearchParams(search);
  const sort = p.get("sort") as SortKey | null;
  const dir = p.get("dir");
  const page = Number(p.get("page"));
  return {
    sector: p.get("sector") ?? "",
    industry: p.get("industry") ?? "",
    query: p.get("q") ?? "",
    sort: sort && SORT_KEYS.includes(sort) ? sort : DEFAULT_VIEW.sort,
    dir: dir === "asc" || dir === "desc" ? dir : DEFAULT_VIEW.dir,
    page: Number.isInteger(page) && page > 0 ? page : 1,
  };
}

export function viewToSearch(v: ViewState): string {
  const p = new URLSearchParams();
  if (v.sector) p.set("sector", v.sector);
  if (v.industry) p.set("industry", v.industry);
  if (v.query) p.set("q", v.query);
  if (v.sort !== DEFAULT_VIEW.sort || v.dir !== DEFAULT_VIEW.dir) {
    p.set("sort", v.sort);
    p.set("dir", v.dir);
  }
  if (v.page > 1) p.set("page", String(v.page));
  const s = p.toString();
  return s ? `?${s}` : "";
}
