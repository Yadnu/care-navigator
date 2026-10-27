"""Env switches, model ids, thresholds and limits.

Offline is the default (D-008): a provider switches on only when its API key is set.
Settings are read at call time so tests can toggle them with monkeypatch.
"""
from __future__ import annotations

import os
from pathlib import Path

ENV_FILE = Path(__file__).resolve().parents[1] / ".env"

# ------------------------------------------------------------------ providers
CLAUDE_MODEL = "claude-haiku-5-5"   # extraction, follow-up question, explanation (D-004)
JUDGE_MODEL = "claude-sonnet-5-5"   # offline evaluation judge only (D-004)
CLAUDE_TIMEOUT_S = 15.0
CLAUDE_MAX_TOKENS = 1024

# TypeSafe Jev API (D-023). Override with JEV_BASE_URL / JEV_MODEL.
JEV_DEFAULT_URL = "https://api.typesafe.ai/v1/systemone"
JEV_DEFAULT_MODEL = "jev-latest"
JEV_TIMEOUT_S = 5.0


def load_env_file(path: Path = ENV_FILE) -> list[str]:
    """Load KEY=value lines into os.environ (D-024).

    Called by entry points (cli, app, eval), never on import, so tests stay offline.
    Real environment variables win, blank values are skipped, and a missing file is fine.
    Returns the keys it set.
    """
    if not path.is_file():
        return []
    loaded = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = (part.strip() for part in line.split("=", 1))
        value = value.strip("'\"")
        if key and value and key not in os.environ:
            os.environ[key] = value
            loaded.append(key)
    return loaded


def _get(key: str, default: str = "") -> str:
    return os.environ.get(key, "").strip() or default


def _has(key: str) -> bool:
    return bool(_get(key))


VOYAGE_URL = "https://api.voyageai.com/v1/embeddings"
VOYAGE_DEFAULT_MODEL = "voyage-4"
VOYAGE_TIMEOUT_S = 10.0
VOYAGE_BATCH_SIZE = 128  # API allows up to 1,000 texts per request


def voyage_model() -> str:
    return _get("VOYAGE_MODEL", VOYAGE_DEFAULT_MODEL)


def jev_base_url() -> str:
    return _get("JEV_BASE_URL", JEV_DEFAULT_URL)


def jev_model() -> str:
    return _get("JEV_MODEL", JEV_DEFAULT_MODEL)


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

# ------------------------------------------------------------------ retrieval (D-006)
MAX_DISTANCE_KM = 10.0
RRF_K = 60
RERANK_TOP_N = 10
TOP_K = 3

# ------------------------------------------------------------------ confidence gating
# high -> act on the rule; medium -> escalate one level; low -> ask the follow-up (D-003).
CONFIDENCE_ACTIONS = {"high": "act", "medium": "escalate", "low": "ask"}


def confidence_action(confidence: str) -> str:
    """Unknown confidence is treated as low: ask rather than guess."""
    return CONFIDENCE_ACTIONS.get(confidence, "ask")
