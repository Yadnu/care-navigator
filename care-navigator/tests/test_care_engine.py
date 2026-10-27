"""Phase 4: care_rules.yaml + care_engine.py (D-001, D-003)."""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

import pytest

from navigator.care_engine import CareEngine, load_rules
from navigator.data import is_open, load_practitioners
from navigator.jev_client import CATEGORIES, OfflineJev
from navigator.models import CareLevel, Practitioner, SymptomReport
from navigator.parser import OfflineParser

EVAL = Path(__file__).resolve().parents[1] / "data" / "eval"
TUE_DAY = datetime(2026, 11, 3, 14, 0)
TUE_EVE = datetime(2026, 11, 3, 22, 30)
MIDNIGHT = datetime(2026, 11, 4, 0, 15)


def load_jsonl(name):
    return [json.loads(l) for l in (EVAL / name).read_text(encoding="utf-8").splitlines() if l.strip()]


ROUTING = [r for r in load_jsonl("routing_cases.jsonl") if r["expected_outcome"] == "RECOMMENDATION"]
engine = CareEngine()
jev = OfflineJev()
parser = OfflineParser()


def decide_case(case, **overrides):
    report = parser.parse(case["text"], case["severity"]).report
    category, _, _ = jev.classify_category(case["text"])
    urgency, _ = jev.urgency_score(case["text"])
    kwargs = dict(report=report, category=category, urgency=urgency,
                  request_time=datetime.fromisoformat(case["request_time"]),
                  plan=case["plan"], age_group=case.get("age_group", "adult"))
    kwargs.update(overrides)
    return engine.decide(**kwargs)


def report(**fields):
    base = dict(main_symptom="sore throat", body_area="throat", duration_hours=48, severity=4, confidence="high")
    base.update(fields)
    return SymptomReport(**base)


# ------------------------------------------------------------------ opening hours
@pytest.mark.parametrize("hours, when, expected", [
    ({"tue": "24h"}, TUE_DAY, True),
    ({"tue": "08:00-20:00"}, TUE_DAY, True),
    ({"tue": "08:00-14:00"}, TUE_DAY, False),   # end is exclusive
    ({"tue": "14:00-20:00"}, TUE_DAY, True),    # start is inclusive
    ({"tue": None}, TUE_DAY, False),
    ({}, TUE_DAY, False),
])
def test_is_open(hours, when, expected):
    assert is_open(hours, when) is expected


def test_practitioners_load_as_models():
    pracs = load_practitioners()
    assert len(pracs) == 44 and all(isinstance(p, Practitioner) for p in pracs)


# ------------------------------------------------------------------ rules file
def test_rules_file_is_versioned_and_labeled():
    rules = load_rules()
    assert rules["version"]
    assert "not clinically validated" in rules["label"].lower()


def test_rules_are_well_formed():
    rules = load_rules()["rules"]
    ids = [r["id"] for r in rules]
    assert len(ids) == len(set(ids)) and 12 <= len(ids) <= 25
    levels = {l.value for l in CareLevel}
    for r in rules:
        assert re.fullmatch(r"R-\d\d", r["id"]), r["id"]
        assert r["level"] in levels, r["id"]
        assert r["after_hours"] in levels - {"SELF_CARE"}, r["id"]  # never down to self-care
        assert set(r.get("when", {}).get("category", [])) <= set(CATEGORIES), r["id"]


def test_last_rule_is_a_catch_all():
    assert not load_rules()["rules"][-1].get("when")


# ------------------------------------------------------------------ routing eval
@pytest.mark.parametrize("case", ROUTING, ids=[c["id"] for c in ROUTING])
def test_routing_case_lands_on_an_acceptable_level_never_lower(case):
    decision = decide_case(case)
    expected = CareLevel(case["expected_level"])
    assert decision.level >= expected, (case["text"], decision)
    assert decision.level.value in case["acceptable_levels"], (case["text"], decision)


def test_midnight_food_poisoning_goes_to_telehealth_with_er_note():
    case = next(c for c in ROUTING if c["id"] == "RT-002")
    decision = decide_case(case)
    assert decision.level is CareLevel.TELEHEALTH
    assert any("ER" in n and "fluids" in n for n in decision.notes), decision.notes
    assert any("closed" in n.lower() for n in decision.notes), decision.notes


def test_same_case_in_daytime_is_urgent_care():
    case = next(c for c in ROUTING if c["id"] == "RT-002")
    assert decide_case(case, request_time=TUE_DAY).level is CareLevel.URGENT_CARE


def test_decision_records_rule_and_version():
    case = ROUTING[0]
    decision = decide_case(case)
    assert re.fullmatch(r"R-\d\d", decision.rule_id)
    assert decision.rules_version == load_rules()["version"]


def test_decisions_are_deterministic():
    case = ROUTING[0]
    assert decide_case(case) == decide_case(case)


# ------------------------------------------------------------------ confidence gating
def test_high_confidence_is_not_escalated():
    d = engine.decide(report(), category="ent", urgency=2, request_time=TUE_DAY, plan="PLAN_GOLD_PPO")
    assert d.level is CareLevel.URGENT_CARE and d.escalated is False


def test_medium_confidence_from_model_uncertainty_escalates_one_level():
    d = engine.decide(report(confidence="medium"), category="respiratory", urgency=2,
                      request_time=TUE_DAY, plan="PLAN_GOLD_PPO")
    assert d.escalated is True
    assert d.level is CareLevel.PRIMARY_CARE  # TELEHEALTH + 1


def test_medium_confidence_from_unstated_duration_alone_does_not_escalate():
    r = report(duration_hours=None, missing=["duration"], confidence="medium")
    d = engine.decide(r, category="ent", urgency=2, request_time=TUE_DAY, plan="PLAN_GOLD_PPO")
    assert d.escalated is False and d.level is CareLevel.URGENT_CARE


def test_unknown_duration_never_matches_a_long_standing_rule():
    long = engine.decide(report(duration_hours=720), category="skin", urgency=2,
                         request_time=TUE_DAY, plan="PLAN_GOLD_PPO")
    unknown = engine.decide(report(duration_hours=None, missing=["duration"], confidence="medium"),
                            category="skin", urgency=2, request_time=TUE_DAY, plan="PLAN_GOLD_PPO")
    assert long.rule_id != unknown.rule_id


def test_still_vague_after_follow_up_escalates():
    r = report(main_symptom=None, body_area=None, duration_hours=None,
               missing=["main_symptom", "duration"], confidence="low")
    first = engine.decide(r, category="general", urgency=2, request_time=TUE_DAY, plan="PLAN_GOLD_PPO")
    after = engine.decide(r, category="general", urgency=2, request_time=TUE_DAY, plan="PLAN_GOLD_PPO",
                          after_followup=True)
    assert after.escalated is True
    assert after.level > first.level


def test_escalation_caps_at_er():
    d = engine.decide(report(confidence="medium"), category="ent", urgency=5,
                      request_time=TUE_DAY, plan="PLAN_GOLD_PPO")
    assert d.level is CareLevel.ER


# ------------------------------------------------------------------ safety-leaning rules
def test_top_urgency_goes_to_er():
    d = engine.decide(report(), category="ent", urgency=5, request_time=TUE_DAY, plan="PLAN_GOLD_PPO")
    assert d.level is CareLevel.ER


def test_very_high_severity_is_at_least_urgent_care():
    d = engine.decide(report(severity=9, main_symptom="headache"), category="neuro", urgency=1,
                      request_time=TUE_DAY, plan="PLAN_GOLD_PPO")
    assert d.level >= CareLevel.URGENT_CARE


def test_unrecognised_category_fails_toward_more_care():
    d = engine.decide(report(main_symptom="odd feeling"), category="general", urgency=2,
                      request_time=TUE_DAY, plan="PLAN_GOLD_PPO")
    assert d.level >= CareLevel.URGENT_CARE


# ------------------------------------------------------------------ opening hours
def test_closed_injury_goes_up_to_er_not_down():
    d = engine.decide(report(main_symptom="twisted ankle"), category="musculoskeletal", urgency=4,
                      request_time=TUE_EVE, plan="PLAN_GOLD_PPO")
    assert d.level is CareLevel.ER
    assert d.notes[0] == "Urgent care is closed now (22:30), so the next open option is the ER."


def test_after_hours_never_drops_to_self_care():
    for case in ROUTING:
        d = decide_case(case, request_time=MIDNIGHT)
        assert d.level is not CareLevel.SELF_CARE or decide_case(case, request_time=TUE_DAY).level is CareLevel.SELF_CARE


def test_self_care_does_not_need_an_open_practitioner():
    d = engine.decide(report(main_symptom="sneezing, itchy eyes", severity=2), category="allergy", urgency=1,
                      request_time=MIDNIGHT, plan="PLAN_GOLD_PPO")
    assert d.level is CareLevel.SELF_CARE


def test_closed_fallback_steps_up_until_something_is_open():
    only_er = [p for p in load_practitioners() if p.type == "ER"]
    d = CareEngine(practitioners=only_er).decide(report(), category="ent", urgency=2,
                                                 request_time=TUE_DAY, plan="PLAN_GOLD_PPO")
    assert d.level is CareLevel.ER
    assert any("closed" in n.lower() for n in d.notes)


def test_child_needs_a_provider_that_sees_children():
    # 22:30: pediatric telehealth (TH-004) is closed; NightOwl (all ages) is open.
    r = report(main_symptom="fever, rash", body_area="skin", duration_hours=None, missing=["duration"],
               confidence="medium")
    d = engine.decide(r, category="skin", urgency=2, request_time=TUE_EVE, plan="PLAN_SILVER_HMO",
                      age_group="child")
    assert d.level is CareLevel.TELEHEALTH


def test_unknown_plan_still_gets_a_level():
    d = engine.decide(report(), category="ent", urgency=2, request_time=TUE_DAY, plan="PLAN_DOES_NOT_EXIST")
    assert d.level is CareLevel.URGENT_CARE


def test_no_plan_still_gets_a_level():
    d = engine.decide(report(), category="ent", urgency=2, request_time=TUE_DAY, plan=None)
    assert d.level is CareLevel.URGENT_CARE
