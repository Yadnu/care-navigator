"""Env switches, model ids, thresholds and limits.

Offline is the default (D-008): a provider switches on only when its API key is set.
Keys are read at call time so tests can toggle them with monkeypatch.
"""
from __future__ import annotations

import os

# ------------------------------------------------------------------ providers
CLAUDE_MODEL = "claude-haiku-5-5"   # extraction, follow-up question, explanation (D-004)
JUDGE_MODEL = "claude-sonnet-5-5"   # offline evaluation judge only (D-004)
CLAUDE_TIMEOUT_S = 15.0
CLAUDE_MAX_TOKENS = 1024

# TODO: verify against Jev docs - endpoint is a placeholder until the real one is confirmed.
JEV_BASE_URL = os.environ.get("JEV_BASE_URL", "https://api.jev.example/v1/ask")
JEV_TIMEOUT_S = 5.0


def _has(key: str) -> bool:
    return bool(os.environ.get(key, "").strip())


def claude_enabled() -> bool:
    return _has("ANTHROPIC_API_KEY")


def jev_enabled() -> bool:
    return _has("JEV_API_KEY")


def voyage_enabled() -> bool:
    return _has("VOYAGE_API_KEY")


# ------------------------------------------------------------------ thresholds
# Red-flag fuzzy matching (D-014): a token window must reach this RapidFuzz ratio,
# and tokens shorter than FUZZY_MIN_TOKEN_LEN must match exactly ("can" != "cant").
FUZZY_THRESHOLD = 88
FUZZY_MIN_TOKEN_LEN = 4

# Jev probabilities at or above these count as "yes" (D-019).
JEV_EMERGENCY_THRESHOLD = 0.5
JEV_VAGUE_THRESHOLD = 0.5
GUARD_THRESHOLD = 0.5

# ------------------------------------------------------------------ confidence gating
# high -> act on the rule; medium -> escalate one level; low -> ask the follow-up (D-003).
CONFIDENCE_ACTIONS = {"high": "act", "medium": "escalate", "low": "ask"}


def confidence_action(confidence: str) -> str:
    """Unknown confidence is treated as low: ask rather than guess."""
    return CONFIDENCE_ACTIONS.get(confidence, "ask")
