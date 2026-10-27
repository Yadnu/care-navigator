"""Phase 3: env switches, model ids and confidence gating in navigator/config.py."""
from __future__ import annotations

import pytest

from navigator import config

KEYS = ["ANTHROPIC_API_KEY", "JEV_API_KEY", "VOYAGE_API_KEY"]


@pytest.fixture
def no_keys(monkeypatch):
    for k in KEYS:
        monkeypatch.delenv(k, raising=False)


def test_offline_by_default(no_keys):
    assert not config.claude_enabled()
    assert not config.jev_enabled()
    assert not config.voyage_enabled()


@pytest.mark.parametrize("key, switch", [
    ("ANTHROPIC_API_KEY", config.claude_enabled),
    ("JEV_API_KEY", config.jev_enabled),
    ("VOYAGE_API_KEY", config.voyage_enabled),
])
def test_each_key_switches_on_its_provider(no_keys, monkeypatch, key, switch):
    monkeypatch.setenv(key, "test-key")
    assert switch()


def test_blank_key_stays_offline(no_keys, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "   ")
    assert not config.claude_enabled()


def test_model_ids():
    assert config.CLAUDE_MODEL == "claude-haiku-5-5"
    assert config.JUDGE_MODEL == "claude-sonnet-5-5"


@pytest.mark.parametrize("confidence, action", [("high", "act"), ("medium", "escalate"), ("low", "ask")])
def test_confidence_gate(confidence, action):
    assert config.confidence_action(confidence) == action


def test_unknown_confidence_asks():
    assert config.confidence_action("unsure") == "ask"


def test_thresholds_are_probabilities():
    for name in ["JEV_EMERGENCY_THRESHOLD", "JEV_VAGUE_THRESHOLD", "GUARD_THRESHOLD"]:
        assert 0 < getattr(config, name) < 1
