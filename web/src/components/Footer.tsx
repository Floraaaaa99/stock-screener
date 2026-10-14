import { formatDate, formatDateTime, formatNasdaqFileTime } from "../lib/format";
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
              <a href="https://finance.yahoo.com" target="_blank" rel="noreferrer">
                Yahoo Finance
              </a>{" "}
              (via yfinance) — sector, industry, market cap and price.
              {s && <span className="muted"> Prices as of {formatDateTime(s.yahoo.marketNewest)}.</span>}
            </li>
            <li>
              <a href="https://www.sec.gov/edgar/sec-api-documentation" target="_blank" rel="noreferrer">
                SEC EDGAR XBRL Company Facts
              </a>{" "}
              — quarterly revenue from 10-Q and 10-K filings.
              {s && <span className="muted"> Latest filing included: {formatDate(s.sec.latestFilingDate)}.</span>}
            </li>
          </ul>
        </div>
        <div>
          <h3>Method</h3>
          <p>
            Current TTM is the sum of the latest four standalone fiscal quarters; Previous TTM is the four quarters
            before those. Growth = Current ÷ Previous − 1, shown only when all eight quarters are available, consecutive
            and comparable and Previous TTM is positive. Quarters missing from 10-Qs are derived from year-to-date totals
            (for example Q4 = annual − nine months). Missing values are shown as N/A, never as zero.
          </p>
          <p className="muted">
            For personal research only. Not investment advice. Data may be delayed or incomplete.
          </p>
        </div>
      </div>
    </footer>
  );
}
