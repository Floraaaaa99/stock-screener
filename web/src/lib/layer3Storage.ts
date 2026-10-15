import { LAYER3_ANALYSIS_STATUS, uniqueTickers, type Layer3Entry } from "./layer3";

export const LAYER3_SCHEMA_VERSION = 1;
export const LAYER3_SELECTION_KEY = "stock-screener.layer3.selection.v1";
export const LAYER3_MEMBERSHIP_KEY = "stock-screener.layer3.membership.v1";

export type StorageStatus = "ok" | "empty" | "unavailable" | "recovered" | "migrated";

export interface KvStore {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}

interface VersionedEnvelope {
  version: number;
  updatedAt: string;
  data: unknown;
}

export function createMemoryStore(initial: Record<string, string> = {}): KvStore {
  const map = new Map(Object.entries(initial));
  return {
    getItem(key) {
      return map.has(key) ? map.get(key)! : null;
    },
    setItem(key, value) {
      map.set(key, value);
    },
    removeItem(key) {
      map.delete(key);
    },
  };
}

/** Probe localStorage. Returns null when the API is missing or blocked. */
export function browserKvStore(): KvStore | null {
  try {
    if (typeof window === "undefined" || !window.localStorage) return null;
    const probe = "__stock-screener.layer3.probe__";
    window.localStorage.setItem(probe, "1");
    window.localStorage.removeItem(probe);
    return window.localStorage;
  } catch {
    return null;
  }
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
}

function parseJson(raw: string | null): unknown {
  if (raw == null || raw === "") return null;
  try {
    return JSON.parse(raw);
  } catch {
    return undefined;
  }
}

function unwrapEnvelope(value: unknown): { version: number; data: unknown; migrated: boolean } | null {
  const rec = asRecord(value);
  if (!rec) return null;
  if (typeof rec.version === "number" && "data" in rec) {
    return { version: rec.version, data: rec.data, migrated: rec.version !== LAYER3_SCHEMA_VERSION };
  }
  // Bare payload from an older experimental shape.
  return { version: 0, data: value, migrated: true };
}

function sanitizeTickers(value: unknown): string[] | null {
  if (!Array.isArray(value)) return null;
  const tickers = uniqueTickers(value.filter((t): t is string => typeof t === "string" && t.trim().length > 0));
  return tickers;
}

function sanitizeEntry(value: unknown): Layer3Entry | null {
  const rec = asRecord(value);
  if (!rec) return null;
  const issuerId = typeof rec.issuerId === "string" && rec.issuerId.trim() ? rec.issuerId : null;
  const tickers = sanitizeTickers(rec.tickers);
  const displayTicker = typeof rec.displayTicker === "string" ? rec.displayTicker : tickers?.[0];
  if (!issuerId || !tickers?.length || !displayTicker) return null;
  const cik = typeof rec.cik === "string" && rec.cik.trim() ? rec.cik : rec.cik === null ? null : null;
  return {
    issuerId,
    cik,
    tickers,
    displayTicker,
    name: typeof rec.name === "string" && rec.name.trim() ? rec.name : displayTicker,
    exchange: typeof rec.exchange === "string" ? rec.exchange : "",
    sicIndustry: typeof rec.sicIndustry === "string" ? rec.sicIndustry : null,
    sicMajorGroup: typeof rec.sicMajorGroup === "string" ? rec.sicMajorGroup : null,
    addedAt: typeof rec.addedAt === "string" && rec.addedAt ? rec.addedAt : new Date(0).toISOString(),
    analysisStatus: LAYER3_ANALYSIS_STATUS,
  };
}

function sanitizeEntries(value: unknown): { entries: Layer3Entry[]; recovered: boolean } | null {
  if (!Array.isArray(value)) return null;
  const seen = new Set<string>();
  const out: Layer3Entry[] = [];
  for (const item of value) {
    const entry = sanitizeEntry(item);
    if (!entry || seen.has(entry.issuerId)) continue;
    seen.add(entry.issuerId);
    out.push(entry);
  }
  return { entries: out, recovered: value.length > 0 && out.length === 0 };
}

export class Layer3Store {
  private unavailable = false;

  constructor(private readonly kv: KvStore | null) {
    if (!kv) this.unavailable = true;
  }

  get available(): boolean {
    return !this.unavailable;
  }

  loadSelection(): { tickers: string[]; status: StorageStatus } {
    if (!this.kv) return { tickers: [], status: "unavailable" };
    const parsed = parseJson(this.read(LAYER3_SELECTION_KEY));
    if (parsed === undefined) return { tickers: [], status: "recovered" };
    if (parsed === null) return { tickers: [], status: "empty" };
    const envelope = unwrapEnvelope(parsed);
    if (!envelope) return { tickers: [], status: "recovered" };
    const rec = asRecord(envelope.data);
    const tickers = sanitizeTickers(rec?.tickers ?? envelope.data);
    if (!tickers) return { tickers: [], status: "recovered" };
    return { tickers, status: envelope.migrated ? "migrated" : "ok" };
  }

  saveSelection(tickers: readonly string[]): StorageStatus {
    return this.write(LAYER3_SELECTION_KEY, { tickers: uniqueTickers(tickers) });
  }

  loadMembership(): { entries: Layer3Entry[]; status: StorageStatus } {
    if (!this.kv) return { entries: [], status: "unavailable" };
    const parsed = parseJson(this.read(LAYER3_MEMBERSHIP_KEY));
    if (parsed === undefined) return { entries: [], status: "recovered" };
    if (parsed === null) return { entries: [], status: "empty" };
    const envelope = unwrapEnvelope(parsed);
    if (!envelope) return { entries: [], status: "recovered" };
    const rec = asRecord(envelope.data);
    const parsedEntries = sanitizeEntries(rec?.entries ?? envelope.data);
    if (!parsedEntries) return { entries: [], status: "recovered" };
    if (parsedEntries.recovered) return { entries: [], status: "recovered" };
    return { entries: parsedEntries.entries, status: envelope.migrated ? "migrated" : "ok" };
  }

  saveMembership(entries: readonly Layer3Entry[]): StorageStatus {
    return this.write(LAYER3_MEMBERSHIP_KEY, { entries });
  }

  private read(key: string): string | null {
    if (!this.kv) return null;
    try {
      return this.kv.getItem(key);
    } catch {
      this.unavailable = true;
      return null;
    }
  }

  private write(key: string, data: unknown): StorageStatus {
    if (!this.kv || this.unavailable) return "unavailable";
    const envelope: VersionedEnvelope = {
      version: LAYER3_SCHEMA_VERSION,
      updatedAt: new Date().toISOString(),
      data,
    };
    try {
      this.kv.setItem(key, JSON.stringify(envelope));
      return "ok";
    } catch {
      this.unavailable = true;
      return "unavailable";
    }
  }
}

export function storageBanner(status: StorageStatus): string | null {
  if (status === "unavailable") {
    return "This browser blocked or ran out of local storage. Layer 3 changes stay in this tab only and will be lost on refresh.";
  }
  if (status === "recovered") {
    return "Saved Layer 3 data could not be read and was reset. The list is local to this browser.";
  }
  return null;
}
