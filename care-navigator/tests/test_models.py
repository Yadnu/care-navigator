"""Phase 2: Pydantic schemas in navigator/models.py."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from navigator.models import (
    CareDecision,
    CareLevel,
    CostEstimate,
    JevAnswers,
    Match,
    Option,
    Outcome,
    Practitioner,
    Recommendation,
    Request,
    SymptomReport,
    TraceStep,
)

DATA = Path(__file__).resolve().parents[1] / "data"


def make_request(**overrides) -> Request:
    fields = dict(text="sore throat", severity=4, zip="00101", plan="PLAN_SILVER_HMO",
                  request_time=datetime(2026, 11, 3, 14, 0))
    fields.update(overrides)
    return Request(**fields)


def test_request_defaults_and_parses_iso_time():
    r = make_request(request_time="2026-11-04T00:15")
    assert r.request_time == datetime(2026, 11, 4, 0, 15)
    assert r.age_group == "adult"
    assert r.followup_answer is None


@pytest.mark.parametrize("severity", [0, 11])
def test_request_severity_must_be_1_to_10(severity):
    with pytest.raises(ValidationError):
        make_request(severity=severity)


def test_request_age_group_is_adult_or_child():
    assert make_request(age_group="child").age_group == "child"
    with pytest.raises(ValidationError):
        make_request(age_group="senior")


def test_outcome_values():
    assert {o.value for o in Outcome} == {"CALL_911", "GO_TO_ER", "QUESTION", "RECOMMENDATION"}


def test_care_levels_are_ordered_low_to_high():
    order = [CareLevel.SELF_CARE, CareLevel.TELEHEALTH, CareLevel.PRIMARY_CARE,
             CareLevel.URGENT_CARE, CareLevel.ER]
    assert sorted(order, key=lambda l: l.rank) == order
    assert CareLevel.TELEHEALTH < CareLevel.URGENT_CARE
    assert CareLevel.ER > CareLevel.PRIMARY_CARE


def test_escalate_moves_one_level_up_and_caps_at_er():
    assert CareLevel.SELF_CARE.escalate() == CareLevel.TELEHEALTH
    assert CareLevel.URGENT_CARE.escalate() == CareLevel.ER
    assert CareLevel.ER.escalate() == CareLevel.ER


def test_symptom_report_defaults_and_confidence_values():
    r = SymptomReport(main_symptom="sore throat", severity=4, confidence="high")
    assert r.body_area is None and r.duration_hours is None
    assert r.red_flags == [] and r.missing == []
    with pytest.raises(ValidationError):
        SymptomReport(main_symptom="x", severity=4, confidence="certain")


def test_symptom_report_rejects_negative_duration():
    with pytest.raises(ValidationError):
        SymptomReport(main_symptom="x", severity=4, duration_hours=-1, confidence="high")


def test_jev_answers_probabilities_are_bounded():
    ok = JevAnswers(emergency_prob=0.1, emergency_confidence=0.9, category="respiratory",
                    category_probs={"respiratory": 0.8, "other": 0.2}, category_confidence=0.8,
                    urgency=2, urgency_confidence=0.7, vague_prob=0.1, vague_confidence=0.9)
    assert ok.urgency == 2
    with pytest.raises(ValidationError):
        JevAnswers(**{**ok.model_dump(), "emergency_prob": 1.5})
    with pytest.raises(ValidationError):
        JevAnswers(**{**ok.model_dump(), "urgency": 6})


def test_care_decision_fields():
    d = CareDecision(level="URGENT_CARE", rule_id="R-07", escalated=False, rules_version="1.0")
    assert d.level is CareLevel.URGENT_CARE
    assert d.notes == []


def test_every_practitioner_in_data_validates():
    records = json.loads((DATA / "practitioners.json").read_text(encoding="utf-8"))
    practitioners = [Practitioner(**r) for r in records]
    assert len(practitioners) == len(records)
    assert all(p.synthetic for p in practitioners)


def test_practitioner_must_be_synthetic():
    record = json.loads((DATA / "practitioners.json").read_text(encoding="utf-8"))[0]
    with pytest.raises(ValidationError):
        Practitioner(**{**record, "synthetic": False})


def test_recommendation_holds_decision_and_options():
    record = json.loads((DATA / "practitioners.json").read_text(encoding="utf-8"))[0]
    decision = CareDecision(level="ER", rule_id="R-01", escalated=False, rules_version="1.0")
    match = Match(practitioner=Practitioner(**record), distance_km=1.2, score=0.5, matched_text="chest pain")
    cost = CostEstimate(care_type="ER", copay_usd=250, typical_range_usd=(1200, 3500))
    rec = Recommendation(decision=decision, options=[Option(match=match, cost=cost)])
    assert rec.explanation == "" and rec.notes == [] and rec.alternatives == [] and rec.nurse_line is None
    assert rec.options[0].cost.label == "Estimate"


def test_trace_step_optional_metrics():
    step = TraceStep(name="redact", input="my name is [NAME]", output="ok", used="regex", latency_ms=0.4)
    assert step.tokens is None and step.cost_usd is None
