"""Company facts are refetched when the company filed a report the cache lacks.

The facts file is cached for a day. A 10-Q filed after the fetch was invisible
until the day ran out: SPCX's Q3 10-Q, filed 2026-10-22, was missing from a
2026-10-23 run whose cache dated from the evening before. The filing index
(EDGAR submissions) is small and read fresh, so a report newer than every fact
in the cache forces a refetch. All network access is mocked.
"""

import contextlib
import json
import os
import time

import pytest

from tradingagents.dataflows.vendors import sec_edgar

TICKER_MAP = {"0": {"cik_str": 1181412, "ticker": "SPCX", "title": "Space Exploration Technologies Corp."}}
CIK = "0001181412"


def _facts(*quarters):
    """Company facts with one quarterly revenue fact per (end, filed) pair."""
    values = [{"start": f"{end[:4]}-{int(end[5:7]) - 2:02d}-01", "end": end, "val": 1e9 * (i + 1),
               "filed": filed, "form": "10-Q", "fp": "Q", "fy": int(end[:4])}
              for i, (end, filed) in enumerate(quarters)]
    return {"facts": {"us-gaap": {"Revenues": {"units": {"USD": values}}}}}


OLD = _facts(("2026-06-30", "2026-08-04"))
NEW = _facts(("2026-06-30", "2026-08-04"), ("2026-09-30", "2026-10-22"))


def _submissions(*filings):
    forms, dates = zip(*filings, strict=True) if filings else ((), ())
    return {"filings": {"recent": {"form": list(forms), "filingDate": list(dates)}}}


@pytest.fixture
def cache(tmp_path, monkeypatch):
    monkeypatch.setattr(sec_edgar, "get_config", lambda: {"data_cache_dir": str(tmp_path)})
    sec_edgar._SUBMISSIONS_MEMO.clear()
    path = tmp_path / "sec_edgar" / f"CIK{CIK}.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(OLD))
    # As in the SPCX run: cached at 18:12 on the 10-Q's filing day, read the next day.
    fetched = time.mktime(time.strptime("2026-10-22 18:12", "%Y-%m-%d %H:%M"))
    os.utime(path, (fetched, fetched))
    monkeypatch.setattr(sec_edgar.time, "time", lambda: fetched + 18 * 3600)
    return path


def _serve(monkeypatch, submissions, facts=NEW):
    calls = []

    def fetch(url):
        calls.append(url)
        if "company_tickers" in url:
            return TICKER_MAP
        if "submissions" in url:
            if isinstance(submissions, Exception):
                raise submissions
            return submissions
        return facts

    monkeypatch.setattr(sec_edgar, "_fetch_json", fetch)
    return calls


@pytest.mark.unit
def test_a_report_filed_after_the_cache_forces_a_refetch(cache, monkeypatch):
    calls = _serve(monkeypatch, _submissions(("10-Q", "2026-10-22"), ("8-K", "2026-10-20")))
    out = sec_edgar.get_income_statement("SPCX", "quarterly", "2026-10-23")
    assert "2026-09-30" in out
    assert any("companyfacts" in url for url in calls)


@pytest.mark.unit
def test_a_cache_that_holds_the_latest_report_is_not_refetched(cache, monkeypatch):
    calls = _serve(monkeypatch, _submissions(("10-Q", "2026-08-04")))
    sec_edgar.get_income_statement("SPCX", "quarterly", "2026-10-23")
    assert not any("companyfacts" in url for url in calls)


@pytest.mark.unit
def test_a_newer_filing_that_is_not_a_report_does_not_refetch(cache, monkeypatch):
    # An 8-K carries no statement facts, so it says nothing about the cache.
    calls = _serve(monkeypatch, _submissions(("8-K", "2026-10-20"), ("10-Q", "2026-08-04")))
    sec_edgar.get_income_statement("SPCX", "quarterly", "2026-10-23")
    assert not any("companyfacts" in url for url in calls)


@pytest.mark.unit
def test_an_amended_report_counts_as_a_report(cache, monkeypatch):
    calls = _serve(monkeypatch, _submissions(("10-Q/A", "2026-10-22")))
    sec_edgar.get_income_statement("SPCX", "quarterly", "2026-10-23")
    assert any("companyfacts" in url for url in calls)


@pytest.mark.unit
def test_an_unreachable_filing_index_serves_the_cache(cache, monkeypatch):
    _serve(monkeypatch, sec_edgar.VendorUnavailableError("SEC EDGAR request failed (503)"))
    out = sec_edgar.get_income_statement("SPCX", "quarterly", "2026-10-23")
    assert "2026-06-30" in out and "2026-09-30" not in out


@pytest.mark.unit
def test_a_filing_index_without_filings_serves_the_cache(cache, monkeypatch):
    calls = _serve(monkeypatch, {"name": "unexpected"})
    sec_edgar.get_income_statement("SPCX", "quarterly", "2026-10-23")
    assert not any("companyfacts" in url for url in calls)


@pytest.mark.unit
def test_the_filing_index_is_read_once_for_several_statements(cache, monkeypatch):
    calls = _serve(monkeypatch, _submissions(("10-Q", "2026-10-22")))
    for get in (sec_edgar.get_income_statement, sec_edgar.get_balance_sheet, sec_edgar.get_cashflow):
        with contextlib.suppress(sec_edgar.NoMarketDataError):  # the fixture tags revenue only
            get("SPCX", "quarterly", "2026-10-23")
    assert len([url for url in calls if "submissions" in url]) == 1
    assert len([url for url in calls if "companyfacts" in url]) == 1
