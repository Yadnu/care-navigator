"""Phase 3: OfflineParser and ClaudeParser (mocked client only)."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import anthropic
import httpx2
import pytest

from navigator import config
from navigator.parser import (
    SYSTEM_PROMPT,
    TOOL,
    ClaudeParser,
    OfflineParser,
    ParseResult,
    get_parser,
)

EVAL = Path(__file__).resolve().parents[1] / "data" / "eval"


def load_jsonl(name):
    return [json.loads(l) for l in (EVAL / name).read_text(encoding="utf-8").splitlines() if l.strip()]


ROUTING = load_jsonl("routing_cases.jsonl")
VAGUE = load_jsonl("vague.jsonl")
offline = OfflineParser()


# ------------------------------------------------------------ OfflineParser
@pytest.mark.parametrize("text, hours", [
    ("Sore throat and fever for two days", 48),
    ("fever 2 days", 48),
    ("Knee pain from running for 3 weeks", 504),
    ("body aches since yesterday", 24),
    ("Heartburn most nights for a month", 720),
    ("Acne getting worse for months", 2160),
    ("chest pian since an hour", 1),
    ("Runny nose and mild cough for 3 days", 72),
    ("Sinus pressure and stuffy nose for 10 days", 240),
])
def test_duration_extraction(text, hours):
    assert offline.parse(text, severity=4).report.duration_hours == hours


@pytest.mark.parametrize("text", [
    "Vomiting and stomach cramps since dinner, can keep water down",
    "My 4 year old has ear pain and a fever of 101 since this morning",
    "Mild headache since this afternoon",
    "Vomiting and diarrhea since lunch",
    "Fever 100.5 and sore throat, tonight",
])
def test_relative_durations_are_short(text):
    hours = offline.parse(text, severity=4).report.duration_hours
    assert hours is not None and 0 < hours <= 12


@pytest.mark.parametrize("text, area", [
    ("Sore throat and fever for two days", "throat"),
    ("Twisted my ankle playing soccer", "ankle"),
    ("Ear pain for two days, no fever", "ear"),
    ("Vomiting and stomach cramps since dinner", "stomach"),
    ("Burning when I pee for two days", "urinary"),
])
def test_body_area(text, area):
    assert offline.parse(text, severity=4).report.body_area == area


def test_main_symptom_records_what_was_said():
    report = offline.parse("Sore throat and fever for two days", severity=4).report
    assert "sore throat" in report.main_symptom and "fever" in report.main_symptom


def test_severity_is_passed_through():
    assert offline.parse("cough for 2 days", severity=7).report.severity == 7


def test_confidence_high_with_symptom_and_duration():
    report = offline.parse("Sore throat and fever for two days", severity=4).report
    assert report.confidence == "high" and report.missing == []


def test_confidence_medium_without_duration():
    report = offline.parse("Cough and sore throat", severity=4).report
    assert report.confidence == "medium" and report.missing == ["duration"]


@pytest.mark.parametrize("case", VAGUE, ids=[c["id"] for c in VAGUE])
def test_vague_input_is_low_confidence(case):
    report = offline.parse(case["text"], severity=case["severity"]).report
    assert report.confidence == "low"
    assert "main_symptom" in report.missing


@pytest.mark.parametrize("case", ROUTING, ids=[c["id"] for c in ROUTING])
def test_routing_cases_have_a_main_symptom(case):
    report = offline.parse(case["text"], severity=case["severity"]).report
    assert report.main_symptom, case["text"]
    assert report.confidence in {"high", "medium"}


def test_red_flags_recorded_from_text():
    report = offline.parse("chest pain and sweating", severity=7).report
    assert report.red_flags


def test_offline_result_metadata():
    result = offline.parse("cough for 2 days", severity=3)
    assert isinstance(result, ParseResult)
    assert result.used == "offline-parser" and result.fallback is False


@pytest.mark.parametrize("text", ["", "   ", "<script>alert(1)</script> headache", "a" * 5000,
                                  "Me duele la garganta y tengo fiebre desde hace dos días"])
def test_offline_parser_never_crashes(text):
    assert offline.parse(text, severity=3).report


# ------------------------------------------------------------ ClaudeParser (mocked)
GOOD_INPUT = {"main_symptom": "sore throat and fever", "body_area": "throat", "duration_hours": 48,
              "red_flags": [], "missing": [], "confidence": "high"}


def response(tool_input=None, stop_reason="tool_use"):
    content = [] if tool_input is None else [
        SimpleNamespace(type="tool_use", name=TOOL["name"], input=tool_input)]
    return SimpleNamespace(content=content, stop_reason=stop_reason,
                           usage=SimpleNamespace(input_tokens=120, output_tokens=30))


def fake_client(*results):
    client = MagicMock()
    client.messages.create.side_effect = list(results)
    return client


def test_claude_parser_valid_output():
    client = fake_client(response(GOOD_INPUT))
    result = ClaudeParser(client=client).parse("Sore throat and fever for two days", severity=4)
    assert result.report.main_symptom == "sore throat and fever"
    assert result.report.severity == 4
    assert result.used == config.CLAUDE_MODEL and result.fallback is False
    assert result.tokens == 150


def test_claude_parser_request_shape():
    client = fake_client(response(GOOD_INPUT))
    ClaudeParser(client=client).parse("Sore throat", severity=4)
    kwargs = client.messages.create.call_args.kwargs
    assert kwargs["model"] == "claude-haiku-5-5"
    assert kwargs["tool_choice"] == {"type": "tool", "name": TOOL["name"]}
    assert kwargs["tools"][0]["strict"] is True
    assert kwargs["tools"][0]["input_schema"]["additionalProperties"] is False
    assert "temperature" not in kwargs  # Haiku 5.5 rejects non-default sampling params (D-018)
    assert kwargs["messages"][-1]["role"] == "user"
    assert "Sore throat" in kwargs["messages"][-1]["content"]


def test_system_prompt_rules_and_examples():
    assert "Record what the person said. Do not guess a condition." in SYSTEM_PROMPT
    assert "elephant" in SYSTEM_PROMPT        # indirect red-flag example
    assert "I just feel off" in SYSTEM_PROMPT  # vague example
    for banned in ["ibuprofen", "acetaminophen", "antibiotic", "mg"]:
        assert banned not in SYSTEM_PROMPT.lower().split()


def test_claude_parser_retries_once_after_invalid_output():
    bad = {**GOOD_INPUT, "confidence": "certain"}
    client = fake_client(response(bad), response(GOOD_INPUT))
    result = ClaudeParser(client=client).parse("Sore throat", severity=4)
    assert client.messages.create.call_count == 2
    assert result.fallback is False and result.report.confidence == "high"


def test_claude_parser_falls_back_after_two_invalid_outputs():
    client = fake_client(response(None, stop_reason="end_turn"), response({"main_symptom": 3}))
    result = ClaudeParser(client=client).parse("Sore throat and fever for two days", severity=4)
    assert client.messages.create.call_count == 2
    assert result.fallback is True and result.used == "offline-parser"
    assert result.report.duration_hours == 48


def test_claude_parser_refusal_counts_as_invalid():
    client = fake_client(response(None, stop_reason="refusal"), response(GOOD_INPUT))
    assert ClaudeParser(client=client).parse("x", severity=4).fallback is False
    assert client.messages.create.call_count == 2


def test_claude_parser_falls_back_on_api_error():
    req = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    client = fake_client(anthropic.APITimeoutError(request=req))
    result = ClaudeParser(client=client).parse("cough for 2 days", severity=3)
    assert result.fallback is True and result.report.duration_hours == 48
    assert client.messages.create.call_count == 1


def test_get_parser_offline_without_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert isinstance(get_parser(), OfflineParser)


def test_get_parser_claude_with_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    assert isinstance(get_parser(), ClaudeParser)
