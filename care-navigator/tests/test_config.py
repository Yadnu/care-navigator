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


def test_jev_endpoint_and_model_defaults():
    assert config.jev_base_url() == "https://api.typesafe.ai/v1/systemone"
    assert config.jev_model() == "jev-latest"


def test_jev_endpoint_and_model_from_env(monkeypatch):
    monkeypatch.setenv("JEV_BASE_URL", "https://jev.test/v1/systemone")
    monkeypatch.setenv("JEV_MODEL", "jev-1.14.0")
    assert config.jev_base_url() == "https://jev.test/v1/systemone"
    assert config.jev_model() == "jev-1.14.0"


def test_blank_jev_settings_use_defaults(monkeypatch):
    monkeypatch.setenv("JEV_BASE_URL", "")
    monkeypatch.setenv("JEV_MODEL", "  ")
    assert config.jev_base_url() == "https://api.typesafe.ai/v1/systemone"
    assert config.jev_model() == "jev-latest"


def test_load_env_file(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text(
        "# comment\n"
        "\n"
        "ANTHROPIC_API_KEY=sk-test\n"
        "JEV_API_KEY=\n"
        'JEV_MODEL="jev-1.13.0"\n'
        "VOYAGE_API_KEY = 'vk-test' \n"
        "not a setting\n",
        encoding="utf-8",
    )
    loaded = config.load_env_file(env)
    assert loaded == ["ANTHROPIC_API_KEY", "JEV_MODEL", "VOYAGE_API_KEY"]
    assert config.claude_enabled() and config.voyage_enabled()
    assert not config.jev_enabled()  # blank values are skipped
    assert config.jev_model() == "jev-1.13.0"


def test_load_env_file_never_overrides_real_env(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("JEV_MODEL=jev-1.13.0\n", encoding="utf-8")
    monkeypatch.setenv("JEV_MODEL", "jev-1.14.0")
    assert config.load_env_file(env) == []
    assert config.jev_model() == "jev-1.14.0"


def test_load_env_file_missing_file_is_fine(tmp_path):
    assert config.load_env_file(tmp_path / "nope.env") == []


def test_importing_config_does_not_load_dotenv():
    import importlib
    import os

    importlib.reload(config)
    assert "ANTHROPIC_API_KEY" not in os.environ


def test_thresholds_are_probabilities():
    for name in ["JEV_EMERGENCY_THRESHOLD", "JEV_VAGUE_THRESHOLD", "GUARD_THRESHOLD"]:
        assert 0 < getattr(config, name) < 1
