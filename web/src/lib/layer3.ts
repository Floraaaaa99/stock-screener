/** Layer 3 Phase 1: manual selection and saved issuer membership. No scores. */

export const LAYER3_ANALYSIS_STATUS = "pending_implementation" as const;
export type Layer3AnalysisStatus = typeof LAYER3_ANALYSIS_STATUS;

export type HeaderCheckState = "none" | "some" | "all";

export interface Layer3CatalogRow {
  ticker: string;
  name: string;
  exchange: string;
  sicIndustry: string | null;
  sicMajorGroup: string | null;
}

export interface Layer3Entry {
  issuerId: string;
  cik: string | null;
  tickers: string[];
  displayTicker: string;
  name: string;
  exchange: string;
  sicIndustry: string | null;
  sicMajorGroup: string | null;
  addedAt: string;
  analysisStatus: Layer3AnalysisStatus;
}

export interface AddToLayer3Result {
  added: number;
  alreadySaved: number;
  issuerIds: string[];
}

export type CikByTicker = Record<string, string | null | undefined>;

/** Normalize an SEC CIK to 10 digits, or null when missing/invalid. */
export function normalizeCik(cik: string | null | undefined): string | null {
  if (cik == null) return null;
  const digits = String(cik).replace(/\D/g, "");
  if (!digits) return null;
  return digits.padStart(10, "0");
}

export function normalizeTicker(ticker: string): string {
  return ticker.trim().toUpperCase();
}

/**
 * Stable issuer identity: CIK when known, otherwise the listing ticker.
 * Share classes that share a CIK (HEI / HEI-A) collapse to one issuer.
 */
export function issuerIdFor(ticker: string, cik?: string | null): string {
  const normalized = normalizeCik(cik);
  if (normalized) return `cik:${normalized}`;
  return `ticker:${normalizeTicker(ticker)}`;
}

export function issuerIdForTicker(ticker: string, cikByTicker: CikByTicker): string {
  return issuerIdFor(ticker, cikByTicker[ticker] ?? cikByTicker[normalizeTicker(ticker)]);
}

export function headerCheckState(selected: ReadonlySet<string>, filteredTickers: readonly string[]): HeaderCheckState {
  if (filteredTickers.length === 0) return "none";
  let n = 0;
  for (const t of filteredTickers) {
    if (selected.has(t)) n += 1;
  }
  if (n === 0) return "none";
  if (n === filteredTickers.length) return "all";
  return "some";
}

export function sameTickerSet(a: ReadonlySet<string>, b: ReadonlySet<string>): boolean {
  if (a.size !== b.size) return false;
  for (const t of a) {
    if (!b.has(t)) return false;
  }
  return true;
}

/** Keep only tickers that are still on the current filtered list. */
export function restrictSelectionToCurrentList(
  selected: ReadonlySet<string>,
  currentTickers: readonly string[],
): Set<string> {
  const keep = new Set(currentTickers);
  const next = new Set<string>();
  for (const t of selected) {
    if (keep.has(t)) next.add(t);
  }
  return next;
}

/** Replace the selection with the current filtered list. Does not keep leftover tickers. */
export function selectFiltered(_selected: ReadonlySet<string>, filteredTickers: readonly string[]): Set<string> {
  return new Set(filteredTickers);
}

/** Clear the current filtered list from the selection. */
export function deselectFiltered(selected: ReadonlySet<string>, filteredTickers: readonly string[]): Set<string> {
  const drop = new Set(filteredTickers);
  const next = new Set<string>();
  for (const t of selected) {
    if (!drop.has(t)) next.add(t);
  }
  return next;
}

export function toggleFilteredSelection(selected: ReadonlySet<string>, filteredTickers: readonly string[]): Set<string> {
  return headerCheckState(selected, filteredTickers) === "all"
    ? deselectFiltered(selected, filteredTickers)
    : selectFiltered(selected, filteredTickers);
}

export function toggleTicker(selected: ReadonlySet<string>, ticker: string, checked: boolean): Set<string> {
  const next = new Set(selected);
  if (checked) next.add(ticker);
  else next.delete(ticker);
  return next;
}

export function uniqueTickers(tickers: readonly string[]): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const raw of tickers) {
    if (!raw) continue;
    if (seen.has(raw)) continue;
    seen.add(raw);
    out.push(raw);
  }
  return out;
}

function catalogByTicker(catalog: readonly Layer3CatalogRow[]): Map<string, Layer3CatalogRow> {
  const map = new Map<string, Layer3CatalogRow>();
  for (const row of catalog) map.set(row.ticker, row);
  return map;
}

function entryFromSelection(
  tickers: string[],
  cik: string | null,
  catalog: Map<string, Layer3CatalogRow>,
  addedAt: string,
): Layer3Entry {
  const displayTicker = tickers[0] ?? "";
  const row = catalog.get(displayTicker);
  return {
    issuerId: issuerIdFor(displayTicker, cik),
    cik,
    tickers,
    displayTicker,
    name: row?.name ?? displayTicker,
    exchange: row?.exchange ?? "",
    sicIndustry: row?.sicIndustry ?? null,
    sicMajorGroup: row?.sicMajorGroup ?? null,
    addedAt,
    analysisStatus: LAYER3_ANALYSIS_STATUS,
  };
}

/**
 * Copy selected listing tickers into issuer-level membership.
 * Idempotent: existing issuers are not overwritten. Additional share classes
 * are recorded on the existing entry without changing addedAt or other fields.
 */
export function addSelectedToMembership(
  entries: readonly Layer3Entry[],
  selectedTickers: readonly string[],
  cikByTicker: CikByTicker,
  catalog: readonly Layer3CatalogRow[],
  now = new Date().toISOString(),
): { entries: Layer3Entry[]; result: AddToLayer3Result } {
  const next = entries.map((e) => ({ ...e, tickers: [...e.tickers] }));
  const byId = new Map(next.map((e) => [e.issuerId, e]));
  const rows = catalogByTicker(catalog);
  const addedIds: string[] = [];
  let added = 0;
  let alreadySaved = 0;

  const grouped = new Map<string, { cik: string | null; tickers: string[] }>();
  for (const ticker of uniqueTickers(selectedTickers)) {
    const cik = normalizeCik(cikByTicker[ticker] ?? cikByTicker[normalizeTicker(ticker)]);
    const id = issuerIdFor(ticker, cik);
    const group = grouped.get(id);
    if (group) {
      if (!group.tickers.includes(ticker)) group.tickers.push(ticker);
    } else {
      grouped.set(id, { cik, tickers: [ticker] });
    }
  }

  for (const [id, group] of grouped) {
    const existing = byId.get(id);
    if (!existing) {
      const created = entryFromSelection(group.tickers, group.cik, rows, now);
      next.push(created);
      byId.set(id, created);
      added += 1;
      addedIds.push(id);
      continue;
    }
    alreadySaved += 1;
    for (const ticker of group.tickers) {
      if (!existing.tickers.includes(ticker)) existing.tickers.push(ticker);
    }
  }

  return { entries: next, result: { added, alreadySaved, issuerIds: addedIds } };
}

export function removeIssuer(entries: readonly Layer3Entry[], issuerId: string): Layer3Entry[] {
  return entries.filter((e) => e.issuerId !== issuerId);
}

export function savedIssuerIds(entries: readonly Layer3Entry[]): Set<string> {
  return new Set(entries.map((e) => e.issuerId));
}

export function isTickerSaved(ticker: string, entries: readonly Layer3Entry[], cikByTicker: CikByTicker): boolean {
  const id = issuerIdForTicker(ticker, cikByTicker);
  return entries.some((e) => e.issuerId === id);
}

export function selectedAlreadySavedCount(
  selectedTickers: readonly string[],
  entries: readonly Layer3Entry[],
  cikByTicker: CikByTicker,
): number {
  const saved = savedIssuerIds(entries);
  const seen = new Set<string>();
  let n = 0;
  for (const ticker of selectedTickers) {
    const id = issuerIdForTicker(ticker, cikByTicker);
    if (seen.has(id)) continue;
    seen.add(id);
    if (saved.has(id)) n += 1;
  }
  return n;
}
