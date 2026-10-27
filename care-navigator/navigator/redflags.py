"""Three-tier red-flag screen (D-002, D-041).

Tier 1 (`screen_text`): unmistakable signs -> EMERGENCY immediately.
Tier 2 (`tier2_signals`): one weak signal -> ask a safety question first.
Tier 3: neither -> normal clarification and routing.
Runs on redacted text: the first message plus every answer, and again on parsed fields.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Optional

import yaml
from pydantic import BaseModel
from rapidfuzz.distance import JaroWinkler

from navigator import config
from navigator.models import SymptomReport

RULES_PATH = Path(__file__).with_name("red_flags.yaml")

# Eval labels a keyword screen must catch; "parsed_or_jev" needed the parser or Jev before D-041.
KEYWORD_DETECTABLE = {"keyword", "fuzzy_keyword"}
BREAK = "|"


class RedFlagHit(BaseModel):
    category: str
    phrase: str
    method: str  # exact | fuzzy | pattern
    score: float


class RedFlagResult(BaseModel):
    hits: list[RedFlagHit] = []
    resources: list[str] = []
    message: str = ""
    action: Optional[str] = None  # CALL_911 or GO_TO_ER; CALL_911 wins when both hit (D-048)

    @property
    def is_emergency(self) -> bool:
        return bool(self.hits)

    @property
    def categories(self) -> set[str]:
        return {h.category for h in self.hits}


class Signal(BaseModel):
    name: str
    slot: str           # the safety question to ask
    phrase: str


@lru_cache(maxsize=1)
def load_rules() -> dict:
    return yaml.safe_load(RULES_PATH.read_text(encoding="utf-8"))


def normalize(text: str) -> str:
    text = text.lower().replace("’", "'").replace("'", "")
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text).split())


class TextView:
    """Normalized text that remembers clause breaks, for negation-aware matching."""

    def __init__(self, text: str):
        rules = load_rules()
        s = (text or "").lower().replace("’", "'").replace("'", "")
        s = re.sub(r"[.,;:!?\n]+", f" {BREAK} ", s)
        tokens = [t for t in re.sub(r"[^a-z0-9|]+", " ", s).split()]
        breaks = set(rules["clause_breaks"])
        self.full = [BREAK if t in breaks else t for t in tokens]
        self.plain_tokens = [t for t in self.full if t != BREAK]
        self._to_full = [i for i, t in enumerate(self.full) if t != BREAK]
        self.plain = " ".join(self.plain_tokens)
        self._cues = set(rules["negation_cues"])

    def _token_at(self, char: int) -> int:
        return self.plain[:char].count(" ")

    def negated_at(self, token: int) -> bool:
        """True when a negation cue sits up to 3 words before `token` in the same clause."""
        i = self._to_full[token]
        for j in range(i - 1, max(-1, i - 4), -1):
            if self.full[j] == BREAK:
                return False
            if self.full[j] in self._cues:
                return True
        return False

    def find(self, pattern: str) -> Optional[re.Match]:
        """First match of `pattern` that is not negated."""
        for m in re.finditer(pattern, self.plain):
            if not self.negated_at(self._token_at(m.start())):
                return m
        return None


def _same_word(want: str, got: str) -> float:
    """1.0 for equal words, the Jaro-Winkler similarity for an allowed typo, else 0."""
    if want == got:
        return 1.0
    if min(len(want), len(got)) < config.FUZZY_MIN_TOKEN_LEN or want[0] != got[0]:
        return 0.0
    sim = JaroWinkler.normalized_similarity(want, got)
    return sim if sim >= config.FUZZY_WORD_THRESHOLD else 0.0


def _match_phrase(view: TextView, phrase: str) -> Optional[tuple[str, float]]:
    """Word-by-word phrase match (typos allowed per word). Returns (method, score)."""
    want = normalize(phrase).split()
    tokens = view.plain_tokens
    best: Optional[tuple[str, float]] = None
    for i in range(len(tokens) - len(want) + 1):
        scores = [_same_word(w, t) for w, t in zip(want, tokens[i:i + len(want)])]
        if not all(scores) or view.negated_at(i):
            continue
        score = min(scores) * 100
        method = "exact" if score == 100 else "fuzzy"
        if best is None or score > best[1]:
            best = (method, score)
    return best


def screen_text(text: str) -> RedFlagResult:
    """Tier 1: unmistakable signs only."""
    rules = load_rules()
    view = TextView(text)
    hits: list[RedFlagHit] = []
    for category, spec in rules["categories"].items():
        found = [(p, m) for p in spec.get("phrases", []) if (m := _match_phrase(view, p))]
        if found:
            phrase, (method, score) = max(found, key=lambda f: f[1][1])
            hits.append(RedFlagHit(category=category, phrase=normalize(phrase), method=method, score=score))
        for group in spec.get("patterns", []):
            if all(view.find(p) for p in group):
                hits.append(RedFlagHit(category=category, phrase=" + ".join(group), method="pattern", score=100.0))
                break

    resources: list[str] = []
    for category in dict.fromkeys(h.category for h in hits):
        for r in rules["categories"][category]["resources"]:
            if r not in resources:
                resources.append(r)
    resources.sort(key=lambda r: r != "988")  # crisis line first when present
    actions = {rules["categories"][h.category]["action"] for h in hits}
    action = None if not hits else "CALL_911" if "CALL_911" in actions else "GO_TO_ER"
    return RedFlagResult(hits=hits, resources=resources, action=action,
                         message=emergency_message(action, resources) if hits else "")


def emergency_message(action: str, resources: list[str]) -> str:
    """988 first for crisis wording; otherwise the message for the action."""
    messages = load_rules()["messages"]
    if resources and resources[0] == "988":
        return messages["988"]
    return messages["911"] if action == "CALL_911" else messages["GO_TO_ER"]


def has_injury_context(text: str) -> bool:
    view = TextView(text)
    return any(view.find(p) for p in load_rules()["injury_context"])


def has_child_context(text: str) -> bool:
    view = TextView(text)
    return any(view.find(p) for p in load_rules()["child_context"])


def tier2_signals(text: str, age_group: str = "adult", extra: Iterable[Signal] = ()) -> list[Signal]:
    """Tier 2 signals in order; signals marked suppressed_by_injury drop out under injury context."""
    view = TextView(text)
    injury = has_injury_context(text)
    child = age_group == "child" or has_child_context(text)
    signals: list[Signal] = []
    for name, spec in load_rules()["tier2"].items():
        if spec.get("needs_child") and not child:
            continue
        if spec.get("suppressed_by_injury") and injury:
            continue
        for pattern in spec["patterns"]:
            m = view.find(pattern)
            if m:
                signals.append(Signal(name=name, slot=spec["safety_slot"], phrase=m.group()))
                break
    signals += [s for s in extra if not (injury and s.name in ("jev", "parser"))]
    return signals


def screen_report(report: SymptomReport) -> RedFlagResult:
    """Tier 1 again on parsed fields. Parser flags that match no rule are not emergencies (D-041)."""
    return screen_text(" . ".join([report.main_symptom or "", report.body_area or "", *report.red_flags]))


def unmatched_flags(report: SymptomReport) -> list[str]:
    """Parser-reported red flags that no Tier 1 rule recognises; the pipeline treats them as Tier 2."""
    return [f for f in report.red_flags if not screen_text(f).is_emergency]
