"""Finnhub company news vendor.

Finnhub's company-news endpoint returns, per article, the headline, source,
publish time and a summary, which Yahoo's search fallback does not carry. A free
API key (https://finnhub.io/register) is read from ``FINNHUB_API_KEY``. The free
plan covers North American listings only and answers 403 for others; that is
reported as unavailable, so the next configured news vendor serves the call.
"""

import os
from datetime import UTC, datetime

from tradingagents.dataflows.config import get_config
from tradingagents.dataflows.date_window import in_window
from tradingagents.dataflows.errors import (
    NoMarketDataError,
    VendorNotConfiguredError,
    VendorUnavailableError,
)
from tradingagents.dataflows.net import get_scrubbed
from tradingagents.dataflows.symbols import normalize_symbol

FINNHUB_API_BASE = "https://finnhub.io/api/v1"

# Network timeout (seconds), as for the other keyed vendors.
REQUEST_TIMEOUT = 30

# Answers that say nothing about the symbol: a bad key (401), a listing the plan
# does not cover (403), the per-minute limit (429).
_REFUSED = (401, 403, 429)


class FinnhubNotConfiguredError(VendorNotConfiguredError):
    """Raised when Finnhub is selected but no API key is configured."""


def get_api_key() -> str:
    """Retrieve the Finnhub API key from the environment."""
    api_key = os.getenv("FINNHUB_API_KEY")
    if not api_key:
        raise FinnhubNotConfiguredError(
            "FINNHUB_API_KEY environment variable is not set. Get a free key at "
            "https://finnhub.io/register."
        )
    return api_key


def _format_article(article: dict, published: datetime) -> str:
    out = f"### {article.get('headline') or 'No title'} (source: {article.get('source') or 'Unknown'}, {published:%Y-%m-%d})\n"
    if article.get("summary"):
        out += f"{article['summary'].strip()}\n"
    if article.get("url"):
        out += f"Link: {article['url']}\n"
    return out + "\n"


def get_news(ticker: str, start_date: str, end_date: str) -> str:
    """News about ``ticker`` published in the window, newest first, from Finnhub."""
    canonical = normalize_symbol(ticker)
    api_key = get_api_key()
    response = get_scrubbed(
        f"{FINNHUB_API_BASE}/company-news",
        params={"symbol": canonical, "from": start_date, "to": end_date, "token": api_key},
        timeout=REQUEST_TIMEOUT,
        secret=api_key,
        passthrough=_REFUSED,
    )
    if response.status_code in _REFUSED:
        raise VendorUnavailableError(
            f"Finnhub refused company news for {canonical} (HTTP {response.status_code})"
        )
    articles = response.json()
    if not isinstance(articles, list):
        raise VendorUnavailableError(f"Finnhub returned no news list for {canonical}")

    # Finnhub filters by date already; the shared window check keeps the bounds
    # identical to the other news vendors (UTC, end day included), so no article
    # from after the analysis date can reach a historical run.
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    dated = []
    for article in articles:
        stamp = article.get("datetime")
        if not stamp:
            continue
        published = datetime.fromtimestamp(stamp, tz=UTC)
        if in_window(published, start_dt, end_dt):
            dated.append((published, article))
    if not dated:
        raise NoMarketDataError(ticker, canonical, f"no Finnhub news between {start_date} and {end_date}")

    # Finnhub returns every article it has, often hundreds a week for a large cap.
    dated.sort(key=lambda pair: pair[0], reverse=True)
    kept = dated[: get_config()["news_article_limit"]]
    resolved = "" if canonical == ticker else f" (resolved to {canonical})"
    body = "".join(_format_article(article, published) for published, article in kept)
    return f"## {ticker}{resolved} News, from {start_date} to {end_date}:\n\n{body}"
