"""Shared symptom vocabulary for the offline classifier and offline parser.

Patterns run on text normalized by `redflags.normalize` (lowercase, no apostrophes,
punctuation -> spaces). Simplified, not clinically validated.
"""
from __future__ import annotations

import re

# Symptom terms by category. Any match makes the text "specific" (not vague).
SYMPTOM_TERMS: dict[str, list[str]] = {
    "respiratory": [r"cough\w*", r"runny nose", r"stuffy nose", r"congest\w*", r"cold symptoms", r"chest cold",
                    r"short of breath", r"shortness of breath", r"out of breath", r"breathless"],
    "ent": [r"sore throat", r"ear ?aches?", r"ear pain", r"sinus\w*", r"tonsil\w*", r"hoarse"],
    "gastrointestinal": [r"vomit\w*", r"threw up", r"throwing up", r"diarrh?ea", r"cramps?", r"nause\w*",
                         r"heartburn", r"acid reflux", r"constipat\w*", r"stomach (bug|ache|pain)",
                         r"keep (any )?(water|fluids|anything) down"],
    "musculoskeletal": [r"sprain\w*", r"twisted", r"strain\w*", r"pulled (a )?muscle",
                        # injury context (D-041): an injury points to the injury rules
                        r"played", r"fell", r"tripped", r"lifted", r"lifting", r"carrying", r"carried",
                        r"volleyball", r"soccer", r"basketball", r"tennis", r"bench press", r"skating",
                        r"hike", r"hiking", r"moving furniture"],
    "skin": [r"rash\w*", r"hives", r"itch\w*", r"acne", r"eczema"],
    "eye": [r"pink eye", r"crusty", r"red eyes?"],
    "urinary": [r"burning when i pee", r"(pain|hurts) when i pee", r"urinat\w*", r"\buti\b"],
    "wound": [r"cut", r"bite", r"puncture", r"splinter", r"burn", r"burned", r"blister", r"scrape\w*", r"wound"],
    "dental": [r"tooth\w*", r"teeth"],
    "mental_health": [r"stress\w*", r"anxi\w*", r"cant sleep", r"insomnia", r"panic\w*", r"depress\w*"],
    "chronic": [r"refill", r"blood pressure", r"check ?up", r"diabetes", r"cholesterol"],
    "allergy": [r"sneez\w*", r"itchy eyes", r"every spring", r"seasonal", r"pollen", r"allerg\w*"],
    "fever": [r"fever\w*", r"flu", r"body aches", r"chills"],
    "neuro": [r"headaches?", r"migraines?"],
}

# Body areas: name -> (pattern, category it leans toward). Not specific on their own.
BODY_AREAS: dict[str, tuple[str, str]] = {
    "throat": (r"throat", "ent"),
    "ear": (r"ears?", "ent"),
    "stomach": (r"stomach|belly|abdomen|tummy", "gastrointestinal"),
    "chest": (r"chest", "respiratory"),
    "head": (r"head", "neuro"),
    "eye": (r"eyes?", "eye"),
    "ankle": (r"ankles?", "musculoskeletal"),
    "knee": (r"knees?", "musculoskeletal"),
    "wrist": (r"wrists?", "musculoskeletal"),
    "back": (r"back", "musculoskeletal"),
    "shoulder": (r"shoulders?", "musculoskeletal"),
    "hand": (r"hands?|fingers?|fingernail|palm", "musculoskeletal"),
    "arm": (r"arms?", "musculoskeletal"),
    "leg": (r"legs?", "musculoskeletal"),
    "neck": (r"neck", "musculoskeletal"),
    "jaw": (r"jaw", "dental"),
    "skin": (r"skin", "skin"),
    "mouth": (r"mouth|cheek|gums?", "dental"),
    "urinary": (r"pee|peeing|bladder", "urinary"),
}

PAIN_WORDS = r"pain|painful|hurts?|aches?|sore|swollen|swelling"


def _search(pattern: str, text: str) -> re.Match | None:
    return re.search(rf"\b(?:{pattern})\b", text)


def symptom_matches(norm: str) -> list[tuple[int, str, str]]:
    """(position, matched text, category) for every symptom term, in text order."""
    found = []
    for category, patterns in SYMPTOM_TERMS.items():
        for p in patterns:
            for m in re.finditer(rf"\b(?:{p})\b", norm):
                found.append((m.start(), m.group(), category))
    return sorted(found)


def body_areas(norm: str) -> list[tuple[int, str, str]]:
    """(position, area name, category) for every body area, in text order."""
    found = []
    for name, (pattern, category) in BODY_AREAS.items():
        m = _search(pattern, norm)
        if m:
            found.append((m.start(), name, category))
    return sorted(found)


def has_pain_word(norm: str) -> bool:
    return _search(PAIN_WORDS, norm) is not None


def is_specific(norm: str) -> bool:
    """A named symptom, or a body area together with a pain word ("knee pain")."""
    return bool(symptom_matches(norm)) or (bool(body_areas(norm)) and has_pain_word(norm))
