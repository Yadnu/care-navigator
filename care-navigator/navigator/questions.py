"""Question bank access, rebuilt from the symptom guide (D-041, D-050).

One entry per guide `ask_about` topic and per `possible_cause_questions` item. The offline
interviewer asks the bank text as-is; Claude may word a question differently, but only about a
bank topic (the question guard checks it).

classify(): map a direct answer to an option value.
extract(): fill topics from free text the person already wrote (negation-aware).
danger_sign(): the guide danger sign an answer confirms; the action comes from the guide (D-048).
"""
from __future__ import annotations

import json
from functools import lru_cache
from typing import Optional

from navigator.data import DATA_DIR
from navigator.guide import sign_by_text
from navigator.redflags import TextView


@lru_cache(maxsize=1)
def load_bank() -> dict[str, dict]:
    entries = json.loads((DATA_DIR / "question_bank.json").read_text(encoding="utf-8"))
    return {e["topic"]: e for e in entries}


def _first_option(topic: str, text: str, anchored: bool) -> Optional[str]:
    view = TextView(text)
    for option in load_bank()[topic]["options"]:
        for pattern in option["match"]:
            if pattern.startswith("^") and not anchored:
                continue
            if view.find(pattern):
                return option["value"]
    return None


def classify(topic: str, answer: str) -> Optional[str]:
    """The option a direct answer picks: the quick-reply label itself, or the first option whose
    patterns match (options are listed so the more specific one comes first). None if unclear."""
    entry = load_bank()[topic]
    for option in entry["options"]:
        if answer.strip().lower() == option["label"].lower():
            return option["value"]
    return _first_option(topic, answer, anchored=True)


def extract(text: str, topics: Optional[list[str]] = None) -> dict[str, str]:
    """Topic values stated anywhere in free text (unanchored patterns only). Possible-cause
    questions are never filled from free text: they are only answered when asked."""
    bank = load_bank()
    found = {}
    for topic in topics or list(bank):
        if bank[topic]["kind"] == "cause" or not bank[topic]["options"]:
            continue
        value = _first_option(topic, text, anchored=False)
        if value is not None:
            found[topic] = value
    return found


def danger_sign(topic: str, value: Optional[str]) -> Optional[dict]:
    """The guide danger sign (with its cluster, action and why) this answer confirms, if any."""
    if value is None or topic not in load_bank():
        return None
    for link in load_bank()[topic]["danger"]:
        if value in link["values"]:
            return sign_by_text(link["cluster"], link["sign"])
    return None


def danger_action(topic: str) -> Optional[str]:
    """The most urgent action any danger answer to this topic leads to (CALL_911 before GO_TO_ER)."""
    actions = {sign_by_text(link["cluster"], link["sign"])["action"] for link in load_bank()[topic]["danger"]}
    return "CALL_911" if "CALL_911" in actions else "GO_TO_ER" if actions else None


def routine_answer(topic: str) -> str:
    """The no-danger answer the eval runner gives (the routine option's label)."""
    entry = load_bank()[topic]
    for option in entry["options"]:
        if option["value"] == entry["routine_value"]:
            return option["label"]
    return "I'm not sure"


def quick_replies(topic: str) -> list[str]:
    return list(load_bank()[topic]["quick_replies"])
