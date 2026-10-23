"""The Yahoo overview carries the next earnings date and the analyst consensus.

``Ticker.info`` already holds the next earnings timestamp, whether Yahoo has it
confirmed, and the analysts' price targets and rating; ``Ticker.calendar`` holds
the EPS and revenue estimates for the quarter being reported. Without them an
analyst cannot say when the next catalyst lands or what the market expects of it.
Both are live-only, so a historical run withholds them with the rest of the
profile (#1300), and a calendar that fails never costs the overview.
"""

from unittest import mock

import pytest

from tradingagents.dataflows import date_window
from tradingagents.dataflows.errors import VendorUnavailableError
from tradingagents.dataflows.vendors.yahoo import fundamentals

TODAY = "2026-10-23"

_INFO = {
    "longName": "Apple Inc.",
    "currency": "USD",
    "financialCurrency": "USD",
    "exchangeTimezoneName": "America/New_York",
    "earningsTimestamp": 1793649600,  # 2026-11-02 20:00 UTC
    "earningsCallTimestampStart": 1793656800,  # 2026-11-02 22:00 UTC
    "isEarningsDateEstimate": False,
    "targetMeanPrice": 328.35,
    "targetMedianPrice": 335.0,
    "targetHighPrice": 405.0,
    "targetLowPrice": 215.0,
    "recommendationKey": "buy",
    "recommendationMean": 2.25,
    "numberOfAnalystOpinions": 39,
}

_CALENDAR = {
    "Earnings Average": 1.98187, "Earnings Low": 1.93, "Earnings High": 2.06,
    "Revenue Average": 113357085200, "Revenue Low": 112525022000, "Revenue High": 116186700000,
}


def _fundamentals(info=_INFO, calendar=None, as_of=TODAY):
    with mock.patch.object(date_window, "get_current_date", return_value=TODAY), \
         mock.patch.object(fundamentals, "yf_retry", lambda fn: info), \
         mock.patch.object(fundamentals, "_earnings_calendar", return_value=calendar or {}):
        return fundamentals.get_fundamentals("AAPL", as_of)


@pytest.mark.unit
def test_analyst_targets_rating_and_coverage_are_served():
    out = _fundamentals()
    assert "Analyst Target Mean: 328.35 USD" in out
    assert "Analyst Target Range: 215.0 - 405.0 USD (median 335.0)" in out
    assert "Analyst Recommendation: buy (mean 2.25, 1 strong buy - 5 strong sell)" in out
    assert "Number of Analyst Opinions: 39" in out


@pytest.mark.unit
def test_next_earnings_date_is_given_in_the_exchange_time_zone_and_says_it_is_confirmed():
    out = _fundamentals()
    assert "Next Earnings Date: 2026-11-02 (confirmed by Yahoo)" in out
    # US daylight saving ends on 2026-11-01, so 22:00 UTC is 17:00 EST.
    assert "Earnings Call: 2026-11-02 17:00 EST" in out


@pytest.mark.unit
def test_an_earnings_date_yahoo_estimates_is_labelled_an_estimate():
    out = _fundamentals({**_INFO, "isEarningsDateEstimate": True})
    assert "Next Earnings Date: 2026-11-02 (estimated by Yahoo, not confirmed)" in out


@pytest.mark.unit
def test_the_earnings_date_follows_the_exchange_day_not_the_utc_day():
    # 2026-11-03 02:00 UTC is still the evening of 2026-11-02 in New York.
    out = _fundamentals({**_INFO, "earningsTimestamp": 1793671200})
    assert "Next Earnings Date: 2026-11-02" in out


@pytest.mark.unit
def test_an_earnings_date_already_past_is_not_called_the_next_one():
    # Yahoo keeps the date just reported until it publishes the next one.
    out = _fundamentals({**_INFO, "earningsTimestamp": 1792180800})  # 2026-10-16
    assert "Next Earnings Date" not in out
    assert "Latest Earnings Date: 2026-10-16 (already reported; Yahoo has no later date yet)" in out


@pytest.mark.unit
def test_quarter_estimates_come_from_the_calendar():
    out = _fundamentals(calendar=_CALENDAR)
    assert "Next Quarter EPS Estimate: 1.98187 USD (low 1.93, high 2.06)" in out
    assert "Next Quarter Revenue Estimate: 113357085200 USD (low 112525022000, high 116186700000)" in out


@pytest.mark.unit
def test_without_a_calendar_the_overview_is_still_served():
    out = _fundamentals(calendar={})
    assert "Name: Apple Inc." in out
    assert "Next Earnings Date" in out
    assert "EPS Estimate" not in out


@pytest.mark.unit
def test_a_profile_without_earnings_or_analyst_fields_adds_no_section():
    out = _fundamentals({"longName": "Some Fund", "currency": "USD"})
    assert "Analyst" not in out and "Earnings" not in out


@pytest.mark.unit
def test_a_historical_run_requests_no_calendar():
    with mock.patch.object(date_window, "get_current_date", return_value=TODAY), \
         mock.patch.object(fundamentals, "yf_retry", side_effect=AssertionError("requested")), \
         mock.patch.object(fundamentals, "_earnings_calendar", side_effect=AssertionError("requested")):
        out = fundamentals.get_fundamentals("AAPL", "2025-05-09")
    assert "withheld" in out and "Next Earnings" not in out


@pytest.mark.unit
def test_a_calendar_request_that_fails_reads_as_no_calendar():
    def fail(fn):
        raise VendorUnavailableError("Yahoo Finance request failed")

    with mock.patch.object(fundamentals, "yf_retry", fail):
        assert fundamentals._earnings_calendar("AAPL") == {}


@pytest.mark.unit
@pytest.mark.parametrize("answer", [None, [], "not a calendar"])
def test_a_calendar_that_is_not_a_dict_reads_as_no_calendar(answer):
    with mock.patch.object(fundamentals, "yf_retry", lambda fn: answer):
        assert fundamentals._earnings_calendar("AAPL") == {}
