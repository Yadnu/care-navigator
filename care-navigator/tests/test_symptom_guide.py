"""CHANGE_conversational_triage.md Part 4: symptom_guide.json schema, and the question bank rebuilt
from it (D-050)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from navigator.models import CareLevel
from navigator.questions import classify, extract, load_bank

DATA = Path(__file__).resolve().parents[1] / "data"
GUIDE = json.loads((DATA / "symptom_guide.json").read_text(encoding="utf-8"))
CLUSTERS = {c["id"]: c for c in GUIDE["clusters"]}
ROUTINE_LEVELS = {level.value for level in CareLevel} - {"ER"}


def test_guide_top_level_fields():
    assert GUIDE["synthetic"] is True
    assert {"version", "disclaimer", "hedging_rules", "clusters"} <= set(GUIDE)


@pytest.mark.parametrize("cluster", GUIDE["clusters"], ids=lambda c: c["id"])
def test_cluster_schema(cluster):
    assert {"id", "name", "match_terms", "ask_about", "possible_cause_questions", "danger_signs",
            "possible_causes", "watch_for"} <= set(cluster)
    assert cluster["match_terms"]
    for item in cluster["ask_about"]:
        assert item["topic"] and item["why"]
    for sign in cluster["danger_signs"]:
        assert sign["action"] in {"CALL_911", "GO_TO_ER"} and sign["why"].strip(), sign
    for cause in cluster["possible_causes"]:
        assert cause["typical_level"] in ROUTINE_LEVELS and cause["description"].strip(), cause


def test_mental_health_has_no_causes_and_no_questions():
    mh = CLUSTERS["mental_health"]
    assert mh["possible_causes"] == [] and mh["ask_about"] == [] and mh["possible_cause_questions"] == []


def test_cluster_ids_are_unique():
    assert len(CLUSTERS) == len(GUIDE["clusters"])


# ------------------------------------------------------------------ question bank (rebuilt from the guide)
def test_bank_has_every_guide_topic_and_cause_question():
    bank = load_bank()
    for cluster in GUIDE["clusters"]:
        for item in cluster["ask_about"]:
            assert cluster["id"] in bank[item["topic"]]["clusters"], item["topic"]
        for i, question in enumerate(cluster["possible_cause_questions"]):
            entry = bank[f"{cluster['id']}.cause{i + 1}"]
            assert entry["kind"] == "cause" and entry["question"] == question
    assert "main_symptom" in bank


def test_bank_entries_are_synthetic_and_well_formed():
    for topic, entry in load_bank().items():
        assert entry["synthetic"] is True, topic
        assert entry["question"].endswith("?"), topic
        assert len(entry["question"].split()) < 30, topic
        values = {o["value"] for o in entry["options"]}
        if entry["options"]:
            assert entry["routine_value"] in values, topic
        for link in entry["danger"]:
            assert set(link["values"]) <= values, topic


def test_every_danger_link_names_a_guide_sign():
    signs = {(c["id"], d["sign"]) for c in GUIDE["clusters"] for d in c["danger_signs"]}
    for topic, entry in load_bank().items():
        for link in entry["danger"]:
            assert (link["cluster"], link["sign"]) in signs, (topic, link)


def test_cause_hints_name_causes_of_their_cluster():
    for topic, entry in load_bank().items():
        if entry["cause"]:
            causes = {c["cause"] for c in CLUSTERS[entry["clusters"][0]]["possible_causes"]}
            assert entry["cause"] in causes and entry["cause_on"] in {"yes", "no"}, topic


@pytest.mark.parametrize("topic, answer, value", [
    ("fluids_kept_down", "Some", "some"),
    ("fluids_kept_down", "nothing stays down", "no"),
    ("fluids_kept_down", "some fluids stay down", "some"),
    ("blood", "no", "no"),
    ("blood", "yes", "vomit"),
    ("blood", "a little in my stool", "stool"),
    ("dehydration_signs", "I'm dizzy when I stand", "yes"),
    ("dehydration_signs", "no dizziness", "no"),
    ("onset", "it came on slowly after a long day on screens", "gradual"),
    ("onset", "suddenly, worst ever", "sudden"),
    ("age", "8 months", "3_to_12_months"),
    ("age", "6 weeks old", "under_3_months"),
    ("temperature_value", "101F", "100_4_to_102"),
    ("location", "lower right", "lower_right"),
    ("onset_and_trend", "getting worse", "worse"),
    ("vomiting_diarrhea.cause1", "ate leftover takeout", "yes"),
    ("vomiting_diarrhea.cause2", "roommate is fine", "no"),
    ("headache.cause1", "Not sure", "unsure"),
])
def test_classify_direct_answers(topic, answer, value):
    assert classify(topic, answer) == value


def test_extract_skips_cause_questions_and_respects_negation():
    found = extract("pain in my left hand since I played volleyball, no numbness")
    assert found.get("injury_mechanism") == "yes" and found.get("numbness") != "yes"
    assert not any(t.endswith(tuple(f".cause{i}" for i in range(1, 6))) for t in found)
