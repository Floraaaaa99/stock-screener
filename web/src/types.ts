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

/** Compact ticker → SEC CIK map for Layer 3 issuer identity. */
export interface IssuersFile {
  schemaVersion: number;
  byTicker: Record<string, string | null>;
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
  earnings: {
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

export interface Layer2FreshnessPeriod {
  label: string | null;
  end: string | null;
  filed?: string | null;
  form?: string | null;
  filedBy?: string | null;
  filedByDays?: number | null;
}

export interface Layer2Freshness {
  status: "current" | "verified_lagging" | "unknown";
  asOf: string | null;
  window: "verified_historical";
  latestVerified: Layer2FreshnessPeriod | null;
  expectedNext: Layer2FreshnessPeriod | null;
  message: string | null;
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
  earningsConcept?: string | null;
  earningsYoy?: Layer2Rate[];
  earningsQoq?: Layer2Rate[];
  /** Client (and future pipeline) NI badges. Never used for revenue eligibility. */
  ni?: {
    appliedProfitability: string[];
    appliedImprovement: string[];
  };
  badges: Layer2Badge[];
  appliedCategories: string[];
  freshness: Layer2Freshness;
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

export type Layer3ExtractionStatus = "extracted" | "pending_analysis" | "insufficient_facts";
export type Layer3VerificationStatus = "company_facts_only" | "not_checked";
export type Layer3ModelApplicability = "applicable" | "not_applicable";
export type Layer3ScoringStatus = "not_implemented";
export type Layer3InputCompleteness = "ready" | "pending_data_verification" | "pending_analysis";

/** @deprecated Split into extraction/verification/model/scoring/input fields. */
export type Layer3RowStatus =
  | "extracted"
  | "pending_data_verification"
  | "pending_analysis"
  | "model_not_applicable"
  | "insufficient_verified_data";

export interface Layer3Quarter {
  fiscalYear: number | null;
  fiscalQuarter: number | null;
  start: string | null;
  end: string | null;
  value: number | null;
  rawValue?: number | null;
  reason?: string | null;
  method: string | null;
  formula: string | null;
  concept?: string | null;
  restated?: boolean;
  accn?: string | null;
  form?: string | null;
  filed?: string | null;
  url?: string | null;
  calculationMethod?: string | null;
  verification?: string | null;
}

export interface Layer3StockHistoryPoint {
  fiscalYear?: number | null;
  fiscalQuarter?: number | null;
  end: string | null;
  value: number | null;
  status?: string | null;
  reason?: string | null;
  concept?: string | null;
  accn?: string | null;
  form?: string | null;
  filed?: string | null;
  url?: string | null;
  calculationMethod?: string | null;
  verification?: string | null;
}

export interface Layer3FlowMetric {
  status: string;
  reason: string | null;
  concept?: string | null;
  unit?: string | null;
  signPolicy?: string;
  ttm: number | null;
  previousTtm?: number | null;
  ttmYoy?: number | null;
  ttmYoyReason?: string | null;
  formula?: string;
  definition?: string;
  quarters?: Layer3Quarter[];
  calculationMethod?: string;
  verification: string;
  verificationNote?: string;
  identity?: string | null;
  qualityFlags?: string[];
  qualityNote?: string | null;
  unreliableTtm?: number | null;
}

export interface Layer3StockMetric {
  status: string;
  reason: string | null;
  concept?: string | null;
  value: number | null;
  end?: string | null;
  accn?: string | null;
  form?: string | null;
  filed?: string | null;
  url?: string | null;
  unit?: string | null;
  aggregation?: string;
  formula?: string;
  calculationMethod?: string;
  verification: string;
  components?: Layer3StockMetric[];
  /** Up to 8 aligned quarter-end snapshots. Stocks are never summed into a TTM. */
  history?: Layer3StockHistoryPoint[];
}

export interface Layer3DerivedMetric {
  status: string;
  reason: string | null;
  value?: number | null;
  ttm?: number | null;
  previousTtm?: number | null;
  ttmYoy?: number | null;
  formula?: string;
  unit?: string;
  end?: string | null;
  calculationMethod?: string;
  verification?: string;
  verificationNote?: string;
  quarters?: Layer3Quarter[];
  qualityFlags?: string[];
  qualityNote?: string | null;
  unreliableTtm?: number | null;
  unreliableValue?: number | null;
}

export interface Layer3Metrics {
  ocf: Layer3FlowMetric;
  capex: Layer3FlowMetric;
  fcf: Layer3FlowMetric;
  operatingIncome: Layer3FlowMetric;
  interestExpense: Layer3FlowMetric;
  depreciationAmortization?: Layer3FlowMetric;
  ebitda: Layer3FlowMetric;
  cash: Layer3StockMetric;
  shortTermDebt: Layer3StockMetric;
  longTermDebt: Layer3StockMetric;
  totalDebt: Layer3StockMetric;
  netDebt: Layer3StockMetric;
  revenue?: Layer3FlowMetric;
  netIncome?: Layer3FlowMetric;
  grossProfit?: Layer3FlowMetric;
  costOfRevenue?: Layer3FlowMetric;
  grossMargin?: Layer3DerivedMetric;
  operatingMargin?: Layer3DerivedMetric;
  netMargin?: Layer3DerivedMetric;
  fcfMargin?: Layer3DerivedMetric;
  cashConversion?: Layer3DerivedMetric;
  accountsReceivable?: Layer3StockMetric;
  inventory?: Layer3StockMetric;
  accountsPayable?: Layer3StockMetric;
  currentAssets?: Layer3StockMetric;
  currentLiabilities?: Layer3StockMetric;
  currentRatio?: Layer3DerivedMetric;
  operatingWorkingCapital?: Layer3DerivedMetric;
  arYoy?: Layer3DerivedMetric;
  inventoryYoy?: Layer3DerivedMetric;
  apYoy?: Layer3DerivedMetric;
  dso?: Layer3DerivedMetric;
  dio?: Layer3DerivedMetric;
  dpo?: Layer3DerivedMetric;
  cashConversionCycle?: Layer3DerivedMetric;
  noInterestBurden: boolean;
  growthSource: string;
}

export interface Layer3Row {
  cik: string;
  tickers: string[];
  displayTicker: string;
  name: string;
  exchange: string | null;
  sicCode: string | null;
  sicIndustry: string | null;
  sicMajorGroup: string | null;
  extractionStatus?: Layer3ExtractionStatus;
  verificationStatus?: Layer3VerificationStatus;
  modelApplicability?: Layer3ModelApplicability;
  scoringStatus?: Layer3ScoringStatus;
  inputCompleteness?: Layer3InputCompleteness;
  /** @deprecated Prefer the four separate status fields. */
  status?: Layer3RowStatus;
  reason?: string | null;
  currency?: string | null;
  flags?: string[];
  companyFactsCik?: string | null;
  schemaVersion?: number;
  extractionVersion: number;
  dataAsOf?: string | null;
  growthSource: string;
  scoring: null;
  issuerFile?: string | null;
  layer1: {
    revenueTtm: number | null;
    revenuePriorTtm: number | null;
    revenueTtmGrowth: number | null;
    revenueReason: string | null;
    revenueCurrency: string | null;
    earningsConcept: string | null;
    earningsStatus: string | null;
    source: string;
  };
  metrics: Layer3Metrics | null;
}

export interface Layer3File {
  schemaVersion: number;
  extractionVersion: number;
  generatedAt: string;
  /** Index payload omits quarter-level metrics; full rows live at issuerFileTemplate. */
  payload?: "index" | "issuer";
  issuerFileTemplate?: string;
  cutoffNote: string;
  verificationNote?: string;
  scoring: null;
  counts: {
    issuers: number;
    extraction?: { extracted: number; pendingAnalysis: number; insufficientFacts: number };
    verification?: { companyFactsOnly: number; notChecked: number };
    model?: { applicable: number; notApplicable: number };
    scoring?: { notImplemented: number };
    inputs?: { ready: number; pendingDataVerification: number; pendingAnalysis: number };
    metrics?: Record<string, { extracted: number; missing: number; notApplicable: number }>;
    extracted?: number;
    pendingDataVerification?: number;
    pendingAnalysis?: number;
    modelNotApplicable?: number;
    insufficientVerifiedData?: number;
  };
  rows: Layer3Row[];
}
