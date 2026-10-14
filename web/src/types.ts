// Mirrors the JSON written by pipeline/src/screener_pipeline/output.py and build.py.

export interface ScreenerRow {
  ticker: string;
  name: string;
  exchange: string;
  type: "common" | "adr";
  sicCode: string | null;
  sicMajorGroup: string | null;
  sicIndustry: string | null;
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
  cikMatched: number;
  sicAssigned: number;
  includedWithoutRevenue: number;
  foreignFilers: number;
  ambiguousConcept: number;
  eightQuarters: number;
  currentTtm: number;
  growth: number;
  statementVerified: number;
  quarterChecks: Record<string, number>;
  naReasons: Record<string, number>;
  classificationIssues: number;
  byCurrency: Record<string, number>;
}

export interface Meta {
  schemaVersion: number;
  generatedAt: string;
  dataset: {
    mode: "sample" | "full" | "partial";
    id: string;
    name: string;
    description: string;
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
    sec: { url: string; companyFacts?: string; sic?: string; latestFilingDate: string | null };
  };
  coverage: Coverage;
  sicMajorGroups: Record<string, string[]>;
  currencies: string[];
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
  sic: {
    code: string | null;
    description: string | null;
    majorGroup: string | null;
    label: string | null;
    source: string;
  };
  ttm: { current: number | null; previous: number | null; growthPct: number | null; reason: string | null; currency: string | null };
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

export type Layer2Bucket = "passed" | "watchlist" | "data_review" | "ttm_nonpositive";

export interface Layer2Rate {
  fiscalYear: number | null;
  fiscalQuarter: number | null;
  start: string | null;
  end: string | null;
  label: string | null;
  rate: number | null;
  reason: string | null;
  kind: "yoy" | "qoq";
  currentValue: number | null;
  otherValue: number | null;
  absoluteChange: number | null;
  currentUrl: string | null;
  otherUrl: string | null;
  currentForm: string | null;
  otherForm: string | null;
  currentCheck: string | null;
  otherCheck: string | null;
}

export interface Layer2Badge {
  id: string;
  label: string;
  tooltip: string;
  applied: boolean;
  blockedByThreshold: boolean;
  rulesVersion: number;
}

export interface Layer2Row {
  ticker: string;
  name: string;
  exchange: string;
  type: string;
  sicCode: string | null;
  sicMajorGroup: string | null;
  sicIndustry: string | null;
  revenueCurrency: string | null;
  revenueConcept: string | null;
  layer1SchemaVersion: number;
  ttmGrowth: number | null;
  ttmReason: string | null;
  bucket: Layer2Bucket;
  dataReviewReasons: string[];
  yoy: Layer2Rate[];
  qoq: Layer2Rate[];
  badges: Layer2Badge[];
  appliedCategories: string[];
  rulesVersion: number;
}

export interface Layer2File {
  schemaVersion: number;
  rulesVersion: number;
  generatedAt: string;
  layer1GeneratedAt: string;
  layer1SchemaVersion: number;
  thresholds: { qoqStableSpreadPctPoints: number | null; qoqRecentJumpPctPoints: number | null };
  counts: { passed: number; watchlist: number; dataReview: number; ttmNonpositive: number; listings: number };
  rows: Layer2Row[];
}
