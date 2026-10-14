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
  const checks = c.quarterChecks;
  const checked = Object.values(checks).reduce((a, b) => a + b, 0);
  const reasons = Object.entries(c.naReasons).sort((a, b) => b[1] - a[1]);
  return (
    <section className="panel coverage" aria-labelledby="coverage-title">
      <h2 id="coverage-title">Data coverage</h2>
      <div className="stats">
        <Stat label="Sector & industry (Yahoo)" value={c.yahooProfile} of={c.listings} />
        <Stat label="Market cap (Yahoo)" value={c.marketCap} of={c.listings} />
        <Stat label="Matched to SEC CIK" value={c.cikMatched} of={c.listings} />
        <Stat label="8 consecutive quarters" value={c.eightQuarters} of={c.listings} />
        <Stat label="Current TTM revenue" value={c.currentTtm} of={c.listings} />
        <Stat label="TTM revenue growth" value={c.growth} of={c.listings} />
        <Stat
          label="Quarters matching filing statements"
          value={checks.match ?? 0}
          of={checked}
          hint="Each quarter is compared with the income statement of the 10-Q/10-K it comes from."
        />
      </div>
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
          {formatCount(c.classificationIssues)} Yahoo classification issue(s) recorded (listings are still included; NASDAQ
          Trader is authoritative).
        </p>
      )}
    </section>
  );
}
