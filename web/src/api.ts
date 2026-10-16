import type { CompanyDetail, IssuersFile, Layer2File, Layer3File, Layer3Row, Meta, ScreenerFile } from "./types";
import { layer3IssuerFile, normalizeCik } from "./lib/layer3";

const DATA_BASE = `${import.meta.env.BASE_URL}data/`;

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(DATA_BASE + path, { cache: "no-cache" });
  if (!res.ok) throw new Error(`Could not load ${path} (HTTP ${res.status})`);
  return (await res.json()) as T;
}

export function loadMeta(): Promise<Meta> {
  return getJson<Meta>("meta.json");
}

export function loadScreener(): Promise<ScreenerFile> {
  return getJson<ScreenerFile>("screener.json");
}

export function loadLayer2(): Promise<Layer2File> {
  return getJson<Layer2File>("layer2.json");
}

export function loadLayer3(): Promise<Layer3File> {
  return getJson<Layer3File>("layer3.json");
}

const layer3IssuerCache = new Map<string, Promise<Layer3Row | null>>();

/** Fetch one issuer’s Phase 2 metrics file. 404 / missing CIK → null. */
export function loadLayer3Issuer(cik: string): Promise<Layer3Row | null> {
  const normalized = normalizeCik(cik);
  if (!normalized) return Promise.resolve(null);
  let pending = layer3IssuerCache.get(normalized);
  if (!pending) {
    pending = getJson<Layer3Row>(layer3IssuerFile(normalized)).catch(() => null);
    layer3IssuerCache.set(normalized, pending);
  }
  return pending;
}

/** Lazy-load metrics only for the given CIKs (the user’s Layer 3 list). */
export async function loadLayer3Issuers(ciks: readonly string[]): Promise<Layer3Row[]> {
  const unique: string[] = [];
  const seen = new Set<string>();
  for (const cik of ciks) {
    const normalized = normalizeCik(cik);
    if (!normalized || seen.has(normalized)) continue;
    seen.add(normalized);
    unique.push(normalized);
  }
  const rows = await Promise.all(unique.map((cik) => loadLayer3Issuer(cik)));
  return rows.filter((row): row is Layer3Row => row != null);
}

export async function loadIssuers(): Promise<Record<string, string | null>> {
  try {
    const file = await getJson<IssuersFile>("issuers.json");
    return file.byTicker ?? {};
  } catch {
    return {};
  }
}

const companyCache = new Map<string, Promise<CompanyDetail>>();

export function loadCompany(ticker: string): Promise<CompanyDetail> {
  let p = companyCache.get(ticker);
  if (!p) {
    p = getJson<CompanyDetail>(`companies/${encodeURIComponent(ticker)}.json`);
    p.catch(() => companyCache.delete(ticker));
    companyCache.set(ticker, p);
  }
  return p;
}
