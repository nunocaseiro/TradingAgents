"""Edge cases of the FOMC schedule note found in review of the calendar table."""

import pytest

from tradingagents.dataflows import fomc


@pytest.mark.unit
def test_a_date_past_the_table_is_not_told_a_stale_last_decision():
    # Meetings after the table's end were held but are not listed.
    assert "Last FOMC decision" not in fomc.schedule_note("2028-06-01")


@pytest.mark.unit
def test_a_trade_date_with_a_time_part_is_read_by_its_day():
    note = fomc.schedule_note("2026-10-28 00:00:00")
    assert "Next scheduled FOMC decisions: 2026-10-28" in note
