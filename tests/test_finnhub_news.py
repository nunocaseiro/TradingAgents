"""Finnhub company news: headlines with their summaries, kept to the run's window.

Yahoo's quote news feed answers 404 for every symbol (yfinance #3004) and its
search fallback carries titles only, so the news analyst had no article text.
Finnhub's company-news endpoint returns a summary per article. Its free plan
covers North American listings only and answers 403 for the rest, which must
hand the call to the next configured vendor rather than end it. All API access
is mocked.
"""

from datetime import UTC, datetime
from unittest import mock

import pytest

import tradingagents.default_config as default_config
from tradingagents.dataflows import router
from tradingagents.dataflows.config import get_config, set_config
from tradingagents.dataflows.errors import (
    NoMarketDataError,
    VendorNotConfiguredError,
    VendorUnavailableError,
)
from tradingagents.dataflows.vendors import finnhub


def _epoch(stamp):
    return int(datetime.fromisoformat(stamp).replace(tzinfo=UTC).timestamp())


def _article(headline, stamp, summary="Body.", source="Reuters"):
    return {"headline": headline, "summary": summary, "source": source,
            "url": f"https://example.com/{headline}", "datetime": _epoch(stamp), "related": "AAPL"}


class _Response:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


@pytest.fixture
def key(monkeypatch):
    monkeypatch.setenv("FINNHUB_API_KEY", "secret-key")


def _news(articles=None, status=200, start="2026-10-16", end="2026-10-23", ticker="AAPL"):
    response = _Response(status, articles if articles is not None else [])
    with mock.patch.object(finnhub, "get_scrubbed", return_value=response) as get:
        return finnhub.get_news(ticker, start, end), get


@pytest.mark.unit
def test_articles_carry_headline_source_date_summary_and_link(key):
    out, _ = _news([_article("Apple beats", "2026-10-20T13:00:00", summary="Revenue rose 16%.")])
    assert "## AAPL News, from 2026-10-16 to 2026-10-23" in out
    assert "### Apple beats (source: Reuters, 2026-10-20)" in out
    assert "Revenue rose 16%." in out
    assert "Link: https://example.com/Apple beats" in out


@pytest.mark.unit
def test_articles_outside_the_window_are_dropped(key):
    out, _ = _news([
        _article("BEFORE", "2026-10-15T23:00:00"),
        _article("INSIDE", "2026-10-23T20:00:00"),
        _article("AFTER", "2026-10-24T01:00:00"),
    ])
    assert "INSIDE" in out and "BEFORE" not in out and "AFTER" not in out


@pytest.mark.unit
def test_the_most_recent_articles_are_kept_up_to_the_configured_limit(key):
    limit = get_config()["news_article_limit"]
    articles = [_article(f"N{i:03d}", f"2026-10-{16 + i % 7}T{i % 24:02d}:00:00") for i in range(limit + 30)]
    out, _ = _news(articles)
    assert out.count("### ") == limit
    newest = max(articles, key=lambda a: a["datetime"])["headline"]
    assert out.index(newest) < out.index("### ", out.index(newest) + 1)


@pytest.mark.unit
def test_the_request_asks_for_the_canonical_symbol_and_the_window(key):
    _, get = _news([_article("X", "2026-10-20T12:00:00")])
    params = get.call_args.kwargs["params"]
    assert params["symbol"] == "AAPL"
    assert (params["from"], params["to"]) == ("2026-10-16", "2026-10-23")
    assert get.call_args.kwargs["secret"] == "secret-key"


@pytest.mark.unit
def test_an_article_without_a_summary_is_still_listed(key):
    out, _ = _news([_article("BARE", "2026-10-20T12:00:00", summary="")])
    assert "### BARE" in out


@pytest.mark.unit
def test_no_article_in_the_window_is_no_data(key):
    with pytest.raises(NoMarketDataError):
        _news([_article("OLD", "2026-09-01T12:00:00")])


@pytest.mark.unit
@pytest.mark.parametrize("status", [401, 403, 429])
def test_a_refused_or_throttled_request_is_unavailable(key, status):
    # 403 is the free plan refusing a non-US listing; 429 the per-minute limit.
    with pytest.raises(VendorUnavailableError):
        _news({"error": "You don't have access to this resource."}, status=status, ticker="BCP.LS")


@pytest.mark.unit
def test_an_answer_that_is_not_a_list_is_unavailable(key):
    with pytest.raises(VendorUnavailableError):
        _news({"error": "unexpected"})


@pytest.mark.unit
def test_without_a_key_the_vendor_is_not_configured(monkeypatch):
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
    with pytest.raises(VendorNotConfiguredError):
        finnhub.get_news("AAPL", "2026-10-16", "2026-10-23")


@pytest.mark.unit
def test_the_company_news_chain_can_be_set_from_the_environment(monkeypatch):
    # The built-in default stays Yahoo; a launcher picks Finnhub first without
    # editing code (#1467 asked for this).
    monkeypatch.setenv("TRADINGAGENTS_NEWS_VENDOR", "finnhub,yfinance")
    assert default_config.build_default_config()["tool_vendors"]["get_news"] == "finnhub,yfinance"


@pytest.mark.unit
def test_the_variable_leaves_the_other_news_tools_on_their_vendor(monkeypatch):
    # Finnhub serves company news only; global news and insider trades must not
    # be routed to a chain with no vendor for them, even when it names Finnhub alone.
    monkeypatch.setenv("TRADINGAGENTS_NEWS_VENDOR", "finnhub")
    config = default_config.build_default_config()
    assert config["data_vendors"]["news_data"] == "yfinance"
    set_config(config)
    assert router.get_vendor("news_data", "get_global_news") == "yfinance"
    assert router.get_vendor("news_data", "get_insider_transactions") == "yfinance"


@pytest.mark.unit
def test_without_the_variable_news_keeps_the_built_in_vendor(monkeypatch):
    monkeypatch.delenv("TRADINGAGENTS_NEWS_VENDOR", raising=False)
    config = default_config.build_default_config()
    assert config["data_vendors"]["news_data"] == "yfinance"
    assert "get_news" not in config["tool_vendors"]


@pytest.mark.unit
def test_a_listing_finnhub_refuses_is_served_by_yahoo(key):
    set_config({"data_vendors": {"news_data": "finnhub,yfinance"}})
    yahoo = mock.Mock(return_value="YAHOO NEWS")
    with mock.patch.dict(router.VENDOR_METHODS["get_news"], {"yfinance": yahoo}), \
         mock.patch.object(finnhub, "get_scrubbed", return_value=_Response(403, {"error": "no access"})):
        out = router.route_to_vendor("get_news", "BCP.LS", "2026-10-16", "2026-10-23")
    assert out == "YAHOO NEWS"
