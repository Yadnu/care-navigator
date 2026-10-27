"""Phase 2: keyword + fuzzy red-flag screen (D-002)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from navigator.models import SymptomReport
from navigator.redflags import (
    KEYWORD_DETECTABLE,
    has_injury_context,
    load_rules,
    screen_report,
    screen_text,
    tier2_signals,
    unmatched_flags,
)

EVAL = Path(__file__).resolve().parents[1] / "data" / "eval"


def load_jsonl(name):
    return [json.loads(l) for l in (EVAL / name).read_text(encoding="utf-8").splitlines() if l.strip()]


RED_FLAGS = load_jsonl("red_flags.jsonl")
KEYWORD_CASES = [r for r in RED_FLAGS if r["detectable_by"] in KEYWORD_DETECTABLE]
ROUTING = load_jsonl("routing_cases.jsonl")
NON_EMERGENCY_ROUTING = [r for r in ROUTING if r["expected_outcome"] != "EMERGENCY"]
EMERGENCY_ROUTING = [r for r in ROUTING if r["expected_outcome"] == "EMERGENCY"]
VAGUE = load_jsonl("vague.jsonl")


def test_keyword_detectable_covers_keyword_and_fuzzy():
    assert KEYWORD_DETECTABLE == {"keyword", "fuzzy_keyword"}
    assert len(KEYWORD_CASES) >= 25


@pytest.mark.parametrize("case", KEYWORD_CASES, ids=[c["id"] for c in KEYWORD_CASES])
def test_every_keyword_detectable_red_flag_is_caught(case):
    result = screen_text(case["text"])
    assert result.is_emergency, case["text"]
    assert case["category"] in result.categories, (case["text"], result.categories)


@pytest.mark.parametrize("case", EMERGENCY_ROUTING, ids=[c["id"] for c in EMERGENCY_ROUTING])
def test_emergency_routing_cases_are_caught(case):
    assert screen_text(case["text"]).is_emergency


@pytest.mark.parametrize("case", NON_EMERGENCY_ROUTING + VAGUE,
                         ids=[c["id"] for c in NON_EMERGENCY_ROUTING + VAGUE])
def test_no_false_positives_on_non_emergency_cases(case):
    result = screen_text(case["text"])
    assert not result.is_emergency, (case["text"], result.hits)


@pytest.mark.parametrize("text", ["chest pian since an hour", "cant breath", "worst hedache of my life",
                                  "vomitting blood", "my fase is droopng on one side"])
def test_typos_are_caught_by_fuzzy_match(text):
    result = screen_text(text)
    assert result.is_emergency
    assert any(h.method == "fuzzy" for h in result.hits)


@pytest.mark.parametrize("text", [
    "I can breathe fine, just a stuffy nose",
    "can keep water down",
    "bleeding stopped after a minute",
    "no fever, mild headache",
    "",
])
def test_near_misses_do_not_fire(text):
    assert not screen_text(text).is_emergency


def test_apostrophes_and_case_are_normalized():
    assert screen_text("I CAN’T BREATHE").is_emergency
    assert screen_text("i can't breathe").is_emergency


def test_suicidal_intent_routes_to_988_and_911():
    result = screen_text("I want to end my life")
    assert result.categories == {"mental_health_crisis"}
    assert result.resources == ["988", "911"]
    assert "988" in result.message and "911" in result.message


def test_physical_red_flag_routes_to_911():
    result = screen_text("chest pain and sweating")
    assert result.resources == ["911"]
    assert result.message == "Call 911 or go to the nearest ER."


def test_non_emergency_has_no_message():
    result = screen_text("Sore throat and fever for two days")
    assert result.hits == [] and result.resources == [] and result.message == ""


def test_hits_record_category_phrase_and_method():
    hit = screen_text("crushing chest pain").hits[0]
    assert hit.category == "cardiac"
    assert hit.phrase and hit.method in {"exact", "fuzzy", "pattern"}


def test_rules_file_is_versioned_and_labeled():
    rules = load_rules()
    assert rules["version"]
    assert "not clinically validated" in rules["label"]
    for required in ["cardiac", "breathing", "stroke", "bleeding", "allergic_reaction",
                     "mental_health_crisis", "severe_dehydration"]:
        assert required in rules["categories"]


def test_screen_report_fires_on_parsed_red_flags():
    report = SymptomReport(main_symptom="pressure on chest", severity=6,
                           red_flags=["chest pressure"], confidence="medium")
    assert screen_report(report).is_emergency


def test_screen_report_rechecks_parsed_fields():
    report = SymptomReport(main_symptom="can't keep any water down", severity=5, confidence="high")
    assert screen_report(report).is_emergency


def test_screen_report_quiet_for_ordinary_report():
    report = SymptomReport(main_symptom="sore throat", body_area="throat", duration_hours=48,
                           severity=4, confidence="high")
    assert not screen_report(report).is_emergency


# ------------------------------------------------------------------ Prompt1 A2: tiers, negation, per-word typos
NEAR_MISSES = load_jsonl("near_misses.jsonl")


@pytest.mark.parametrize("case", NEAR_MISSES, ids=[c["id"] for c in NEAR_MISSES])
def test_near_misses_never_hit_tier1(case):
    assert not screen_text(case["text"]).is_emergency, screen_text(case["text"]).hits


@pytest.mark.parametrize("text", ["my arm hurts", "headache", "stomach pain", "short of breath"])
def test_single_weak_signals_are_not_tier1(text):
    assert not screen_text(text).is_emergency
    assert tier2_signals(text)


@pytest.mark.parametrize("text, slot", [
    ("my arm hurts", "associated_cardiac_symptoms"),
    ("my jaw aches", "associated_cardiac_symptoms"),
    ("short of breath", "breathing_at_rest"),
    ("headache", "headache_onset"),
    ("stomach pain", "abdominal_location_and_trend"),
    ("kind of dizzy maybe?", "associated_cardiac_symptoms"),
    ("vomiting since lunch", "fluids_kept_down"),
])
def test_tier2_signals_map_to_a_safety_question(text, slot):
    assert slot in [s.slot for s in tier2_signals(text)]


@pytest.mark.parametrize("text", [
    "no chest pain, I lifted boxes",
    "I don't have chest pain",
    "chest muscles sore, no shortness of breath",
    "throat is a bit scratchy, no swelling",
    "bumped my head, no vomiting",
])
def test_negated_signs_do_not_fire(text):
    assert not screen_text(text).is_emergency
    assert "breathing_at_rest" not in [s.slot for s in tier2_signals(text)]


def test_negation_stops_at_a_clause_break():
    assert screen_text("not sure why, but I have chest pain").is_emergency
    assert screen_text("no fever. chest pain since an hour").is_emergency


@pytest.mark.parametrize("text", ["played volleyball", "after I fell skating", "lifted boxes", "after my flu shot",
                                  "from carrying groceries", "after a hike"])
def test_injury_context(text):
    assert has_injury_context(text)


def test_no_injury_context_for_plain_pain():
    assert not has_injury_context("my arm hurts")
    assert not has_injury_context("I didn't fall, it just hurts")


@pytest.mark.parametrize("typo, word", [("pian", "pain"), ("hedache", "headache"), ("vomitting", "vomiting"),
                                        ("droopng", "drooping")])
def test_per_word_typo_correction_reaches_the_phrase(typo, word):
    result = screen_text({"pain": "chest pian", "headache": "worst hedache of my life",
                          "vomiting": "vomitting blood", "drooping": "face is droopng"}[word])
    assert result.is_emergency and any(h.method == "fuzzy" for h in result.hits)


def test_short_words_are_never_corrected():
    assert not screen_text("I can keep water down").is_emergency  # "can" is not "cant"


def test_parser_flags_that_match_no_rule_are_returned_not_fired():
    report = SymptomReport(main_symptom="hand pain after volleyball", body_area="hand", severity=4,
                           red_flags=["severe pain"], confidence="medium")
    assert not screen_report(report).is_emergency
    assert unmatched_flags(report) == ["severe pain"]


def test_rules_file_has_tiers():
    rules = load_rules()
    assert rules["tier2"] and rules["injury_context"] and rules["negation_cues"]
    assert all(s["safety_slot"] for s in rules["tier2"].values())


@pytest.mark.parametrize("case", RED_FLAGS, ids=[c["id"] for c in RED_FLAGS])
def test_every_red_flag_is_tier1(case):
    # Jev alone needs >= 0.8 with high confidence (D-041), so the rules must catch all 40 on their own.
    assert screen_text(case["text"]).is_emergency, case["text"]
