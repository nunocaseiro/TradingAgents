"""A report that adds no facts does not refetch the company facts on every run.

Some amendments carry no financial data, so no fact ever bears their filing
date. A cache fetched after the report's filing day already holds whatever SEC
published for it, so it is kept.
"""

import json
import os
import time

import pytest

from tradingagents.dataflows.vendors import sec_edgar

CIK = "0001181412"
TICKER_MAP = {"0": {"cik_str": 1181412, "ticker": "SPCX", "title": "Space Exploration Technologies Corp."}}
FACTS = {"facts": {"us-gaap": {"Revenues": {"units": {"USD": [
    {"start": "2026-04-01", "end": "2026-06-30", "val": 7.8e9, "filed": "2026-08-04", "form": "10-Q"}]}}}}}


@pytest.mark.unit
def test_a_cache_fetched_after_the_report_day_is_kept(tmp_path, monkeypatch):
    monkeypatch.setattr(sec_edgar, "get_config", lambda: {"data_cache_dir": str(tmp_path)})
    sec_edgar._SUBMISSIONS_MEMO.clear()
    path = tmp_path / "sec_edgar" / f"CIK{CIK}.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(FACTS))
    # Fetched at noon on 2026-10-23, the day after a facts-less 10-Q/A was filed.
    noon = time.mktime(time.strptime("2026-10-23 12:00", "%Y-%m-%d %H:%M"))
    os.utime(path, (noon, noon))
    monkeypatch.setattr(sec_edgar.time, "time", lambda: noon + 60)
    calls = []

    def fetch(url):
        calls.append(url)
        if "company_tickers" in url:
            return TICKER_MAP
        if "submissions" in url:
            return {"filings": {"recent": {"form": ["10-Q/A"], "filingDate": ["2026-10-22"]}}}
        return FACTS

    monkeypatch.setattr(sec_edgar, "_fetch_json", fetch)
    sec_edgar.get_income_statement("SPCX", "quarterly", "2026-10-23")
    assert not any("companyfacts" in url for url in calls)
