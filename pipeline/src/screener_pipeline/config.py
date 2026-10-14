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

# SEC fair-access policy allows 10 requests/second; stay below it.
SEC_MAX_RPS = 8.0
YAHOO_MIN_INTERVAL_S = 1.0

# Cache freshness, in hours.
SEC_FACTS_TTL_H = 20
NASDAQ_TTL_H = 20
YAHOO_PROFILE_TTL_H = 24 * 30
YAHOO_MARKET_TTL_H = 20


class ConfigError(RuntimeError):
    pass


def sec_user_agent() -> str:
    """SEC requires a descriptive User-Agent with contact details (e.g. "Name email@example.com")."""
    ua = os.environ.get("SEC_USER_AGENT", "").strip()
    if not ua:
        raise ConfigError(
            "SEC_USER_AGENT is not set. Set it to your name and contact email, e.g. "
            "SEC_USER_AGENT='Jane Doe jane@example.com'. In GitHub Actions use a repository variable."
        )
    return ua
