"""TA_ANTHROPIC_API_KEY stands in for ANTHROPIC_API_KEY (cloud sessions reserve that name)."""

import importlib

import tradingagents


def test_ta_key_sets_anthropic_key(monkeypatch):
    monkeypatch.setenv("TA_ANTHROPIC_API_KEY", "ta-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "other")
    importlib.reload(tradingagents)
    import os
    assert os.environ["ANTHROPIC_API_KEY"] == "ta-key"


def test_without_ta_key_anthropic_key_is_untouched(monkeypatch):
    monkeypatch.delenv("TA_ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "mine")
    importlib.reload(tradingagents)
    import os
    assert os.environ["ANTHROPIC_API_KEY"] == "mine"
