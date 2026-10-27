"""Shared fixtures. Tests always run offline (D-008): provider keys are cleared for every test,
so keys exported in the developer's shell or loaded from .env can never cause a network call."""
from __future__ import annotations

import pytest

PROVIDER_ENV = ["ANTHROPIC_API_KEY", "JEV_API_KEY", "VOYAGE_API_KEY", "JEV_BASE_URL", "JEV_MODEL"]


@pytest.fixture(autouse=True)
def offline_env(monkeypatch):
    for key in PROVIDER_ENV:
        # setenv first so monkeypatch records the key and removes anything a test
        # (e.g. config.load_env_file) writes to os.environ directly.
        monkeypatch.setenv(key, "")
        monkeypatch.delenv(key)
