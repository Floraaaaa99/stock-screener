import { formatCount, formatDateTime } from "../lib/format";
import type { Meta } from "../types";

export function Header({ meta }: { meta: Meta | null }) {
  const sample = meta?.dataset.mode === "sample";
  return (
    <header className="header">
      <div className="container header-inner">
        <div>
          <h1>
            <span className="logo" aria-hidden="true">
              <svg viewBox="0 0 32 32" width="28" height="28">
                <rect width="32" height="32" rx="7" fill="currentColor" />
                <path d="M7 22l6-7 5 4 7-10" stroke="white" strokeWidth="3" fill="none" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </span>
            U.S. Stock Screener
          </h1>
          <p className="subtitle">
            Sector, industry, market cap and trailing-twelve-month revenue growth for U.S.-listed stocks, with
            quarterly revenue taken from SEC filings.
          </p>
        </div>
        <dl className="header-stats">
          <div>
            <dt>Data updated</dt>
            <dd>{meta ? formatDateTime(meta.generatedAt) : "…"}</dd>
          </div>
          <div>
            <dt>Companies shown</dt>
            <dd>{meta ? formatCount(meta.coverage.listings) : "…"}</dd>
          </div>
        </dl>
      </div>
      {sample && meta && (
        <div className="sample-banner" role="note">
          <div className="container">
            <strong>{meta.dataset.name}.</strong> This validation build shows {formatCount(meta.coverage.listings)} of the{" "}
            {formatCount(meta.universe.eligibleListings)} eligible NASDAQ, NYSE and NYSE American listings. The full U.S.
            universe is added after the sample's calculations have been checked against SEC filings.
          </div>
        </div>
      )}
    </header>
  );
}
