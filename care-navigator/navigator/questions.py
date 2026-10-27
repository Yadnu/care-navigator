"""Question bank access: the only source of questions the system asks (D-041).

classify(): map a direct answer to an option value.
extract(): fill slots from free text the person already wrote (negation-aware).
"""
from __future__ import annotations

import json
from functools import lru_cache
from typing import Optional

from navigator.data import DATA_DIR
from navigator.redflags import TextView


@lru_cache(maxsize=1)
def load_bank() -> dict[str, dict]:
    entries = json.loads((DATA_DIR / "question_bank.json").read_text(encoding="utf-8"))
    return {e["slot"]: e for e in entries}


def _first_option(slot: str, text: str, anchored: bool) -> Optional[str]:
    view = TextView(text)
    for option in load_bank()[slot]["options"]:
        for pattern in option["match"]:
            if pattern.startswith("^") and not anchored:
                continue
            if view.find(pattern):
                return option["value"]
    return None


def classify(slot: str, answer: str) -> Optional[str]:
    """The option a direct answer picks: the quick-reply label itself, or the first option whose
    patterns match (options are listed so the more specific one comes first). None if unclear."""
    entry = load_bank()[slot]
    for option in entry["options"]:
        if answer.strip().lower() == option["label"].lower():
            return option["value"]
    return _first_option(slot, answer, anchored=True)


def extract(text: str, slots: Optional[list[str]] = None) -> dict[str, str]:
    """Slot values stated anywhere in free text (unanchored patterns only)."""
    found = {}
    for slot in slots or list(load_bank()):
        value = _first_option(slot, text, anchored=False)
        if value is not None:
            found[slot] = value
    return found


def is_danger(slot: str, value: Optional[str]) -> bool:
    return value is not None and value in load_bank()[slot]["danger_values"]


def routine_answer(slot: str) -> str:
    """The no-danger answer the eval runner gives (the routine option's label)."""
    entry = load_bank()[slot]
    for option in entry["options"]:
        if option["value"] == entry["routine_value"]:
            return option["label"]
    return "I'm not sure"


def quick_replies(slot: str) -> list[str]:
    return [o["label"] for o in load_bank()[slot]["options"]]
