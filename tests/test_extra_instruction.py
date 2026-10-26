"""extra_instruction: empty leaves prompts unchanged, set it reaches every agent via the language suffix."""

from __future__ import annotations

import tradingagents.default_config as default_config_module
from tradingagents.agents.context import get_language_instruction
from tradingagents.dataflows.config import get_config, set_config


def _with(monkeypatch, **cfg):
    original = dict(get_config())
    set_config({**original, **cfg})
    return original


def test_default_is_empty_and_english_adds_nothing(monkeypatch):
    original = _with(monkeypatch, output_language="English", extra_instruction="")
    try:
        assert get_language_instruction() == ""
    finally:
        set_config(original)


def test_extra_instruction_alone_and_with_language(monkeypatch):
    original = _with(monkeypatch, output_language="English", extra_instruction="Judge over 5 years.")
    try:
        assert get_language_instruction() == " Judge over 5 years."
        set_config({**get_config(), "output_language": "Portuguese"})
        text = get_language_instruction()
        assert "Portuguese" in text and text.endswith(" Judge over 5 years.")
    finally:
        set_config(original)


def test_env_override(monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_EXTRA_INSTRUCTION", "Judge over 5 years.")
    assert default_config_module.build_default_config()["extra_instruction"] == "Judge over 5 years."
