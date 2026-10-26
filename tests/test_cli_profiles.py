"""Run profiles (pote / buffett / livre) and the configurable scoring horizon."""

from __future__ import annotations

import pytest

import cli.run as cli_run
import cli.selections as cli_selections
from cli.models import AnalystType
from cli.prefs import load_last_run, save_last_run
from cli.profiles import apply_profile, get_profile
from tradingagents.default_config import build_default_config

ENV = ("TRADINGAGENTS_HOLDING_PERIOD_DAYS", "TRADINGAGENTS_BENCHMARK_TICKER",
       "TRADINGAGENTS_MEMORY_LOG_PATH", "TRADINGAGENTS_RESULTS_DIR")


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in ENV:
        monkeypatch.delenv(name, raising=False)


@pytest.mark.unit
def test_holding_period_comes_from_the_environment(monkeypatch):
    assert build_default_config()["holding_period_days"] == 5
    monkeypatch.setenv("TRADINGAGENTS_HOLDING_PERIOD_DAYS", "63")
    assert build_default_config()["holding_period_days"] == 63


@pytest.mark.unit
def test_pote_profile_config():
    config = apply_profile(build_default_config(), "pote")
    assert config["holding_period_days"] == 63
    assert config["benchmark_ticker"] == "SPY"
    assert config["memory_log_path"] == "memory/pote_memory.md"
    assert config["results_dir"] == "reports/pote"


@pytest.mark.unit
def test_buffett_profile_config():
    config = apply_profile(build_default_config(), "buffett")
    assert config["holding_period_days"] == 252
    assert config["benchmark_ticker"] == "VT"
    assert config["memory_log_path"] == "memory/buffett_memory.md"
    assert config["results_dir"] == "reports/buffett"


@pytest.mark.unit
def test_livre_only_separates_the_memory_log():
    base = build_default_config()
    config = apply_profile(dict(base), "livre")
    assert config["memory_log_path"] == "memory/livre_memory.md"
    assert {k: v for k, v in config.items() if k != "memory_log_path"} == \
           {k: v for k, v in base.items() if k != "memory_log_path"}


@pytest.mark.unit
def test_no_profile_changes_nothing():
    base = build_default_config()
    assert apply_profile(dict(base), None) == base


@pytest.mark.unit
def test_environment_wins_over_the_profile(monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_HOLDING_PERIOD_DAYS", "10")
    monkeypatch.setenv("TRADINGAGENTS_MEMORY_LOG_PATH", "/tmp/x.md")
    config = apply_profile(build_default_config(), "buffett")
    assert config["holding_period_days"] == 10
    assert config["memory_log_path"] == "/tmp/x.md"
    assert config["benchmark_ticker"] == "VT"


@pytest.mark.unit
def test_profile_names():
    assert get_profile(" Buffett ").key == "buffett"
    with pytest.raises(ValueError):
        get_profile("nope")


@pytest.mark.unit
def test_profile_analysts():
    assert set(get_profile("pote").analysts) == set(AnalystType)
    assert get_profile("buffett").analysts == (AnalystType.NEWS, AnalystType.FUNDAMENTALS)
    assert get_profile("pote").rounds == 2 and get_profile("buffett").rounds == 5


@pytest.mark.unit
def test_build_run_config_applies_the_profile():
    selections = {"research_depth": 5, "quick_think_llm": "q", "deep_think_llm": "d",
                  "backend_url": None, "llm_provider": "openai", "profile": "buffett"}
    cfg = cli_run._build_run_config(selections, None)
    assert cfg["holding_period_days"] == 252
    assert cfg["max_debate_rounds"] == 5 and cfg["max_risk_discuss_rounds"] == 5


@pytest.mark.unit
def test_profile_flag_makes_analysts_and_depth_unattended_gaps(monkeypatch):
    flags = {"ticker": "NVDA", "date": "2026-10-26", "save": True, "show": False}
    monkeypatch.delenv("TRADINGAGENTS_MAX_DEBATE_ROUNDS", raising=False)
    assert "--analysts" in cli_selections.unattended_gaps(flags)
    gaps = cli_selections.unattended_gaps({**flags, "profile": "buffett"})
    assert "--analysts" not in gaps
    assert "TRADINGAGENTS_MAX_DEBATE_ROUNDS and TRADINGAGENTS_MAX_RISK_ROUNDS" not in gaps
    assert "--analysts" in cli_selections.unattended_gaps({**flags, "profile": "livre"})


@pytest.mark.unit
def test_a_fixed_profile_does_not_overwrite_the_free_answers():
    save_last_run({"profile": "livre", "analysts": ["market"], "research_depth": 3})
    save_last_run({"profile": "buffett", "analysts": [AnalystType.NEWS], "research_depth": 5})
    saved = load_last_run()
    assert saved["profile"] == "buffett"
    assert saved["analysts"] == ["market"] and saved["research_depth"] == 3


@pytest.mark.unit
def test_a_fixed_profile_skips_the_analyst_and_depth_questions(monkeypatch):
    from tests.test_cli_headless import UNATTENDED_ENV

    for name, value in UNATTENDED_ENV.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("TRADINGAGENTS_MAX_DEBATE_ROUNDS", raising=False)
    monkeypatch.delenv("TRADINGAGENTS_MAX_RISK_ROUNDS", raising=False)

    def no_prompt(*a, **k):
        raise AssertionError("prompted although the profile answers the step")

    for step in ("select_analysts", "select_research_depth", "select_profile"):
        monkeypatch.setattr(cli_selections, step, no_prompt)
    monkeypatch.setattr(cli_selections.updates, "enabled", lambda: False)

    chosen = cli_selections._prompt_selections(
        {}, {"ticker": "MSFT", "date": "2026-10-26", "profile": "buffett"})
    assert chosen["profile"] == "buffett"
    assert chosen["analysts"] == [AnalystType.NEWS, AnalystType.FUNDAMENTALS]
    assert chosen["research_depth"] == 5
