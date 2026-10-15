const NA = "N/A";

const CURRENCY_SYMBOL: Record<string, string> = { USD: "$", EUR: "€", GBP: "£", JPY: "¥", CNY: "¥" };

function symbolFor(currency: string | null | undefined): { prefix: string; suffix: string } {
  const c = (currency && currency.trim()) || "USD";
  const sym = CURRENCY_SYMBOL[c];
  return { prefix: sym ?? "", suffix: ` ${c}` };
}

/** Compact money: $1.23T, $45.6B, $789.0M, $12.3K. */
export function formatCompactMoney(value: number | null | undefined, currency?: string | null): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return NA;
  const { prefix, suffix } = symbolFor(currency);
  const sign = value < 0 ? "−" : "";
  const abs = Math.abs(value);
  const units: [number, string][] = [
    [1e12, "T"],
    [1e9, "B"],
    [1e6, "M"],
    [1e3, "K"],
  ];
  for (const [size, unit] of units) {
    if (abs >= size) {
      const scaled = abs / size;
      const digits = scaled >= 100 ? 1 : 2;
      return `${sign}${prefix}${scaled.toFixed(digits)}${unit}${suffix}`;
    }
  }
  return `${sign}${prefix}${abs.toFixed(0)}${suffix}`;
}

/** Full-precision money in millions for detail tables: $3,333.9M. */
export function formatMillions(value: number | null | undefined, currency?: string | null): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return NA;
  const { prefix, suffix } = symbolFor(currency);
  const sign = value < 0 ? "−" : "";
  const m = Math.abs(value) / 1e6;
  const digits = m < 10 ? 3 : 1;
  return `${sign}${prefix}${m.toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits })}M${suffix}`;
}

export function formatPrice(value: number | null | undefined, currency?: string | null): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return NA;
  const { prefix, suffix } = symbolFor(currency);
  return `${prefix}${value.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}${suffix}`;
}

export function formatPercent(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return NA;
  const sign = value > 0 ? "+" : value < 0 ? "−" : "";
  return `${sign}${Math.abs(value).toFixed(1)}%`;
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return NA;
  const d = new Date(iso.length === 10 ? `${iso}T00:00:00Z` : iso);
  if (Number.isNaN(d.getTime())) return NA;
  return d.toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric", timeZone: "UTC" });
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return NA;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return NA;
  return d.toLocaleString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "UTC",
    timeZoneName: "short",
  });
}

/** NASDAQ Trader "File Creation Time: MMDDYYYYHH:MM" -> ISO-like display string. */
export function formatNasdaqFileTime(raw: string | null | undefined): string {
  if (!raw) return NA;
  const m = /^(\d{2})(\d{2})(\d{4})(\d{2}):(\d{2})$/.exec(raw.trim());
  if (!m) return raw;
  const [, mm, dd, yyyy, hh, min] = m;
  return `${formatDate(`${yyyy}-${mm}-${dd}`)} ${hh}:${min} ET`;
}

export function fiscalLabel(fy: number | null, fq: number | null): string {
  if (!fy || !fq) return NA;
  return `FY${fy} Q${fq}`;
}

export function formatCount(n: number): string {
  return n.toLocaleString("en-US");
}
