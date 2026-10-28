"""Output guards (D-007, D-053).

check(): blocks an explanation that recommends a different care level, names a diagnosis or
medication, names a cause that is not a hedged possible cause of the matched clusters, says
"you have" before a cause, names a practitioner who wasn't retrieved, shows a price or phone
number that is not in the data, or lacks the disclaimer. The pipeline then uses the template.
check_final(): the code-built final-answer sections (evidence quotes, causes, hedging).
"""
from __future__ import annotations

import json
import re
from functools import lru_cache

from pydantic import BaseModel

from navigator import config
from navigator.care_engine import load_rules as load_care_rules
from navigator.data import DATA_DIR, load_plans, load_practitioners
from navigator.explainer import DISCLAIMER, split_sentences
from navigator.jev_client import JevClient, JevError, OfflineJev
from navigator.interviewer import CAUSE_NAMES
from navigator.models import CareDecision, CareLevel, FinalAnswer, Option

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
HEDGES = re.compile(r"could be|one common possibility|possib\w*|might|may be|a clinician needs to confirm", re.IGNORECASE)
MONEY = re.compile(r"\$\s?(\d[\d,]*)")
PHONE = re.compile(r"\b(?:1-)?(?:\d{3}-)?\d{3}-\d{4}\b")
_offline = OfflineJev()


def _numbers(obj) -> set[int]:
    if isinstance(obj, bool):
        return set()
    if isinstance(obj, (int, float)):
        return {int(obj)}
    if isinstance(obj, dict):
        return _numbers(list(obj.values()))
    if isinstance(obj, (list, tuple)):
        return set().union(*(_numbers(v) for v in obj)) if obj else set()
    return set()


@lru_cache(maxsize=1)
def known_prices() -> frozenset[int]:
    """Every dollar amount in plans.json and cost_ranges.json."""
    ranges = json.loads((DATA_DIR / "cost_ranges.json").read_text(encoding="utf-8"))
    return frozenset(_numbers(list(load_plans())) | _numbers(ranges))


@lru_cache(maxsize=1)
def known_phones() -> frozenset[str]:
    phones = {p.phone for p in load_practitioners()}
    for plan in load_plans():
        phones |= {plan.get("nurse_line") or "", plan.get("member_services") or ""}
    return frozenset(phones - {""})


def _core(cause: str) -> list[str]:
    parts = [re.sub(r"^(an?|the)\s+", "", p.strip().lower()) for p in re.split(r"[()]| or ", cause)]
    return [p for p in parts if len(p) >= 4]


def cause_reasons(text: str, allowed_causes: list[str], trusted: str = "") -> list[str]:
    """Causes named in the text: only allowed ones, each hedged, never after "you have".
    `trusted` is the matched care rule's own `reason` text (care_rules.yaml, versioned,
    never model-generated): a cause word that comes from it is not a model claim, so it
    is exempt, the same way a retrieved practitioner's name is exempt."""
    reasons = []
    allowed = {w for c in allowed_causes for w in _core(c)}
    low_trusted = trusted.lower()
    for sentence in split_sentences(text):
        low = sentence.lower()
        for n in CAUSE_NAMES:
            if not re.search(r"\b" + re.escape(n) + r"\b", low):
                continue
            if trusted and re.search(r"\b" + re.escape(n) + r"\b", low_trusted):
                continue
            if n not in allowed:
                reasons.append(f"cause not in the matched cluster: {n}")
            elif re.search(r"\byou (probably |likely |may |might )?have\b[^.]*\b" + re.escape(n), low):
                reasons.append(f"'you have' before a cause: {n}")
            elif not HEDGES.search(sentence):
                reasons.append(f"cause without hedging: {n}")
    return list(dict.fromkeys(reasons))


def fact_reasons(text: str) -> list[str]:
    """Prices and phone numbers must exist in the data."""
    reasons = []
    for amount in MONEY.findall(text):
        if int(amount.replace(",", "")) not in known_prices():
            reasons.append(f"price not in the data: ${amount}")
    for phone in PHONE.findall(text):
        if not any(phone in k for k in known_phones()):
            reasons.append(f"phone not in the data: {phone}")
    return reasons


def scrub_causes(text: str, allowed_causes: list[str]) -> str:
    for n in sorted({w for c in allowed_causes for w in _core(c)}, key=len, reverse=True):
        text = re.sub(r"\b" + re.escape(n) + r"\b", "a common cause", text, flags=re.IGNORECASE)
    return text


class GuardResult(BaseModel):
    ok: bool
    reasons: list[str] = []
    used: str = "OfflineJev"


def _rule_reason(decision: CareDecision) -> str:
    rule = next((r for r in load_care_rules()["rules"] if r["id"] == decision.rule_id), None)
    return rule.get("reason", "") if rule else ""


def check(text: str, decision: CareDecision, options: list[Option], jev: JevClient,
          alternatives: list[Option] = (), allowed_causes: list[str] = ()) -> GuardResult:
    reasons: list[str] = cause_reasons(text, list(allowed_causes), trusted=_rule_reason(decision)) + fact_reasons(text)
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

    # Record names and allowed, hedged causes are trusted text, so check the rest only.
    scrubbed = scrub_causes(scrubbed, list(allowed_causes))
    used = type(jev).__name__
    try:
        flagged = jev.mentions_diagnosis_or_medication(scrubbed)
    except JevError:
        flagged, used = _offline.mentions_diagnosis_or_medication(scrubbed), "OfflineJev (fallback)"
    if flagged >= config.GUARD_THRESHOLD:
        reasons.append("mentions a diagnosis or medication")

    return GuardResult(ok=not reasons, reasons=reasons, used=used)


def check_final(final: FinalAnswer, conversation: str, allowed_causes: list[str]) -> dict[str, list[str]]:
    """Reasons per final-answer section (empty dict = ok). The pipeline replaces a failing section
    with its template version and traces the reason."""
    out: dict[str, list[str]] = {}
    norm = " ".join(conversation.lower().split())
    told = [f"evidence not in the conversation: {b.evidence!r}" for b in final.told
            if not b.evidence.strip() or " ".join(b.evidence.lower().split()) not in norm]
    if told:
        out["told"] = told
    causes = [f"cause not in the matched cluster: {c.cause}" for c in final.causes if c.cause not in allowed_causes]
    if causes:
        out["causes"] = causes
    for name in ("where", "options", "cost", "go_sooner"):  # guide text and records; facts must exist
        value = getattr(final, name)
        reasons = fact_reasons(" ".join(value) if isinstance(value, list) else value)
        if reasons:
            out[name] = reasons
    return out
