import { formatDate, formatNasdaqFileTime } from "../lib/format";
import type { Meta } from "../types";

export function Footer({ meta }: { meta: Meta | null }) {
  const s = meta?.sources;
  return (
    <footer className="footer">
      <div className="container footer-grid">
        <div>
          <h3>Data sources</h3>
          <ul>
            <li>
              <a href="https://www.nasdaqtrader.com/trader.aspx?id=symboldirdefs" target="_blank" rel="noreferrer">
                NASDAQ Trader symbol directory
              </a>{" "}
              — listed stocks on NASDAQ, NYSE and NYSE American.
              {s && <span className="muted"> File created {formatNasdaqFileTime(s.nasdaqTrader.fileCreated.nasdaqlisted)}.</span>}
            </li>
            <li>
              <a href="https://www.sec.gov/edgar/sec-api-documentation" target="_blank" rel="noreferrer">
                SEC EDGAR
              </a>{" "}
              — SIC codes from company submissions; quarterly revenue from XBRL Company Facts and the income statements of
              10-Q/10-K filings.
              {s && <span className="muted"> Latest filing included: {formatDate(s.sec.latestFilingDate)}.</span>}
            </li>
            <li>
              <a
                href="https://github.com/Floraaaaa99/stock-screener/actions/workflows/daily-update.yml"
                target="_blank"
                rel="noreferrer"
              >
                Refresh dataset
              </a>{" "}
              — repo owners can run the daily SEC update now. Optional ticker rebuild uses current Company Facts; it
              does not create 10-Q numbers for foreign 20-F / F-10 / 6-K filers.
            </li>
          </ul>
        </div>
        <div>
          <h3>Method</h3>
          <p>
            Current TTM is the sum of the latest four standalone fiscal quarters; Previous TTM is the four quarters
            before those. Growth = Current ÷ Previous − 1, shown only when all eight quarters are available, consecutive
            and comparable and Previous TTM is positive. Sequential growth (Layer 2) uses that same eight-quarter window:
            four quarterly YoY rates decide Passed / Watchlist / Data Review; QoQ rates, category badges, and Passed
            net-income profitability / improvement badges are descriptive and never remove a company. Quarters missing from 10-Qs are derived from year-to-date totals
            (for example Q4 = annual − nine months). Missing values are shown as N/A, never as zero. Industry filters use
            SEC SIC codes and descriptions, not a commercial sector taxonomy. Layer 3 is a local, manually
            curated research list in this browser; companies are never added from Layer 1 or Layer 2 automatically.
          </p>
          <p className="muted">
            For personal research only. Not investment advice. Data may be delayed or incomplete. Do not compare revenue
            amounts across currencies without conversion; this site does not convert.
          </p>
        </div>
      </div>
    </footer>
  );
}
