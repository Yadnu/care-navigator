"""Phase 6: explainer (template + Claude) and output guard (D-007)."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import anthropic
import httpx2
import pytest

from navigator import config
from navigator.care_engine import CareEngine
from navigator.costs import estimate
from navigator.explainer import (
    DISCLAIMER,
    ClaudeExplainer,
    TemplateExplainer,
    get_explainer,
    split_sentences,
)
from navigator.guard import check
from navigator.jev_client import JevError, OfflineJev
from navigator.models import CareDecision, Option
from navigator.parser import OfflineParser
from navigator.retrieval.retriever import Retriever

EVAL = Path(__file__).resolve().parents[1] / "data" / "eval"
ROUTING = [json.loads(l) for l in (EVAL / "routing_cases.jsonl").read_text(encoding="utf-8").splitlines()
           if l.strip() and json.loads(l)["expected_outcome"] == "RECOMMENDATION"]
engine, retriever, jev, parser = CareEngine(), Retriever(), OfflineJev(), OfflineParser()
template = TemplateExplainer()


def scenario(case):
    report = parser.parse(case["text"], case["severity"]).report
    when = datetime.fromisoformat(case["request_time"])
    decision = engine.decide(report, jev.classify_category(case["text"])[0], jev.urgency_score(case["text"])[0],
                             when, case["plan"], case["age_group"])
    matches = retriever.search(report, decision.level.value, case["plan"], case["zip"], when,
                               case["age_group"]).matches
    options = [Option(match=m, cost=estimate(m.practitioner.type, case["plan"])) for m in matches]
    return decision, options


def by_id(case_id):
    return next(c for c in ROUTING if c["id"] == case_id)


# ------------------------------------------------------------------ sentences
def test_split_sentences_keeps_abbreviations():
    text = "Go to St. Aldric Children's Hospital. Dr. Marsh is open. This is not medical advice."
    assert len(split_sentences(text)) == 3


# ------------------------------------------------------------------ template explainer
@pytest.mark.parametrize("case", ROUTING, ids=[c["id"] for c in ROUTING])
def test_template_explanations_are_3_to_5_sentences_and_pass_the_guard(case):
    decision, options = scenario(case)
    text = template.explain(decision, options).text
    assert 3 <= len(split_sentences(text)) <= 5, text
    assert text.endswith(DISCLAIMER)
    result = check(text, decision, options, jev)
    assert result.ok, (result.reasons, text)


def test_template_names_the_options_and_cost():
    decision, options = scenario(by_id("RT-001"))
    text = template.explain(decision, options).text
    assert options[0].match.practitioner.facility_name in text
    assert "$75" in text and "estimate" in text.lower()


def test_template_handles_no_options():
    decision = CareDecision(level="URGENT_CARE", rule_id="R-18", escalated=False, rules_version="1.0")
    text = template.explain(decision, []).text
    assert "urgent care" in text.lower() and text.endswith(DISCLAIMER)
    assert check(text, decision, [], jev).ok


def test_template_self_care():
    decision = CareDecision(level="SELF_CARE", rule_id="R-06", escalated=False, rules_version="1.0",
                            notes=["Call your plan's nurse line if symptoms get worse or you are unsure."])
    text = template.explain(decision, []).text
    assert "self-care" in text.lower() and "nurse line" in text and check(text, decision, [], jev).ok


def test_midnight_template_keeps_the_er_escalation_note():
    decision, options = scenario(by_id("RT-002"))
    text = template.explain(decision, options).text
    assert "go to the ER" in text and "telehealth" in text.lower()


# ------------------------------------------------------------------ guard
def test_guard_blocks_wrong_level():
    decision, options = scenario(by_id("RT-001"))  # URGENT_CARE
    text = f"Primary care is the best fit for you. Visit {options[0].match.practitioner.facility_name}. {DISCLAIMER}"
    result = check(text, decision, options, jev)
    assert not result.ok and "level" in " ".join(result.reasons)


def test_guard_allows_conditional_er_and_closed_mentions():
    decision, options = scenario(by_id("RT-002"))  # TELEHEALTH at midnight
    text = ("Urgent care is closed now, so telehealth is the next open option. "
            f"{options[0].match.practitioner.facility_name} can see you by video. "
            f"If you can't keep fluids down, go to the ER. {DISCLAIMER}")
    assert check(text, decision, options, jev).ok


def test_guard_blocks_diagnosis_or_medication():
    decision, options = scenario(by_id("RT-001"))
    text = f"Urgent care is right; you probably have strep throat and need antibiotics. {DISCLAIMER}"
    result = check(text, decision, options, jev)
    assert not result.ok and "diagnosis" in " ".join(result.reasons)


def test_guard_blocks_practitioner_not_retrieved():
    decision, options = scenario(by_id("RT-001"))
    text = f"Urgent care is right. Try Southpoint Pediatrics or Dr. Who's Clinic. {DISCLAIMER}"
    result = check(text, decision, options, jev)
    assert not result.ok and "practitioner" in " ".join(result.reasons)


def test_guard_requires_the_disclaimer_and_the_level():
    decision, options = scenario(by_id("RT-001"))
    assert not check("Urgent care is right.", decision, options, jev).ok
    assert not check(f"See someone soon. {DISCLAIMER}", decision, options, jev).ok


def test_guard_falls_back_to_offline_jev():
    class Down(OfflineJev):
        def mentions_diagnosis_or_medication(self, text):
            raise JevError("down")

    decision, options = scenario(by_id("RT-001"))
    bad = f"Urgent care is right; take ibuprofen. {DISCLAIMER}"
    assert not check(bad, decision, options, Down()).ok


# ------------------------------------------------------------------ Claude explainer (mocked)
def text_response(text):
    return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)], stop_reason="end_turn",
                           usage=SimpleNamespace(input_tokens=300, output_tokens=90))


def fake_client(*results):
    client = MagicMock()
    client.messages.create.side_effect = list(results)
    return client


def test_claude_explainer_returns_text_and_metadata():
    decision, options = scenario(by_id("RT-001"))
    client = fake_client(text_response("Urgent care fits. " + DISCLAIMER))
    result = ClaudeExplainer(client=client).explain(decision, options)
    assert result.text.endswith(DISCLAIMER) and result.used == config.CLAUDE_MODEL and result.tokens == 390


def test_claude_explainer_sees_only_decision_options_and_costs():
    decision, options = scenario(by_id("RT-001"))
    client = fake_client(text_response("x"))
    ClaudeExplainer(client=client).explain(decision, options)
    kwargs = client.messages.create.call_args.kwargs
    payload = json.loads(kwargs["messages"][-1]["content"])
    assert set(payload) == {"decision", "options", "alternatives"}  # D-036: alternatives are retrieved records too
    assert payload["decision"]["level"] == "URGENT_CARE"
    assert payload["options"][0]["facility_name"] == options[0].match.practitioner.facility_name
    assert "Sore throat" not in kwargs["messages"][-1]["content"]  # no raw symptom text
    assert "temperature" not in kwargs
    assert "not medical advice" in kwargs["system"].lower()
    assert "only the notes" in kwargs["system"].lower()  # no invented warning signs


def test_guard_allows_naming_telehealth_only_when_alternatives_are_shown():
    decision = CareDecision(level="URGENT_CARE", rule_id="R-18", escalated=False, rules_version="1.2")
    _, telehealth = scenario(by_id("RT-040"))
    name = telehealth[0].match.practitioner.facility_name
    text = f"Urgent care is the right level. You can start with a telehealth visit at {name}. {DISCLAIMER}"
    assert check(text, decision, [], jev, telehealth).ok
    assert not check(f"Urgent care is the right level. A telehealth visit is fine. {DISCLAIMER}",
                     decision, [], jev).ok


def test_claude_prompt_keeps_internals_out_of_the_text():
    from navigator.explainer import SYSTEM_PROMPT
    assert "rule id" in SYSTEM_PROMPT.lower() and "notes" in SYSTEM_PROMPT.lower()
    assert "general statement" in SYSTEM_PROMPT.lower()  # don't attribute the rule's wording to the person
    decision, options = scenario(by_id("RT-001"))
    client = fake_client(text_response("x"))
    ClaudeExplainer(client=client).explain(decision, options)
    payload = json.loads(client.messages.create.call_args.kwargs["messages"][-1]["content"])
    assert "rule_id" not in payload["decision"]


def test_alternatives_are_explained_and_allowed_by_the_guard():
    decision = CareDecision(level="URGENT_CARE", rule_id="R-18", escalated=False, rules_version="1.1")
    _, telehealth = scenario(by_id("RT-040"))  # evening: telehealth options
    text = template.explain(decision, [], telehealth).text
    assert telehealth[0].match.practitioner.facility_name in text
    assert check(text, decision, [], jev, telehealth).ok
    client = fake_client(text_response("x"))
    ClaudeExplainer(client=client).explain(decision, [], telehealth)
    payload = json.loads(client.messages.create.call_args.kwargs["messages"][-1]["content"])
    assert payload["alternatives"][0]["facility_name"] == telehealth[0].match.practitioner.facility_name


def test_claude_explainer_falls_back_on_api_error():
    decision, options = scenario(by_id("RT-001"))
    req = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    result = ClaudeExplainer(client=fake_client(anthropic.APITimeoutError(request=req))).explain(decision, options)
    assert result.fallback is True and result.text == template.explain(decision, options).text


def test_get_explainer(monkeypatch):
    assert isinstance(get_explainer(), TemplateExplainer)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    assert isinstance(get_explainer(), ClaudeExplainer)


def test_template_uses_cash_wording_for_self_pay():
    case = {**by_id("RT-002"), "plan": "SELF_PAY"}
    decision, options = scenario(case)
    text = template.explain(decision, options).text
    assert "cash price" in text and "copay" not in text and check(text, decision, options, jev).ok
