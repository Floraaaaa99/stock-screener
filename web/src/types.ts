// Mirrors the JSON written by pipeline/src/screener_pipeline/output.py and build.py.

export interface ScreenerRow {
  ticker: string;
  name: string;
  exchange: string;
  type: "common" | "adr";
  sector: string | null;
  industry: string | null;
  marketCap: number | null;
  price: number | null;
  priceCurrency: string | null;
  revenueCurrency: string | null;
  ttmCurrent: number | null;
  ttmPrevious: number | null;
  ttmGrowth: number | null;
  naReason: string | null;
  latestQuarter: string | null;
  latestQuarterEnd: string | null;
  quartersAvailable: number;
}

export interface ScreenerFile {
  schemaVersion: number;
  generatedAt: string;
  rows: ScreenerRow[];
}

export interface Coverage {
  listings: number;
  companies: number;
  yahooProfile: number;
  marketCap: number;
  price: number;
  cikMatched: number;
  foreignFilers: number;
  ambiguousConcept: number;
  eightQuarters: number;
  currentTtm: number;
  growth: number;
  statementVerified: number;
  quarterChecks: Record<string, number>;
  naReasons: Record<string, number>;
  classificationIssues: number;
}

export interface Meta {
  schemaVersion: number;
  generatedAt: string;
  dataset: {
    mode: "sample" | "full";
    id: string;
    name: string;
    description: string;
    expectedIndustry?: string | null;
  };
  universe: {
    source: string;
    exchanges: string[];
    eligibleListings: number;
    byExchange: Record<string, number>;
    bySecurityType: Record<string, number>;
    excludedByReason: Record<string, number>;
    fileCreated: Record<string, string | null>;
  };
  sources: {
    nasdaqTrader: { url: string; fileCreated: Record<string, string | null> };
    yahoo: { url: string; via: string; marketOldest: string | null; marketNewest: string | null; profileOldest: string | null };
    sec: { url: string; api: string; latestFilingDate: string | null };
  };
  coverage: Coverage;
  sectors: Record<string, string[]>;
}

export interface QuarterSource {
  role: string;
  sign: number;
  form: string;
  filed: string;
  accn: string;
  start: string;
  end: string;
  value: number;
  url: string;
}

export interface QuarterCheck {
  status: "match" | "mismatch" | "unavailable" | "no_filing";
  accn?: string;
  form?: string;
  url?: string;
  statement_label?: string;
  statement_value?: number;
  expected_value?: number;
  detail?: string;
}

export interface QuarterBase {
  fiscalYear: number | null;
  fiscalQuarter: number | null;
  start: string;
  end: string;
  ttm: "current" | "previous" | null;
}

export interface MissingQuarter extends QuarterBase {
  missing: true;
  value: null;
}

export interface ReportedQuarter extends QuarterBase {
  missing: false;
  value: number;
  concept: string;
  method: "reported" | "derived";
  formula: string;
  form: string;
  filed: string;
  accn: string;
  url: string;
  restated: boolean;
  labelInferred: boolean;
  flags: string[];
  sources: QuarterSource[];
  check: QuarterCheck | null;
}

export type QuarterEntry = MissingQuarter | ReportedQuarter;

export interface ConceptCandidate {
  concept: string;
  latestEnd: string | null;
  latestValue: number | null;
  quartersInWindow: number;
  selected: boolean;
  comparedWith: string | null;
  overlaps: number;
  disagreements: number;
  statementLabel: string | null;
}

export interface CompanyDetail {
  schemaVersion: number;
  ticker: string;
  name: string;
  exchange: string;
  securityType: string;
  cik: string | null;
  secName: string | null;
  market: {
    sector: string | null;
    industry: string | null;
    marketCap: number | null;
    price: number | null;
    currency: string | null;
    quoteType: string | null;
    profileAsOf: string | null;
    marketAsOf: string | null;
  };
  ttm: { current: number | null; previous: number | null; growthPct: number | null; reason: string | null };
  revenue: {
    status: string;
    currency: string | null;
    concept: string | null;
    conceptStatus: string | null;
    conceptNote: string;
    candidates: ConceptCandidate[];
    flags: string[];
    statementCheck: {
      status: string;
      accn: string | null;
      form: string | null;
      url: string | null;
      period_end: string | null;
      months: number | null;
      pipeline_value: number | null;
      statement_value: number | null;
    } | null;
    quarters: QuarterEntry[];
  } | null;
  classificationIssues: { ticker: string; issue: string; detail: string }[];
}
