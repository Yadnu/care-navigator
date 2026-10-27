"""Jev classifier: interface, transparent offline heuristics, and an HTTP client (D-004, D-008).

Jev only classifies. Its answers feed the rules; it never picks the care level (D-001).
"""
from __future__ import annotations

import os
import re
from abc import ABC, abstractmethod
from typing import Any

import requests

from navigator import config, lexicon
from navigator.redflags import normalize

CATEGORIES = [*lexicon.SYMPTOM_TERMS, "general"]


class JevError(RuntimeError):
    """Jev unreachable, timed out, or returned something we can't read."""


class JevClient(ABC):
    @abstractmethod
    def is_emergency(self, text: str) -> tuple[float, float]: ...

    @abstractmethod
    def classify_category(self, text: str) -> tuple[str, dict[str, float], float]: ...

    @abstractmethod
    def urgency_score(self, text: str) -> tuple[int, float]: ...

    @abstractmethod
    def is_too_vague(self, text: str) -> tuple[float, float]: ...

    @abstractmethod
    def rerank(self, query: str, docs: list[str]) -> list[float]: ...

    @abstractmethod
    def mentions_diagnosis_or_medication(self, text: str) -> float: ...


# ------------------------------------------------------------------ offline heuristics
# Each combo is a list of patterns that must all match: indirect emergency wording
# the keyword screen leaves to the classifier (D-015).
EMERGENCY_COMBOS: list[list[str]] = [
    [r"chest", r"elephant|sitting on|squeez\w*|heavy|weight|pressure"],
    [r"breath\w*", r"struggl\w*|hard to|cant|catch|sitting still|at rest|gasp\w*"],
    [r"cant see|lost (my )?vision|vision loss|blind\w*", r"sudden\w*"],
    [r"confus\w*", r"cant lift|weak\w*|numb\w*|droop\w*|slurr\w*"],
    [r"cant (lift|move) (my |his |her |their )?(right |left )?(arm|leg)"],
    [r"hard to swallow|cant swallow|trouble swallowing", r"swell\w*|lips|tongue|throat"],
    [r"lips|tongue", r"swell\w*"],
    [r"lower right|right lower", r"belly|abdomen|stomach|side", r"fever|worse|worsening"],
    [r"car crash|car accident|crash|hit by a car|fell from", r"neck|back|head|tingl\w*|numb\w*"],
    [r"cant keep|havent peed|no urine|not peeing", r"dizz\w*|vomit\w*|faint\w*"],
    [r"severe|worst", r"stomach|belly|abdomen", r"hard|rigid|cant stand|cant move"],
    [r"stiff neck", r"fever"],
]
URGENCY_UP = [r"\b10[1-9]\b|high fever", r"vomit\w*|diarrh?ea", r"swollen|swelling", r"bleed\w*|edges open",
              r"\bcut\b|\bbite\b|puncture|\bburn\b", r"twisted|sprain\w*|\bfall\b", r"worse"]
URGENCY_DOWN = [r"\bmild\b", r"for (months|weeks)|every (spring|year)|most nights",
                r"feel(ing)? fine", r"\bno (swelling|fever|rash)\b", r"refill|check ?up"]
GUARD_PATTERNS = [
    r"\byou (probably |likely |may |might )?have\b",
    r"diagnos\w*",
    r"sounds like (a |an )?(case of )?\w+",
    r"\b(ibuprofen|acetaminophen|paracetamol|aspirin|naproxen|antibiotics?|amoxicillin|antihistamines?"
    r"|tylenol|advil|motrin|benadryl|steroids?|prescri\w*|dose|dosage|medication|medicine)\b",
    r"\b\d+ ?mg\b",
    r"\b(strep|appendicitis|pneumonia|concussion|sinusitis|conjunctivitis|gastroenteritis|uti)\b",
]
STOPWORDS = {"and", "or", "the", "a", "an", "of", "for", "my", "i", "with", "in", "on", "to", "since", "is"}


def _any(patterns: list[str], text: str) -> int:
    return sum(1 for p in patterns if re.search(p, text))


def _stems(text: str) -> set[str]:
    return {t[:5] for t in normalize(text).split() if t not in STOPWORDS}


class OfflineJev(JevClient):
    """Keyword and heuristic stand-in. Confidence is kept modest because it is a heuristic."""

    CONFIDENCE = 0.6

    def is_emergency(self, text: str) -> tuple[float, float]:
        norm = normalize(text or "")
        hit = any(all(re.search(p, norm) for p in combo) for combo in EMERGENCY_COMBOS)
        return (0.85 if hit else 0.05), self.CONFIDENCE

    def classify_category(self, text: str) -> tuple[str, dict[str, float], float]:
        norm = normalize(text or "")
        scores = {c: 0.0 for c in CATEGORIES}
        for _, _, category in lexicon.symptom_matches(norm):
            scores[category] += 2.0
        for _, _, category in lexicon.body_areas(norm):
            scores[category] += 1.0
        if not any(scores.values()):
            scores["general"] = 1.0
        smoothed = {c: s + 0.1 for c, s in scores.items()}
        total = sum(smoothed.values())
        probs = {c: s / total for c, s in smoothed.items()}
        label = max(CATEGORIES, key=lambda c: probs[c])  # ties go to the earlier category
        return label, probs, probs[label]

    def urgency_score(self, text: str) -> tuple[int, float]:
        norm = normalize(text or "")
        score = 2 + _any(URGENCY_UP, norm) - _any(URGENCY_DOWN, norm)
        return max(1, min(5, score)), self.CONFIDENCE

    def is_too_vague(self, text: str) -> tuple[float, float]:
        norm = normalize(text or "")
        return (0.1 if lexicon.is_specific(norm) else 0.9), 0.7

    def rerank(self, query: str, docs: list[str]) -> list[float]:
        q = _stems(query)
        return [len(q & _stems(d)) / len(q) if q else 0.0 for d in docs]

    def mentions_diagnosis_or_medication(self, text: str) -> float:
        return 0.9 if _any(GUARD_PATTERNS, (text or "").lower()) else 0.05


# ------------------------------------------------------------------ HTTP client
QUESTION_TYPES = {"yes_no", "choice", "score"}


def build_jev_request(state: str | dict, questions: list[dict]) -> dict:
    """Build the Jev request body.

    TODO: verify against Jev docs. Shape taken from public write-ups: a "state" (text or
    JSON) plus questions of type yes/no, Choice or Score; answers carry probabilities
    and a confidence. Field names here are our assumption.
    """
    for q in questions:
        if q.get("type") not in QUESTION_TYPES:
            raise ValueError(f"unknown Jev question type: {q.get('type')!r}")
    return {"state": state, "questions": questions}


def parse_jev_response(payload: Any) -> dict[str, dict]:
    """Map question id -> answer. TODO: verify against Jev docs."""
    if not isinstance(payload, dict) or not isinstance(payload.get("answers"), list):
        raise JevError("unexpected Jev response shape")
    try:
        return {a["id"]: a for a in payload["answers"]}
    except (KeyError, TypeError) as e:
        raise JevError("Jev answer without id") from e


class HttpJev(JevClient):
    def __init__(self, api_key: str, base_url: str = config.JEV_BASE_URL,
                 session: requests.Session | None = None):
        self.api_key = api_key
        self.base_url = base_url
        self.session = session or requests.Session()

    def _ask(self, state: str | dict, questions: list[dict]) -> dict[str, dict]:
        body = build_jev_request(state, questions)
        try:
            resp = self.session.post(self.base_url, json=body, timeout=config.JEV_TIMEOUT_S,
                                     headers={"Authorization": f"Bearer {self.api_key}"})
        except requests.RequestException as e:
            raise JevError(f"Jev request failed: {e}") from e
        if resp.status_code != 200:
            raise JevError(f"Jev returned HTTP {resp.status_code}")
        try:
            return parse_jev_response(resp.json())
        except ValueError as e:
            raise JevError("Jev returned invalid JSON") from e

    def _yes_no(self, qid: str, question: str, text: str) -> tuple[float, float]:
        a = self._ask(text, [{"id": qid, "type": "yes_no", "text": question}])[qid]
        return float(a["probabilities"]["yes"]), float(a["confidence"])

    def is_emergency(self, text: str) -> tuple[float, float]:
        return self._yes_no("emergency", "Does this describe a possible medical emergency?", text)

    def classify_category(self, text: str) -> tuple[str, dict[str, float], float]:
        a = self._ask(text, [{"id": "category", "type": "choice", "text": "Which symptom category fits best?",
                              "options": CATEGORIES}])["category"]
        probs = {c: float(a["probabilities"].get(c, 0.0)) for c in CATEGORIES}
        return max(CATEGORIES, key=lambda c: probs[c]), probs, float(a["confidence"])

    def urgency_score(self, text: str) -> tuple[int, float]:
        a = self._ask(text, [{"id": "urgency", "type": "score", "text": "How urgent is this, 1 to 5?",
                              "min": 1, "max": 5}])["urgency"]
        return max(1, min(5, round(float(a["score"])))), float(a["confidence"])

    def is_too_vague(self, text: str) -> tuple[float, float]:
        return self._yes_no("vague", "Is this too vague to tell what the symptom is?", text)

    def rerank(self, query: str, docs: list[str]) -> list[float]:
        if not docs:
            return []
        questions = [{"id": f"doc{i}", "type": "score", "min": 0, "max": 1,
                      "text": f"How well does this practitioner match the symptoms? {doc}"}
                     for i, doc in enumerate(docs)]
        answers = self._ask({"query": query}, questions)
        return [float(answers[f"doc{i}"]["score"]) for i in range(len(docs))]

    def mentions_diagnosis_or_medication(self, text: str) -> float:
        return self._yes_no("guard", "Does this text name a diagnosis or a medication?", text)[0]


def get_jev() -> JevClient:
    if config.jev_enabled():
        return HttpJev(api_key=os.environ["JEV_API_KEY"])
    return OfflineJev()
