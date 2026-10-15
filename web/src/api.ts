import type { CompanyDetail, IssuersFile, Layer2File, Meta, ScreenerFile } from "./types";

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
