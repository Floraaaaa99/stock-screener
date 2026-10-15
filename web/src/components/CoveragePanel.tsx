import { naReason } from "../lib/explain";
import { formatCount } from "../lib/format";
import type { Meta } from "../types";

function Stat({ label, value, of, hint }: { label: string; value: number; of: number; hint?: string }) {
  const pct = of > 0 ? Math.round((value / of) * 100) : 0;
  return (
    <div className="stat" title={hint}>
      <div className="stat-top">
        <span className="stat-label">{label}</span>
        <span className="stat-value">
          {formatCount(value)} <span className="muted">/ {formatCount(of)}</span>
        </span>
      </div>
      <div className="bar" aria-hidden="true">
        <span style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

export function CoveragePanel({ meta }: { meta: Meta }) {
  const c = meta.coverage;
  const eligible = meta.universe.eligibleListings;
  const listings = c.listings;
  const checks = c.quarterChecks;
  const checked = Object.values(checks).reduce((a, b) => a + b, 0);
  const reasons = Object.entries(c.naReasons).sort((a, b) => b[1] - a[1]);
  const currencies = Object.entries(c.byCurrency || {}).sort((a, b) => b[1] - a[1]);
  return (
    <section className="panel coverage" aria-labelledby="coverage-title">
      <h2 id="coverage-title">Data coverage</h2>

      <div className="coverage-block">
        <h3>Full-universe coverage</h3>
        <p className="muted coverage-note">
          Every eligible NASDAQ, NYSE and NYSE American common stock and ADR stays in the table, including companies
          with missing SEC revenue. This dataset shows {formatCount(listings)} of {formatCount(eligible)} eligible
          listings ({meta.dataset.mode}).
        </p>
        <div className="stats">
          <Stat label="Listings in this dataset" value={listings} of={eligible} />
          <Stat label="Matched to SEC CIK" value={c.cikMatched} of={listings} />
          <Stat label="SEC SIC assigned" value={c.sicAssigned} of={listings} hint="From EDGAR submissions sic / sicDescription, not a commercial sector taxonomy." />
          <Stat
            label="Included without TTM revenue"
            value={c.includedWithoutRevenue}
            of={listings}
            hint="Still listed. Revenue columns show N/A with a reason."
          />
        </div>
      </div>

      <div className="coverage-block">
        <h3>TTM coverage</h3>
        <p className="muted coverage-note">
          Trailing-twelve-month figures require standalone quarterly revenue from 10-Q/10-K filings. Growth additionally
          needs eight consecutive comparable quarters and a positive previous TTM.
        </p>
        <div className="stats">
          <Stat label="8 consecutive quarters" value={c.eightQuarters} of={listings} />
          <Stat label="Current TTM revenue" value={c.currentTtm} of={listings} />
          <Stat label="TTM revenue growth" value={c.growth} of={listings} />
          <Stat
            label="Quarters matching filing statements"
            value={checks.match ?? 0}
            of={checked}
            hint="Each quarter is compared with the income statement of the 10-Q/10-K it comes from."
          />
        </div>
      </div>

      {currencies.length > 0 && (
        <div className="reasons">
          <h3>Reporting currencies (unconverted)</h3>
          <ul>
            {currencies.map(([code, n]) => (
              <li key={code}>
                <strong>{formatCount(n)}</strong> — {code}
              </li>
            ))}
          </ul>
        </div>
      )}

      {reasons.length > 0 && (
        <div className="reasons">
          <h3>Why some values are N/A</h3>
          <ul>
            {reasons.map(([code, n]) => (
              <li key={code}>
                <strong>{formatCount(n)}</strong> — {naReason(code)}
              </li>
            ))}
          </ul>
        </div>
      )}
      {c.classificationIssues > 0 && (
        <p className="muted">
          {formatCount(c.classificationIssues)} classification issue(s) recorded (listings are still included; NASDAQ
          Trader is authoritative for the universe, SEC SIC for industry).
        </p>
      )}
    </section>
  );
}
