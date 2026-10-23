"""A re-run on the same day replaces the day's decision while it is still pending.

The log kept the first decision per ticker and date. A live user re-runs the
same day when new data lands (a 10-Q filed since the morning) or to debate
longer, and the first, weaker decision stayed: TXN's shallow Overweight blocked
the medium Hold that followed it. A pending entry has fed no outcome or
reflection yet, so the latest run replaces it; a settled one is still kept, so
no decision is counted twice.
"""

import pytest

from tradingagents.memory import TradingMemoryLog

FIRST = "**Rating**: Overweight\n\nStart a small TXN position."
LATEST = "**Rating**: Hold\n\nDo not open a TXN position yet."


def _log(tmp_path):
    return TradingMemoryLog({"memory_log_path": str(tmp_path / "trading_memory.md")})


@pytest.mark.unit
def test_the_latest_run_of_the_day_replaces_a_pending_decision(tmp_path):
    log = _log(tmp_path)
    log.store_decision("TXN", "2026-10-23", FIRST)
    log.store_decision("TXN", "2026-10-23", LATEST)

    entries = log.load_entries()
    assert len(entries) == 1
    assert entries[0]["rating"] == "Hold" and entries[0]["pending"] is True
    assert "Do not open" in entries[0]["decision"] and "Start a small" not in entries[0]["decision"]


@pytest.mark.unit
def test_other_entries_keep_their_place_and_text(tmp_path):
    log = _log(tmp_path)
    log.store_decision("NVDA", "2026-10-22", "**Rating**: Overweight\n\nnvda")
    log.store_decision("TXN", "2026-10-23", FIRST)
    log.store_decision("TXN", "2026-10-22", "**Rating**: Sell\n\nolder txn")
    log.store_decision("TXN", "2026-10-23", LATEST)

    entries = log.load_entries()
    assert [(e["ticker"], e["date"], e["rating"]) for e in entries] == [
        ("NVDA", "2026-10-22", "Overweight"),
        ("TXN", "2026-10-23", "Hold"),
        ("TXN", "2026-10-22", "Sell"),
    ]


@pytest.mark.unit
def test_a_settled_decision_is_still_not_replaced(tmp_path):
    log = _log(tmp_path)
    log.store_decision("TXN", "2026-10-23", FIRST)
    log.update_with_outcome("TXN", "2026-10-23", 0.03, 0.01, 5, "worked", "2026-10-30")
    log.store_decision("TXN", "2026-10-23", LATEST)

    entries = log.load_entries()
    assert len(entries) == 1
    assert entries[0]["rating"] == "Overweight" and entries[0]["pending"] is False


@pytest.mark.unit
def test_the_replaced_log_still_reads_back_whole(tmp_path):
    log = _log(tmp_path)
    for text in (FIRST, LATEST, FIRST):
        log.store_decision("TXN", "2026-10-23", text)
    log.store_decision("AAPL", "2026-10-23", "**Rating**: Hold\n\naapl")
    raw = (tmp_path / "trading_memory.md").read_text(encoding="utf-8")
    assert raw.count("[2026-10-23 | TXN |") == 1
    assert [e["ticker"] for e in log.load_entries()] == ["TXN", "AAPL"]
