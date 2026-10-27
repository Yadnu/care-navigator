"""Env switches, model ids, thresholds and limits.

Offline is the default (D-008): a provider switches on only when its API key is set.
Settings are read at call time so tests can toggle them with monkeypatch.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

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


def load_env_file(path: Optional[Path] = None) -> list[str]:
    """Load KEY=value lines into os.environ (D-024).

    Called by entry points (cli, app, eval), never on import, so tests stay offline.
    Real environment variables win, blank values are skipped, and a missing file is fine.
    CARE_NAVIGATOR_SKIP_DOTENV=1 (set by the test suite) skips the project's .env file.
    Returns the keys it set.
    """
    path = ENV_FILE if path is None else path
    if path == ENV_FILE and _has("CARE_NAVIGATOR_SKIP_DOTENV"):
        return []
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
# Red-flag typo matching (D-041): a phrase word and a text word count as the same when they are
# equal, or both have at least FUZZY_MIN_TOKEN_LEN letters, start with the same letter and have a
# Jaro-Winkler similarity >= FUZZY_WORD_THRESHOLD ("pian" -> "pain"). Short words must match exactly.
FUZZY_WORD_THRESHOLD = 0.90
FUZZY_MIN_TOKEN_LEN = 4

# Jev (D-019, D-041). Alone, Jev triggers EMERGENCY only at >= 0.8 with confidence >= 0.7;
# from 0.5 it is a Tier 2 signal that asks a safety question.
JEV_EMERGENCY_THRESHOLD = 0.8
JEV_HIGH_CONFIDENCE = 0.7
JEV_SAFETY_THRESHOLD = 0.5
JEV_VAGUE_THRESHOLD = 0.5
GUARD_THRESHOLD = 0.5

# Conversation (D-041): at most this many questions (safety + detail) per conversation.
MAX_QUESTIONS = 3

# ------------------------------------------------------------------ pipeline
MAX_TEXT_CHARS = 2000            # longer descriptions are rejected with a clear message
TRACE_DIR = Path(__file__).resolve().parents[1] / "traces"
HIGH_DEDUCTIBLE_USD = 3000       # mention the deductible at or above this

# ------------------------------------------------------------------ retrieval (D-006)
MAX_DISTANCE_KM = 3.0   # "nearby" = the person's own neighbourhood; zips are 4-10 km apart (D-031)
RRF_K = 60
RERANK_TOP_N = 10
TOP_K = 3

# ------------------------------------------------------------------ confidence gating
# high -> act on the rule; medium -> escalate one level; low -> ask the follow-up (D-025, D-041).
CONFIDENCE_ACTIONS = {"high": "act", "medium": "escalate", "low": "ask"}


def confidence_action(confidence: str) -> str:
    """Unknown confidence is treated as low: ask rather than guess."""
    return CONFIDENCE_ACTIONS.get(confidence, "ask")
