from __future__ import annotations

import os
from pathlib import Path

PIPELINE_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = PIPELINE_DIR.parent
SAMPLES_DIR = PIPELINE_DIR / "samples"
OVERRIDES_FILE = PIPELINE_DIR / "config" / "concept_overrides.json"
CACHE_DIR = Path(os.environ.get("SCREENER_CACHE_DIR", PIPELINE_DIR / ".cache"))
OUTPUT_DIR = Path(os.environ.get("SCREENER_OUTPUT_DIR", REPO_ROOT / "web" / "public" / "data"))

NASDAQ_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
OTHER_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"
SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers_exchange.json"
SEC_COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
SEC_ARCHIVES_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accn_nodash}/"
SEC_COMPANYFACTS_ZIP_URL = "https://www.sec.gov/Archives/edgar/daily-index/xbrl/companyfacts.zip"

# SEC fair-access policy allows 10 requests/second; stay below it.
SEC_MAX_RPS = 8.0
YAHOO_MIN_INTERVAL_S = 1.0
YAHOO_BATCH_SIZE = 100
# Adopt batched Yahoo prices only when a comparison run is within this relative error.
YAHOO_BATCH_MAX_REL_ERROR = 0.02

# Cache freshness, in hours.
SEC_FACTS_TTL_H = 20
NASDAQ_TTL_H = 20
YAHOO_PROFILE_TTL_H = 24 * 30
YAHOO_MARKET_TTL_H = 20
SEC_BULK_TTL_H = 20

STATE_VERSION = 1
STATE_DIR = Path(os.environ.get("SCREENER_STATE_DIR", CACHE_DIR / "state"))
RELEASE_TAG = "pipeline-state"

# Publishing gates (relative drop vs the last complete baseline). A first full run has no baseline.
GROWTH_COVERAGE_MAX_DROP = 0.05
YAHOO_PROFILE_COVERAGE_MAX_DROP = 0.10
# Leave headroom under GitHub's 6-hour job limit for packing and uploading state.
DEFAULT_TIME_BUDGET_S = int(os.environ.get("SCREENER_TIME_BUDGET_S", str(5 * 3600)))


class ConfigError(RuntimeError):
    pass


def sec_user_agent() -> str:
    """SEC requires a descriptive User-Agent with contact details (e.g. "Name email@example.com")."""
    ua = os.environ.get("SEC_USER_AGENT", "").strip()
    if not ua:
        raise ConfigError(
            "SEC_USER_AGENT is not set. Set it to your name and contact email, e.g. "
            "SEC_USER_AGENT='Jane Doe jane@example.com'. In GitHub Actions use the SEC_USER_AGENT repository secret."
        )
    return ua
