"""Prompt1 Part A: three-tier red flags, question bank, multi-turn clarification (D-041)."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from navigator import config
from navigator.clarifier import is_valid_question
from navigator.models import CareLevel, Outcome, Request, Turn
from navigator.parser import OfflineParser
from navigator.pipeline import Navigator
from navigator.questions import classify, extract, load_bank, routine_answer

DATA = Path(__file__).resolve().parents[1] / "data"
REQUIRED_SLOTS = {"main_symptom", "duration", "severity_now", "location_detail", "injury_mechanism",
                  "swelling_or_deformity", "can_use_or_bear_weight", "associated_cardiac_symptoms",
                  "headache_onset", "breathing_at_rest", "fluids_kept_down", "urine_output", "fever_value",
                  "child_age", "abdominal_location_and_trend"}
TUE_DAY = datetime(2026, 11, 3, 14, 0)


def load_jsonl(name):
    return [json.loads(l) for l in (DATA / "eval" / f"{name}.jsonl").read_text(encoding="utf-8").splitlines()
            if l.strip()]


NEAR_MISSES, CONVERSATIONS = load_jsonl("near_misses"), load_jsonl("conversations")


@pytest.fixture(scope="module")
def nav(tmp_path_factory):
    return Navigator(trace_dir=tmp_path_factory.mktemp("traces"), save_traces=False)


def req(text, severity=4, when=TUE_DAY, age_group="adult", **kw):
    return Request(text=text, severity=severity, zip="00101", plan="PLAN_SILVER_HMO", request_time=when,
                   age_group=age_group, **kw)


# ------------------------------------------------------------------ question bank (data)
def test_question_bank_has_every_required_slot_and_is_synthetic():
    raw = json.loads((DATA / "question_bank.json").read_text(encoding="utf-8"))
    assert {q["slot"] for q in raw} >= REQUIRED_SLOTS
    for q in raw:
        assert q["synthetic"] is True
        assert q["kind"] in {"safety", "detail"}
        assert set(q["danger_values"]) <= {o["value"] for o in q["options"]}
        assert q["routine_value"] is None or q["routine_value"] in {o["value"] for o in q["options"]}
        assert q["routine_value"] not in q["danger_values"]
        assert q["categories"]


def test_every_bank_question_is_one_short_question_without_levels_or_diagnoses():
    for slot, entry in load_bank().items():
        assert is_valid_question(entry["question"]), slot


# ------------------------------------------------------------------ eval sets (data)
def test_near_misses_schema():
    assert len(NEAR_MISSES) >= 20
    for r in NEAR_MISSES:
        assert r["synthetic"] is True and r["expected_outcome"] == "RECOMMENDATION"
        assert set(r["acceptable_levels"]) <= {l.value for l in CareLevel} and r["acceptable_levels"]
    texts = " | ".join(r["text"] for r in NEAR_MISSES)
    for required in ["pain in my left hand ever since I played volleyball", "sore left arm after my flu shot",
                     "left wrist hurts after I fell skating", "chest muscles sore after bench press yesterday",
                     "short of breath after running, normal again in 5 minutes",
                     "headache after a long day at the screen", "cut my hand, bleeding stopped with pressure",
                     "stomach ache after spicy food, mild"]:
        assert required in texts, required


def test_conversations_schema():
    assert len(CONVERSATIONS) >= 12
    bank = load_bank()
    for c in CONVERSATIONS:
        assert c["synthetic"] is True and c["expected_outcome"] in {o.value for o in Outcome}
        assert set(c["answers"]) <= set(bank) and set(c["must_ask"]) <= set(bank)
        assert 0 <= c["max_questions"] <= config.MAX_QUESTIONS


# ------------------------------------------------------------------ answer classification
@pytest.mark.parametrize("slot, answer, value", [
    ("associated_cardiac_symptoms", "no chest pain, I lifted boxes yesterday", "no"),
    ("associated_cardiac_symptoms", "my chest feels tight and I'm sweating", "yes"),
    ("breathing_at_rest", "only after stairs, fine at rest", "no"),
    ("breathing_at_rest", "yes, even sitting still", "yes"),
    ("headache_onset", "it came on slowly after work", "gradual"),
    ("headache_onset", "worst of my life, came on suddenly", "sudden"),
    ("fluids_kept_down", "I can keep water down", "yes"),
    ("fluids_kept_down", "no, everything comes back up", "no"),
    ("abdominal_location_and_trend", "upper, burning, after spicy food", "upper"),
    ("abdominal_location_and_trend", "lower right, getting worse, and I have a fever", "lower_right_worse"),
    ("child_age", "8 months old, 101, drinking well", "3_to_12_months"),
    ("child_age", "6 weeks", "under_3_months"),
    ("swelling_or_deformity", "yes, it's swollen", "yes"),
    ("can_use_or_bear_weight", "I can't put weight on it", "no"),
])
def test_classify_answers(slot, answer, value):
    assert classify(slot, answer) == value


def test_unclear_answer_is_none():
    assert classify("headache_onset", "I'm not sure") is None


def test_extract_fills_slots_from_free_text_and_respects_negation():
    slots = extract("Twisted my ankle playing soccer, swollen, can walk a little")
    assert slots["swelling_or_deformity"] == "yes" and slots["can_use_or_bear_weight"] == "yes"
    assert extract("Knee pain from running, no swelling").get("swelling_or_deformity") != "yes"
    assert extract("vomiting since dinner, can keep water down")["fluids_kept_down"] == "yes"
    assert "child_age" not in extract("my kid has had a fever for 2 days")  # "2 days" is a duration, not an age


def test_routine_answers_are_never_danger_signs():
    for slot, entry in load_bank().items():
        answer = routine_answer(slot)
        assert answer
        assert classify(slot, answer) not in entry["danger_values"], slot


# ------------------------------------------------------------------ Prompt1 A1 regression
class FlagsSeverePain(OfflineParser):
    """What Claude did in traces/8340ab6389a1.json: listed 'severe pain' as a red flag."""

    def parse(self, text, severity):
        r = super().parse(text, severity)
        return r.model_copy(update={"report": r.report.model_copy(update={"red_flags": ["severe pain"]})})


def test_parser_flag_alone_is_not_an_emergency(tmp_path):
    nav = Navigator(parser=FlagsSeverePain(), trace_dir=tmp_path, save_traces=False)
    result = nav.run(req("My left hand have severe pain ever since I have played volleyball"))
    assert result.outcome is not Outcome.EMERGENCY


# ------------------------------------------------------------------ tiers in the pipeline
def test_tier1_stops_immediately_with_no_questions(nav):
    result = nav.run(req("crushing chest pain", 7))
    assert result.outcome is Outcome.EMERGENCY and result.questions_asked == 0


def test_tier2_asks_a_safety_question_with_quick_replies(nav):
    result = nav.run(req("my arm hurts", 3))
    assert result.outcome is Outcome.SAFETY_CHECK
    assert result.slot == "associated_cardiac_symptoms"
    assert result.question == load_bank()["associated_cardiac_symptoms"]["question"]
    assert result.quick_replies == ["No", "Yes"]


def test_injury_context_skips_the_cardiac_safety_question(nav):
    result = nav.run(req("my left arm is sore from carrying groceries", 2))
    assert result.outcome is not Outcome.SAFETY_CHECK and result.slot != "associated_cardiac_symptoms"


def test_danger_answer_is_an_emergency(nav):
    turns = [Turn(slot="breathing_at_rest", question="q", answer="yes")]
    assert nav.run(req("short of breath", turns=turns)).outcome is Outcome.EMERGENCY


def test_tier1_sign_in_any_answer_is_an_emergency(nav):
    turns = [Turn(slot="associated_cardiac_symptoms", question="q", answer="no, but now I can't breathe")]
    assert nav.run(req("my arm hurts", turns=turns)).outcome is Outcome.EMERGENCY


def test_jev_alone_needs_high_probability_and_confidence(tmp_path):
    from navigator.jev_client import OfflineJev

    class Mid(OfflineJev):
        def is_emergency(self, text):
            return 0.7, 0.9

    class HighButUnsure(OfflineJev):
        def is_emergency(self, text):
            return 0.9, 0.3

    class HighAndSure(OfflineJev):
        def is_emergency(self, text):
            return 0.9, 0.9

    text = "my wrist feels strange"
    assert Navigator(jev=Mid(), save_traces=False).run(req(text)).outcome is Outcome.SAFETY_CHECK
    assert Navigator(jev=HighButUnsure(), save_traces=False).run(req(text)).outcome is Outcome.SAFETY_CHECK
    assert Navigator(jev=HighAndSure(), save_traces=False).run(req(text)).outcome is Outcome.EMERGENCY


def test_never_more_than_three_questions(nav):
    turns = [Turn(slot=s, question="q", answer="I'm not sure")
             for s in ["main_symptom", "associated_cardiac_symptoms", "location_detail"]]
    result = nav.run(req("I feel off", turns=turns))
    assert result.outcome in (Outcome.RECOMMENDATION, Outcome.EMERGENCY)
    assert result.recommendation.decision.escalated is True  # remaining uncertainty -> one level more care


def test_skip_routes_now_and_escalates_one_level(nav):
    base = nav.run(req("Sore throat and fever for two days")).recommendation.decision.level
    skipped = nav.run(req("Sore throat and fever for two days", skip=True))
    assert skipped.outcome is Outcome.RECOMMENDATION
    assert skipped.recommendation.decision.level is base.escalate()


def test_skip_on_an_unanswered_safety_check_escalates(nav):
    result = nav.run(req("my arm hurts", 3, skip=True))
    assert result.outcome is Outcome.RECOMMENDATION and result.recommendation.decision.escalated


def test_answers_are_redacted_in_the_trace(tmp_path):
    nav = Navigator(trace_dir=tmp_path)
    turns = [Turn(slot="main_symptom", question="q", answer="my name is Jane Doe, sore throat for 2 days")]
    result = nav.run(req("I feel off", turns=turns))
    assert "Jane" not in Path(result.trace_path).read_text(encoding="utf-8")


def test_follow_up_answer_shorthand_still_works(nav):
    result = nav.run(req("I just feel off", followup_answer="sore throat and fever for two days"))
    assert result.outcome is Outcome.RECOMMENDATION


# ------------------------------------------------------------------ eval sets end to end
@pytest.mark.parametrize("case", NEAR_MISSES, ids=[c["id"] for c in NEAR_MISSES])
def test_near_misses_are_not_emergencies_and_route_acceptably(nav, case):
    result = nav.converse(req(case["text"], case["severity"]))
    assert result.outcome is Outcome.RECOMMENDATION, (case["text"], result.outcome, result.message)
    assert result.recommendation.decision.level.value in case["acceptable_levels"], (case["text"], result.recommendation.decision)
    assert result.questions_asked <= config.MAX_QUESTIONS


@pytest.mark.parametrize("case", CONVERSATIONS, ids=[c["id"] for c in CONVERSATIONS])
def test_scripted_conversations(nav, case):
    request = Request(text=case["text"], severity=case["severity"], zip=case["zip"], plan=case["plan"],
                      request_time=datetime.fromisoformat(case["request_time"]), age_group=case["age_group"])
    result = nav.converse(request, answers=case["answers"], default=case["default_answer"])
    assert result.outcome.value == case["expected_outcome"], (case["id"], result.message, result.asked_slots)
    if result.recommendation:
        assert result.recommendation.decision.level.value in case["acceptable_levels"], (case["id"], result.recommendation.decision)
    assert result.questions_asked <= case["max_questions"], (case["id"], result.asked_slots)
    assert set(case["must_ask"]) <= set(result.asked_slots), (case["id"], result.asked_slots)
