"""Review findings on the company-facts refresh: SEC's own day, odd indexes, the memo clock."""

import json
import os

import pytest

from tradingagents.dataflows.vendors import sec_edgar

CIK = "0001181412"
TICKER_MAP = {"0": {"cik_str": 1181412, "ticker": "SPCX", "title": "Space Exploration Technologies Corp."}}
OLD = {"facts": {"us-gaap": {"Revenues": {"units": {"USD": [
    {"start": "2026-04-01", "end": "2026-06-30", "val": 7.8e9, "filed": "2026-08-04", "form": "10-Q"}]}}}}}
NEW = {"facts": {"us-gaap": {"Revenues": {"units": {"USD": [
    *OLD["facts"]["us-gaap"]["Revenues"]["units"]["USD"],
    {"start": "2026-07-01", "end": "2026-09-30", "val": 14.6e9, "filed": "2026-10-22", "form": "10-Q"}]}}}}}

# 2026-10-22 22:00 in New York is already 2026-10-23 in Lisbon and further east.
LATE_EVENING_ET = 1792720800


@pytest.fixture
def cache(tmp_path, monkeypatch):
    monkeypatch.setattr(sec_edgar, "get_config", lambda: {"data_cache_dir": str(tmp_path)})
    sec_edgar._SUBMISSIONS_MEMO.clear()
    path = tmp_path / "sec_edgar" / f"CIK{CIK}.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(OLD))
    os.utime(path, (LATE_EVENING_ET, LATE_EVENING_ET))
    monkeypatch.setattr(sec_edgar.time, "time", lambda: LATE_EVENING_ET + 3600)
    yield path
    sec_edgar._SUBMISSIONS_MEMO.clear()


def _serve(monkeypatch, submissions):
    calls = []

    def fetch(url):
        calls.append(url)
        if "company_tickers" in url:
            return TICKER_MAP
        return submissions if "submissions" in url else NEW

    monkeypatch.setattr(sec_edgar, "_fetch_json", fetch)
    return calls


@pytest.mark.unit
def test_the_cache_day_is_read_on_sec_s_clock(cache, monkeypatch):
    # Fetched late on the filing day in New York: the 10-Q filed that day may be
    # missing, whatever the local date says.
    calls = _serve(monkeypatch, {"filings": {"recent": {"form": ["10-Q"], "filingDate": ["2026-10-22"]}}})
    out = sec_edgar.get_income_statement("SPCX", "quarterly", "2026-10-23")
    assert any("companyfacts" in url for url in calls) and "2026-09-30" in out


@pytest.mark.unit
@pytest.mark.parametrize("recent", [
    {"form": [None, "10-Q"], "filingDate": ["2026-10-22", "2026-10-22"]},
    {"form": ["10-Q"], "filingDate": [None]},
])
def test_an_index_with_empty_fields_serves_the_cache(cache, monkeypatch, recent):
    _serve(monkeypatch, {"filings": {"recent": recent}})
    assert "2026-06-30" in sec_edgar.get_income_statement("SPCX", "quarterly", "2026-10-23")


@pytest.mark.unit
def test_the_index_memo_expires_on_a_monotonic_clock(cache, monkeypatch):
    calls = _serve(monkeypatch, {"filings": {"recent": {"form": ["10-Q"], "filingDate": ["2026-08-04"]}}})
    clock = [1000.0]
    monkeypatch.setattr(sec_edgar.time, "monotonic", lambda: clock[0])
    sec_edgar.get_income_statement("SPCX", "quarterly", "2026-10-23")
    clock[0] += sec_edgar._SUBMISSIONS_TTL_SECONDS + 1
    sec_edgar.get_income_statement("SPCX", "quarterly", "2026-10-23")
    assert len([url for url in calls if "submissions" in url]) == 2
