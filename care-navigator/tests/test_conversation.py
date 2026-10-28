"""Prompt1 Part A regression coverage, ported to the conversational-triage architecture
(CHANGE_conversational_triage.md, D-050, D-051): topics replace slots, the question bank is
rebuilt from the symptom guide, and the interviewer (with its own `guard_question`) replaces the
old clarifier. Bank-schema checks that are now cluster-shaped (every danger sign has one action,
every topic belongs to the guide) live in test_symptom_guide.py and test_safety_consistency.py;
this file keeps the pipeline-behavior invariants and the eval-set regressions.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from navigator import config
from navigator.interviewer import LEVEL_WORDS
from navigator.models import CareLevel, Outcome, Request, Turn
from navigator.parser import OfflineParser
from navigator.pipeline import Navigator
from navigator.questions import classify, extract, load_bank, routine_answer

DATA = Path(__file__).resolve().parents[1] / "data"
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
def test_every_bank_question_is_one_short_question_without_a_care_level():
    # The bank's own template wording is trusted data (guard_question only runs the
    # condition-or-medication check on a model's *rephrasing*, not the template itself):
    # a possible-cause question like "Did you start any new medication recently?" is fine.
    for topic, entry in load_bank().items():
        q = entry["question"]
        assert q.strip().endswith("?") and q.count("?") == 1, topic
        assert len(q.split()) <= config.QUESTION_MAX_WORDS, topic
        assert not LEVEL_WORDS.search(q), topic


def test_routine_answers_are_never_danger_signs():
    for topic, entry in load_bank().items():
        answer = routine_answer(topic)
        assert answer
        danger_values = {v for link in entry["danger"] for v in link["values"]}
        assert classify(topic, answer) not in danger_values, topic


# ------------------------------------------------------------------ eval sets (data)
def test_near_misses_schema():
    assert len(NEAR_MISSES) >= 20
    for r in NEAR_MISSES:
        assert r["synthetic"] is True and r["expected_outcome"] in {"RECOMMENDATION", "EMERGENCY"}
        assert set(r["acceptable_levels"]) <= {l.value for l in CareLevel} and r["acceptable_levels"]
        # D-048: a near miss may be a GO_TO_ER emergency that must never become CALL_911.
        assert (r["expected_outcome"] == "EMERGENCY") == (r.get("expected_action") == "GO_TO_ER")
    assert any(r["text"] == "can't keep water down since this morning" and r["expected_action"] == "GO_TO_ER"
               for r in NEAR_MISSES)
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
@pytest.mark.parametrize("topic, answer, value", [
    ("cardiac_screen", "no chest pain, I lifted boxes yesterday", "no"),
    ("cardiac_screen", "my chest feels tight and I'm sweating", "yes"),
    ("at_rest", "only after stairs, fine at rest", "no"),
    ("at_rest", "yes, even sitting still", "yes"),
    ("onset", "it came on slowly after work", "gradual"),
    ("onset", "worst of my life, came on suddenly", "sudden"),
    ("fluids_kept_down", "I can keep water down", "yes"),
    ("fluids_kept_down", "no, everything comes back up", "no"),
    ("location", "upper, burning, after spicy food", "upper"),
    ("location", "lower right, getting worse", "lower_right"),
    ("age", "8 months old, 101, drinking well", "3_to_12_months"),
    ("age", "6 weeks", "under_3_months"),
    ("swelling_or_deformity", "yes, it's swollen", "yes"),
    ("can_bear_weight", "I can't put weight on it", "no"),
])
def test_classify_answers(topic, answer, value):
    assert classify(topic, answer) == value


def test_unclear_answer_is_none():
    assert classify("onset", "I'm not sure") is None


def test_extract_fills_topics_from_free_text_and_respects_negation():
    assert extract("Twisted my ankle playing soccer, swollen, can walk a little",
                   topics=["swelling_or_deformity", "can_bear_weight"]) == {
        "swelling_or_deformity": "yes", "can_bear_weight": "yes"}
    assert extract("Knee pain from running, no swelling", topics=["swelling_or_deformity"]) == {}
    assert extract("vomiting since dinner, can keep water down",
                   topics=["fluids_kept_down"]) == {"fluids_kept_down": "yes"}
    assert extract("my kid has had a fever for 2 days", topics=["age"]) == {}  # "2 days" is a duration, not an age


# ------------------------------------------------------------------ Prompt1 A1 regression
class FlagsSeverePain(OfflineParser):
    """What Claude did in traces/8340ab6389a1.json: listed 'severe pain' as a red flag."""

    def parse(self, text, severity):
        r = super().parse(text, severity)
        return r.model_copy(update={"report": r.report.model_copy(update={"red_flags": ["severe pain"]})})


def test_parser_flag_alone_is_not_an_emergency(tmp_path):
    nav = Navigator(parser=FlagsSeverePain(), trace_dir=tmp_path, save_traces=False)
    result = nav.run(req("My left hand have severe pain ever since I have played volleyball"))
    assert not result.is_emergency


# ------------------------------------------------------------------ tiers in the pipeline
def test_tier1_stops_immediately_with_no_questions(nav):
    result = nav.run(req("crushing chest pain", 7))
    assert result.is_emergency and result.questions_asked == 0


def test_tier2_asks_a_safety_question_with_quick_replies(nav):
    result = nav.run(req("my arm hurts", 3))
    assert result.outcome is Outcome.QUESTION
    assert result.topic == "cardiac_screen"
    assert result.question == load_bank()["cardiac_screen"]["question"]
    assert result.quick_replies == ["No", "Yes"]


def test_danger_answer_is_an_emergency(nav):
    turns = [Turn(topic="at_rest", question="q", answer="yes")]
    assert nav.run(req("short of breath", turns=turns)).is_emergency


def test_tier1_sign_in_any_answer_is_an_emergency(nav):
    turns = [Turn(topic="cardiac_screen", question="q", answer="no, but now I can't breathe")]
    assert nav.run(req("my arm hurts", turns=turns)).is_emergency


def test_jev_vagueness_does_not_override_a_clearly_named_symptom():
    from navigator.jev_client import OfflineJev

    class SaysVague(OfflineJev):  # live Jev scored the A1 text 0.75 "too vague"
        def is_too_vague(self, text):
            return 0.75, 0.5

    nav = Navigator(jev=SaysVague(), save_traces=False)
    result = nav.run(req("My left hand have severe pain ever since I have played volleyball"))
    assert result.topic != "main_symptom"                                        # hand + pain is specific
    assert nav.run(req("I just feel off")).topic == "main_symptom"               # really vague still asks


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
    assert not Navigator(jev=Mid(), save_traces=False).run(req(text)).is_emergency
    assert not Navigator(jev=HighButUnsure(), save_traces=False).run(req(text)).is_emergency
    assert Navigator(jev=HighAndSure(), save_traces=False).run(req(text)).is_emergency


def test_question_limit_reached_escalates(nav):
    turns = [Turn(topic="main_symptom", question="q", answer="I'm not sure") for _ in range(config.MAX_QUESTIONS)]
    result = nav.run(req("I feel off", turns=turns))
    assert result.outcome in (Outcome.RECOMMENDATION, Outcome.CALL_911, Outcome.GO_TO_ER)
    if result.outcome is Outcome.RECOMMENDATION:
        assert result.recommendation.decision.escalated is True  # remaining uncertainty -> one level more care


def test_skip_routes_now_and_escalates_one_level(nav):
    base = nav.converse(req("Sore throat and fever for two days")).recommendation.decision.level
    skipped = nav.run(req("Sore throat and fever for two days", skip=True))
    assert skipped.outcome is Outcome.RECOMMENDATION
    assert skipped.recommendation.decision.level is base.escalate()


def test_skip_on_an_unanswered_safety_check_escalates(nav):
    result = nav.run(req("my arm hurts", 3, skip=True))
    assert result.outcome is Outcome.RECOMMENDATION and result.recommendation.decision.escalated


def test_answers_are_redacted_in_the_trace(tmp_path):
    nav = Navigator(trace_dir=tmp_path)
    turns = [Turn(topic="main_symptom", question="q", answer="my name is Jane Doe, sore throat for 2 days")]
    result = nav.run(req("I feel off", turns=turns))
    assert "Jane" not in Path(result.trace_path).read_text(encoding="utf-8")


def test_follow_up_answer_shorthand_still_works(nav):
    result = nav.converse(req("I just feel off", followup_answer="sore throat and fever for two days"))
    assert result.outcome is Outcome.RECOMMENDATION


# ------------------------------------------------------------------ eval sets end to end
@pytest.mark.parametrize("case", NEAR_MISSES, ids=[c["id"] for c in NEAR_MISSES])
def test_near_misses_are_not_emergencies_and_route_acceptably(nav, case):
    result = nav.converse(req(case["text"], case["severity"]))
    if case["expected_outcome"] == "EMERGENCY":  # D-048: GO_TO_ER, never CALL_911
        assert result.is_emergency and result.action == case["expected_action"], result
        return
    assert result.outcome is Outcome.RECOMMENDATION, (case["text"], result.outcome, result.message)
    assert result.recommendation.decision.level.value in case["acceptable_levels"], \
        (case["text"], result.recommendation.decision)
    assert result.questions_asked <= config.MAX_QUESTIONS


@pytest.mark.parametrize("case", CONVERSATIONS, ids=[c["id"] for c in CONVERSATIONS])
def test_scripted_conversations(nav, case):
    request = Request(text=case["text"], severity=case["severity"], zip=case["zip"], plan=case["plan"],
                      request_time=datetime.fromisoformat(case["request_time"]), age_group=case["age_group"])
    result = nav.converse(request, answers=case["answers"])
    assert result.outcome.value == case["expected_outcome"], (case["id"], result.message, result.asked_topics)
    if result.recommendation:
        assert result.recommendation.decision.level.value in case["acceptable_levels"], \
            (case["id"], result.recommendation.decision)
    assert result.questions_asked <= case["max_questions"], (case["id"], result.asked_topics)
    assert set(case["must_ask"]) <= set(result.asked_topics), (case["id"], result.asked_topics)
