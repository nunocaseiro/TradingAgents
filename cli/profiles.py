"""Run profiles: a named bundle of CLI settings, chosen in one menu step.

A profile changes how a run is configured, never what the agents are told: the
prompts are the same under every profile. It sets the analyst team, the debate
depth, the horizon over which a decision is later scored and its benchmark, and
keeps its own memory log and reports directory, so decisions made under one
horizon are never re-scored under another.

Paths are relative to the working directory. An explicit TRADINGAGENTS_* variable
for the same setting wins over the profile, as it does over the other menu steps.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from cli.models import AnalystType


@dataclass(frozen=True)
class Profile:
    key: str
    label: str
    # None leaves the choice to the menu (analysts) or the config default.
    analysts: tuple[AnalystType, ...] | None
    rounds: int | None
    holding_period_days: int | None
    benchmark_ticker: str | None
    memory_log_path: str
    results_dir: str | None


PROFILES = {
    "buffett": Profile(
        "buffett", "Buffett - long-term holdings (news + fundamentals, 5 rounds, ~252 days vs VT)",
        (AnalystType.NEWS, AnalystType.FUNDAMENTALS), 5, 252, "VT",
        "memory/buffett_memory.md", "reports/buffett",
    ),
    "livre": Profile(
        "livre", "Livre - native settings, with its own memory log",
        None, None, None, None, "memory/livre_memory.md", None,
    ),
}


def get_profile(key: str) -> Profile:
    """The profile named ``key``; a name that is not one raises ValueError."""
    try:
        return PROFILES[key.strip().lower()]
    except KeyError:
        raise ValueError(f"Unknown profile '{key}'. Choose one of: {', '.join(PROFILES)}.") from None


def apply_profile(config: dict, key: str | None) -> dict:
    """Fold a profile into ``config`` in place; settings given by environment win."""
    if not key:
        return config
    profile = get_profile(key)
    env = os.environ.get
    if profile.holding_period_days and not env("TRADINGAGENTS_HOLDING_PERIOD_DAYS"):
        config["holding_period_days"] = profile.holding_period_days
    if profile.benchmark_ticker and not env("TRADINGAGENTS_BENCHMARK_TICKER"):
        config["benchmark_ticker"] = profile.benchmark_ticker
    if not env("TRADINGAGENTS_MEMORY_LOG_PATH"):
        config["memory_log_path"] = profile.memory_log_path
    if profile.results_dir and not env("TRADINGAGENTS_RESULTS_DIR"):
        config["results_dir"] = profile.results_dir
    return config
