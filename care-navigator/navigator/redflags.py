"""Keyword + fuzzy red-flag screen (D-002, D-014).

First of three independent emergency checks. Runs on redacted raw text, and again
on parsed SymptomReport fields. Any hit routes to EMERGENCY.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel
from rapidfuzz import fuzz

from navigator import config
from navigator.models import SymptomReport

RULES_PATH = Path(__file__).with_name("red_flags.yaml")

# Eval labels a keyword screen must catch; "parsed_or_jev" needs the parser or Jev.
KEYWORD_DETECTABLE = {"keyword", "fuzzy_keyword"}


class RedFlagHit(BaseModel):
    category: str
    phrase: str
    method: str  # exact | fuzzy | pattern
    score: float


class RedFlagResult(BaseModel):
    hits: list[RedFlagHit] = []
    resources: list[str] = []
    message: str = ""

    @property
    def is_emergency(self) -> bool:
        return bool(self.hits)

    @property
    def categories(self) -> set[str]:
        return {h.category for h in self.hits}


@lru_cache(maxsize=1)
def load_rules() -> dict:
    return yaml.safe_load(RULES_PATH.read_text(encoding="utf-8"))


def normalize(text: str) -> str:
    text = text.lower().replace("’", "'").replace("'", "")
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text).split())


def _fuzzy_score(phrase: str, tokens: list[str]) -> float:
    """Best ratio of the phrase against any same-length token window, or 0."""
    want = phrase.split()
    best = 0.0
    for i in range(len(tokens) - len(want) + 1):
        window = tokens[i:i + len(want)]
        if any(w != t and (len(w) < config.FUZZY_MIN_TOKEN_LEN or len(t) < config.FUZZY_MIN_TOKEN_LEN)
               for w, t in zip(want, window)):
            continue
        best = max(best, fuzz.ratio(phrase, " ".join(window)))
    return best


def _match_phrases(category: str, phrases: list[str], norm: str, tokens: list[str]) -> RedFlagHit | None:
    """Exact match on any phrase first; only then the best fuzzy match."""
    phrases = [normalize(p) for p in phrases]
    for phrase in phrases:
        if re.search(rf"\b{re.escape(phrase)}\b", norm):
            return RedFlagHit(category=category, phrase=phrase, method="exact", score=100.0)
    score, phrase = max(((_fuzzy_score(p, tokens), p) for p in phrases), default=(0.0, ""))
    if score >= config.FUZZY_THRESHOLD:
        return RedFlagHit(category=category, phrase=phrase, method="fuzzy", score=score)
    return None


def screen_text(text: str) -> RedFlagResult:
    rules = load_rules()
    norm = normalize(text or "")
    tokens = norm.split()
    hits: list[RedFlagHit] = []
    for category, spec in rules["categories"].items():
        hit = _match_phrases(category, spec.get("phrases", []), norm, tokens)
        if hit:
            hits.append(hit)
        for group in spec.get("patterns", []):
            if all(re.search(p, norm) for p in group):
                hits.append(RedFlagHit(category=category, phrase=" + ".join(group), method="pattern", score=100.0))
                break

    resources: list[str] = []
    for category in dict.fromkeys(h.category for h in hits):
        for r in rules["categories"][category]["resources"]:
            if r not in resources:
                resources.append(r)
    resources.sort(key=lambda r: r != "988")  # crisis line first when present
    message = " ".join(rules["messages"][r] for r in resources[:1])
    return RedFlagResult(hits=hits, resources=resources, message=message)


def screen_report(report: SymptomReport) -> RedFlagResult:
    """Rules again on parsed fields: parser-reported red flags plus symptom text."""
    parts = [report.main_symptom or "", report.body_area or "", *report.red_flags]
    result = screen_text(" . ".join(parts))
    if report.red_flags and not result.hits:
        hit = RedFlagHit(category="parsed", phrase=report.red_flags[0], method="parsed", score=100.0)
        rules = load_rules()
        return RedFlagResult(hits=[hit], resources=["911"], message=rules["messages"]["911"])
    return result
