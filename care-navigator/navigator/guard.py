"""Output guard for explanations (D-007).

Blocks text that recommends a different care level, names a diagnosis or medication,
names a practitioner who wasn't retrieved, or lacks the disclaimer. The pipeline then
falls back to the template explanation.
"""
from __future__ import annotations

import re

from pydantic import BaseModel

from navigator import config
from navigator.data import load_practitioners
from navigator.explainer import DISCLAIMER, split_sentences
from navigator.jev_client import JevClient, JevError, OfflineJev
from navigator.models import CareDecision, CareLevel, Option

LEVEL_PATTERNS = {
    CareLevel.ER: re.compile(r"\bER\b|emergency room|emergency department", re.IGNORECASE),
    CareLevel.URGENT_CARE: re.compile(r"urgent care", re.IGNORECASE),
    CareLevel.PRIMARY_CARE: re.compile(r"primary care", re.IGNORECASE),
    CareLevel.TELEHEALTH: re.compile(r"telehealth|virtual visit", re.IGNORECASE),
    CareLevel.SELF_CARE: re.compile(r"self[- ]care", re.IGNORECASE),
}
# Another level may be named only to say it is closed / unavailable, or as conditional escalation.
ALLOWED_CONTEXT = re.compile(r"\bclosed\b|\bno in-network\b|\bisn't open\b|\bnot open\b", re.IGNORECASE)
DOCTOR = re.compile(r"\bDr\.\s+[A-Z][\w'-]+(?:\s+[A-Z][\w'-]+)?")
_offline = OfflineJev()


class GuardResult(BaseModel):
    ok: bool
    reasons: list[str] = []
    used: str = "OfflineJev"


def check(text: str, decision: CareDecision, options: list[Option], jev: JevClient,
          alternatives: list[Option] = ()) -> GuardResult:
    reasons: list[str] = []
    retrieved = {name for o in [*options, *alternatives]
                 for name in (o.match.practitioner.name, o.match.practitioner.facility_name)}
    directory = {name for p in load_practitioners() for name in (p.name, p.facility_name)}

    if not text.strip().endswith(DISCLAIMER):
        reasons.append("missing disclaimer")

    # Names: anything from the directory, or any "Dr. X", must be a retrieved record.
    for name in directory - retrieved:
        if name in text:
            reasons.append(f"practitioner not retrieved: {name}")
    for doctor in DOCTOR.findall(text):
        if not any(doctor in r for r in retrieved):
            reasons.append(f"practitioner not retrieved: {doctor}")

    # Levels: the decision's level must be named; others only when closed or as "if ... ER / 911".
    scrubbed = text  # a neutral placeholder keeps sentences readable for the classifier
    for name in sorted(retrieved, key=len, reverse=True):
        scrubbed = scrubbed.replace(name, "the clinic")
    if not LEVEL_PATTERNS[decision.level].search(scrubbed):
        reasons.append(f"level not stated: {decision.level.value}")
    for sentence in split_sentences(scrubbed):
        for level, pattern in LEVEL_PATTERNS.items():
            if level is decision.level or not pattern.search(sentence):
                continue
            conditional_er = level is CareLevel.ER and re.search(r"\bif\b", sentence, re.IGNORECASE)
            shown_alternative = level is CareLevel.TELEHEALTH and bool(alternatives)
            if not (conditional_er or shown_alternative or ALLOWED_CONTEXT.search(sentence)):
                reasons.append(f"level mismatch: mentions {level.value}, decision is {decision.level.value}")

    # Record names are trusted text ("Downtown Internal Medicine"), so check the rest only.
    used = type(jev).__name__
    try:
        flagged = jev.mentions_diagnosis_or_medication(scrubbed)
    except JevError:
        flagged, used = _offline.mentions_diagnosis_or_medication(scrubbed), "OfflineJev (fallback)"
    if flagged >= config.GUARD_THRESHOLD:
        reasons.append("mentions a diagnosis or medication")

    return GuardResult(ok=not reasons, reasons=reasons, used=used)
