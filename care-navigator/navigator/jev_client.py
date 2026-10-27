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
# TypeSafe Jev API, POST /v1/systemone (D-023): {model, state, questions{name: question}}.
# Answers come back keyed by question name: noul -> {noul}, choice -> {choice, confidence,
# probabilities}, score -> {score (zero-based expected level), confidence, legend, probabilities}.
CATEGORY_CRITERIA = {
    "respiratory": "cough, cold, runny or stuffy nose, congestion",
    "ent": "ear, nose, throat or sinus problems",
    "gastrointestinal": "vomiting, diarrhea, stomach cramps, heartburn",
    "musculoskeletal": "sprains, strains, joint, back or muscle pain",
    "skin": "rash, hives, itching, acne",
    "eye": "red, itchy, crusty or sore eyes",
    "urinary": "burning or pain when urinating",
    "wound": "cuts, bites, burns, splinters, blisters",
    "dental": "tooth or gum pain",
    "mental_health": "stress, anxiety, trouble sleeping, low mood",
    "chronic": "refills, blood pressure, check-ups for ongoing conditions",
    "allergy": "sneezing, seasonal allergy symptoms",
    "fever": "fever, flu-like symptoms, body aches, chills",
    "neuro": "headache or migraine",
    "general": "none of the above, or not about a symptom",
}
URGENCY_LEVELS = [
    "can wait for a routine visit",
    "should be seen within a few days",
    "should be seen within a day",
    "should be seen within a few hours",
    "needs care right away",
]
RELEVANCE_LEVELS = ["not relevant", "somewhat relevant", "highly relevant"]
MAX_CHOICES = 255
MAX_SCORE_LEVELS = 10


def _check_question(name: str, q: dict) -> None:
    kind, criteria = q.get("type"), q.get("criteria")
    if kind == "noul":
        return
    if kind == "choice":
        if not isinstance(criteria, dict) or not 1 <= len(criteria) <= MAX_CHOICES:
            raise ValueError(f"choice question {name!r} needs 1-{MAX_CHOICES} named options")
        return
    if kind == "score":
        if not isinstance(criteria, list) or not 1 <= len(criteria) <= MAX_SCORE_LEVELS:
            raise ValueError(f"score question {name!r} needs 1-{MAX_SCORE_LEVELS} ordered levels")
        return
    raise ValueError(f"unknown Jev question type for {name!r}: {kind!r}")


def build_jev_request(model: str, state: str | dict | list, questions: dict[str, dict]) -> dict:
    """Build the request body for POST /v1/systemone, validating question shapes locally."""
    if not questions:
        raise ValueError("Jev needs at least one question")
    for name, q in questions.items():
        _check_question(name, q)
    return {"model": model, "state": state, "questions": questions}


def parse_jev_response(payload: Any) -> dict[str, dict]:
    """Return the answers map (question name -> answer)."""
    if not isinstance(payload, dict) or not isinstance(payload.get("answers"), dict):
        raise JevError("unexpected Jev response shape")
    return payload["answers"]


def _noul_confidence(p: float) -> float:
    """noul answers carry no confidence; distance from 0.5 stands in for it (D-023)."""
    return abs(2 * p - 1)


class HttpJev(JevClient):
    def __init__(self, api_key: str, base_url: str | None = None, model: str | None = None,
                 session: requests.Session | None = None):
        self.api_key = api_key
        self.base_url = base_url or config.jev_base_url()
        self.model = model or config.jev_model()
        self.session = session or requests.Session()

    def _ask(self, state: str | dict, questions: dict[str, dict]) -> dict[str, dict]:
        body = build_jev_request(self.model, state, questions)
        try:
            resp = self.session.post(self.base_url, json=body, timeout=config.JEV_TIMEOUT_S,
                                     headers={"Authorization": f"Bearer {self.api_key}"})
        except requests.RequestException as e:
            raise JevError(f"Jev request failed: {e}") from e
        if resp.status_code != 200:
            raise JevError(f"Jev returned HTTP {resp.status_code}")
        try:
            answers = parse_jev_response(resp.json())
        except ValueError as e:
            raise JevError("Jev returned invalid JSON") from e
        missing = set(questions) - set(answers)
        if missing:
            raise JevError(f"Jev answer missing for {sorted(missing)}")
        return answers

    def _noul(self, name: str, instructions: str, text: str) -> float:
        answer = self._ask(text, {name: {"type": "noul", "instructions": instructions}})[name]
        return float(answer["noul"])

    def is_emergency(self, text: str) -> tuple[float, float]:
        p = self._noul("emergency", "Does this describe a possible medical emergency?", text)
        return p, _noul_confidence(p)

    def classify_category(self, text: str) -> tuple[str, dict[str, float], float]:
        answer = self._ask(text, {"category": {
            "type": "choice", "instructions": "Which symptom category fits best?",
            "criteria": CATEGORY_CRITERIA}})["category"]
        probs = {c: float(answer.get("probabilities", {}).get(c, 0.0)) for c in CATEGORIES}
        label = answer.get("choice")
        if label not in CATEGORIES:
            label = "general"
            probs = {c: (1.0 if c == "general" else 0.0) for c in CATEGORIES}
        return label, probs, float(answer["confidence"])

    def urgency_score(self, text: str) -> tuple[int, float]:
        answer = self._ask(text, {"urgency": {
            "type": "score", "instructions": "How soon does this person need care?",
            "criteria": URGENCY_LEVELS}})["urgency"]
        level = int(float(answer["score"]) + 1 + 0.5)  # zero-based expected level -> 1..5, half up
        return max(1, min(5, level)), float(answer["confidence"])

    def is_too_vague(self, text: str) -> tuple[float, float]:
        p = self._noul("vague", "Is this too vague to tell what the symptom is?", text)
        return p, _noul_confidence(p)

    def rerank(self, query: str, docs: list[str]) -> list[float]:
        if not docs:
            return []
        questions = {f"doc{i}": {
            "type": "score", "criteria": RELEVANCE_LEVELS,
            "instructions": f"How well does this practitioner match the symptoms in the state? {doc}"}
            for i, doc in enumerate(docs)}
        answers = self._ask({"symptoms": query}, questions)
        top = len(RELEVANCE_LEVELS) - 1
        return [float(answers[f"doc{i}"]["score"]) / top for i in range(len(docs))]

    def mentions_diagnosis_or_medication(self, text: str) -> float:
        # Two narrow questions; asking about "treatment" flagged ordinary care advice (D-036).
        answers = self._ask(text, {
            "diagnosis": {"type": "noul", "instructions":
                          "Does this text tell the reader they have a specific named disease, infection or diagnosis?"},
            "medication": {"type": "noul", "instructions":
                           "Does this text name or recommend a medication, drug, dose or supplement?"},
        })
        return max(float(answers["diagnosis"]["noul"]), float(answers["medication"]["noul"]))


def get_jev() -> JevClient:
    if config.jev_enabled():
        return HttpJev(api_key=os.environ["JEV_API_KEY"].strip())
    return OfflineJev()
