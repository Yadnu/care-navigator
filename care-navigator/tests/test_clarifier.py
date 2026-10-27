"""Phase 4: one follow-up question, max 25 words, never a diagnosis or a care level (D-003)."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import anthropic
import httpx2
import pytest

from navigator import config
from navigator.clarifier import (
    TEMPLATES,
    ClaudeClarifier,
    OfflineClarifier,
    get_clarifier,
    is_valid_question,
)
from navigator.models import SymptomReport
from navigator.parser import OfflineParser

EVAL = Path(__file__).resolve().parents[1] / "data" / "eval"
VAGUE = [json.loads(l) for l in (EVAL / "vague.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
offline = OfflineClarifier()


def report(missing, **fields):
    base = dict(main_symptom=None, body_area=None, duration_hours=None, severity=3,
                missing=missing, confidence="low")
    base.update(fields)
    return SymptomReport(**base)


# ------------------------------------------------------------------ validation
@pytest.mark.parametrize("question", [
    "What is bothering you most right now?",
    "How long has this been going on?",
])
def test_valid_questions(question):
    assert is_valid_question(question)


@pytest.mark.parametrize("question", [
    "",
    "Tell me more.",                                                     # not a question
    "How long? Where does it hurt?",                                     # two questions
    "Could you " + "please " * 30 + "describe it?",                      # over 25 words
    "Do you think you should go to urgent care?",                        # names a care level
    "Should you call 911?",
    "Is it a sharp pain like appendicitis?",                             # suggests a diagnosis
    "Have you tried taking ibuprofen?",                                  # medication
    "Would telehealth work for you?",
])
def test_invalid_questions(question):
    assert not is_valid_question(question)


# ------------------------------------------------------------------ offline templates
def test_every_template_is_valid():
    assert TEMPLATES
    for field, question in TEMPLATES.items():
        assert is_valid_question(question), (field, question)


def test_asks_about_the_main_symptom_first():
    q = offline.question(report(["main_symptom", "duration"]), "I just feel off").question
    assert q == TEMPLATES["main_symptom"]


def test_asks_about_duration_when_only_duration_missing():
    r = report(["duration"], main_symptom="cough", confidence="medium")
    assert offline.question(r, "cough").question == TEMPLATES["duration"]


def test_falls_back_to_default_template():
    r = report([], main_symptom="cough", confidence="medium")
    assert offline.question(r, "cough").question == TEMPLATES["default"]


@pytest.mark.parametrize("case", VAGUE, ids=[c["id"] for c in VAGUE])
def test_every_vague_case_gets_one_valid_question(case):
    r = OfflineParser().parse(case["text"], case["severity"]).report
    result = offline.question(r, case["text"])
    assert is_valid_question(result.question)
    assert result.used == "template"


# ------------------------------------------------------------------ Claude (mocked)
def text_response(text):
    return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)], stop_reason="end_turn",
                           usage=SimpleNamespace(input_tokens=80, output_tokens=12))


def fake_client(*results):
    client = MagicMock()
    client.messages.create.side_effect = list(results)
    return client


def test_claude_question_used_when_valid():
    client = fake_client(text_response("  Where in your body do you feel unwell?  "))
    result = ClaudeClarifier(client=client).question(report(["main_symptom"]), "I just feel off")
    assert result.question == "Where in your body do you feel unwell?"
    assert result.used == config.CLAUDE_MODEL and result.fallback is False and result.tokens == 92


def test_claude_request_shape():
    client = fake_client(text_response("What is bothering you most right now?"))
    ClaudeClarifier(client=client).question(report(["main_symptom"]), "I just feel off")
    kwargs = client.messages.create.call_args.kwargs
    assert kwargs["model"] == "claude-haiku-5-5"
    assert "temperature" not in kwargs
    assert "<symptoms>I just feel off</symptoms>" in kwargs["messages"][-1]["content"]
    assert "main_symptom" in kwargs["messages"][-1]["content"]
    system = kwargs["system"].lower()
    assert "one question" in system and "25 words" in system
    assert "diagnosis" in system and "care level" in system


@pytest.mark.parametrize("bad", [
    "Should you go to the ER now?",
    "Is this appendicitis?",
    "What hurts? Since when?",
    "Tell me more",
])
def test_invalid_claude_question_falls_back_to_template(bad):
    client = fake_client(text_response(bad))
    result = ClaudeClarifier(client=client).question(report(["main_symptom"]), "I just feel off")
    assert result.question == TEMPLATES["main_symptom"]
    assert result.fallback is True


def test_claude_refusal_falls_back():
    resp = text_response("")
    resp.stop_reason = "refusal"
    result = ClaudeClarifier(client=fake_client(resp)).question(report(["main_symptom"]), "x")
    assert result.fallback is True and is_valid_question(result.question)


def test_claude_api_error_falls_back():
    req = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    client = fake_client(anthropic.APIConnectionError(request=req))
    result = ClaudeClarifier(client=client).question(report(["duration"], main_symptom="cough"), "cough")
    assert result.question == TEMPLATES["duration"] and result.fallback is True


def test_get_clarifier_offline_without_key():
    assert isinstance(get_clarifier(), OfflineClarifier)


def test_get_clarifier_claude_with_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    assert isinstance(get_clarifier(), ClaudeClarifier)
