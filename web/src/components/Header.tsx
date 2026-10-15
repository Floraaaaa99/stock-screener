import { formatCount, formatDateTime } from "../lib/format";
import type { LayerId } from "../lib/layer2";
import type { Meta } from "../types";

export function Header({
  meta,
  layer,
  layer3Count,
  onLayer,
}: {
  meta: Meta | null;
  layer: LayerId;
  layer3Count: number;
  onLayer: (layer: LayerId) => void;
}) {
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
            {layer === 1
              ? "SEC SIC industry and trailing-twelve-month revenue growth for U.S.-listed stocks, from NASDAQ Trader listings and SEC EDGAR filings. Revenue is labeled in the reporting currency and is not converted."
              : layer === 2
                ? "Sequential growth on Layer 1’s validated eight-quarter window: four quarterly YoY rates, descriptive QoQ, and on Passed companies descriptive net-income badges. No valuation screen."
                : "Manually curated Layer 3 research list. Filter and select companies on the screener, then add them here. Nothing is enrolled from Layer 1 or Layer 2 automatically."}
          </p>
          <nav className="layer-nav" aria-label="Screener layer">
            <button type="button" className={`layer-btn ${layer === 1 ? "on" : ""}`} onClick={() => onLayer(1)}>
              TTM growth
            </button>
            <button type="button" className={`layer-btn ${layer === 2 ? "on" : ""}`} onClick={() => onLayer(2)}>
              Sequential growth
            </button>
            <button type="button" className={`layer-btn ${layer === 3 ? "on" : ""}`} onClick={() => onLayer(3)}>
              Layer 3{layer3Count > 0 ? ` (${formatCount(layer3Count)})` : ""}
            </button>
          </nav>
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
          <div>
            <dt>Eligible universe</dt>
            <dd>{meta ? formatCount(meta.universe.eligibleListings) : "…"}</dd>
          </div>
        </dl>
      </div>
      {sample && meta && (
        <div className="sample-banner" role="note">
          <div className="container">
            <strong>{meta.dataset.name}.</strong> This validation build shows {formatCount(meta.coverage.listings)} of the{" "}
            {formatCount(meta.universe.eligibleListings)} eligible NASDAQ, NYSE and NYSE American listings. The full U.S.
            universe replaces this sample after a complete run passes completeness and filing-validation checks.
          </div>
        </div>
      )}
    </header>
  );
}
