"""Scheduled FOMC decision dates for the news analyst.

The Fed publishes its meeting calendar more than a year ahead, so the dates a
run is shown were public on its analysis date and carry no look-ahead. No free
API serves them (Finnhub's economic calendar is a paid endpoint), so they live
in a table that is extended when the Fed publishes a new year.
"""

from datetime import date, timedelta

import pytest

from tradingagents.dataflows import fomc


@pytest.mark.unit
def test_the_next_decisions_after_the_analysis_date_are_listed():
    note = fomc.schedule_note("2026-10-23")
    assert "2026-10-28 (meeting 2026-10-27 to 2026-10-28)" in note
    assert "2026-12-09 (meeting 2026-12-08 to 2026-12-09, with economic projections)" in note
    assert note.index("2026-10-28") < note.index("2026-12-09")


@pytest.mark.unit
def test_the_last_decision_before_the_analysis_date_is_given():
    assert "Last FOMC decision: 2026-09-16" in fomc.schedule_note("2026-10-23")


@pytest.mark.unit
def test_a_decision_on_the_analysis_date_counts_as_upcoming():
    # The statement comes at 14:00 ET, after a run made that morning.
    note = fomc.schedule_note("2026-10-28")
    assert "Next scheduled FOMC decisions: 2026-10-28" in note


@pytest.mark.unit
def test_a_date_before_the_table_gets_no_schedule():
    # Earlier meetings are not in the table, so "next" would be wrong.
    assert fomc.schedule_note("2025-06-01") == ""


@pytest.mark.unit
def test_a_date_past_the_table_says_the_schedule_is_unknown():
    note = fomc.schedule_note("2028-06-01")
    assert "not in this build" in note and "do not guess" in note


@pytest.mark.unit
def test_the_table_reaches_at_least_six_months_ahead():
    # Fails on purpose when the table needs the Fed's next published year:
    # https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm
    last_decision = date.fromisoformat(fomc.FOMC_MEETINGS[-1][1])
    assert last_decision >= date.today() + timedelta(days=180), "extend FOMC_MEETINGS"


@pytest.mark.unit
def test_meetings_are_ordered_and_each_ends_on_or_after_it_starts():
    starts = [start for start, _, _ in fomc.FOMC_MEETINGS]
    assert starts == sorted(starts)
    assert all(start <= end for start, end, _ in fomc.FOMC_MEETINGS)


@pytest.mark.unit
def test_the_news_analyst_is_given_the_schedule_for_its_trade_date(monkeypatch):
    from tradingagents.agents.analysts import news_analyst

    seen = {}

    def capture(prompt, llm, tools, messages):
        seen["system"] = prompt.format_messages(messages=[])[0].content
        return None, "report"

    monkeypatch.setattr(news_analyst, "take_turn", capture)
    news_analyst.create_news_analyst(llm=None)({"trade_date": "2026-10-23", "messages": [],
                                                "company_of_interest": "AAPL"})
    assert "Next scheduled FOMC decisions: 2026-10-28" in seen["system"]
    assert "earnings" in seen["system"]
