"""Phase 3: Jev classifier interface, OfflineJev heuristics and HttpJev with mocked HTTP."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import requests

from navigator import config
from navigator.jev_client import (
    CATEGORIES,
    HttpJev,
    JevError,
    OfflineJev,
    build_jev_request,
    get_jev,
    parse_jev_response,
)
from navigator.redflags import screen_text

EVAL = Path(__file__).resolve().parents[1] / "data" / "eval"


def load_jsonl(name):
    return [json.loads(l) for l in (EVAL / name).read_text(encoding="utf-8").splitlines() if l.strip()]


RED_FLAGS = load_jsonl("red_flags.jsonl")
NEEDS_JEV = [r for r in RED_FLAGS if r["detectable_by"] == "parsed_or_jev"]
ROUTING = load_jsonl("routing_cases.jsonl")
NON_EMERGENCY = [r for r in ROUTING if r["expected_outcome"] != "EMERGENCY"]
VAGUE = load_jsonl("vague.jsonl")
jev = OfflineJev()


# ------------------------------------------------------------ OfflineJev: emergency
@pytest.mark.parametrize("case", NEEDS_JEV, ids=[c["id"] for c in NEEDS_JEV])
def test_offline_jev_flags_indirect_emergencies(case):
    prob, conf = jev.is_emergency(case["text"])
    assert prob >= config.JEV_EMERGENCY_THRESHOLD, case["text"]
    assert 0 <= conf <= 1


@pytest.mark.parametrize("case", NON_EMERGENCY + VAGUE, ids=[c["id"] for c in NON_EMERGENCY + VAGUE])
def test_offline_jev_quiet_on_non_emergencies(case):
    prob, _ = jev.is_emergency(case["text"])
    assert prob < config.JEV_EMERGENCY_THRESHOLD, case["text"]


def test_keyword_screen_plus_jev_catch_every_red_flag():
    missed = [r["id"] for r in RED_FLAGS
              if not screen_text(r["text"]).is_emergency
              and jev.is_emergency(r["text"])[0] < config.JEV_EMERGENCY_THRESHOLD]
    assert missed == []


# ------------------------------------------------------------ OfflineJev: category
@pytest.mark.parametrize("text, label", [
    ("Runny nose and mild cough for 3 days", "respiratory"),
    ("Sore throat and fever for two days", "ent"),
    ("Ear pain for two days, no fever", "ent"),
    ("Vomiting and stomach cramps since dinner", "gastrointestinal"),
    ("Twisted my ankle playing soccer", "musculoskeletal"),
    ("Itchy red rash after using a new detergent", "skin"),
    ("Pink eye, crusty eyes", "eye"),
    ("Burning when I pee for two days", "urinary"),
    ("Dog bite on my hand, small puncture", "wound"),
    ("Toothache, cheek a little swollen", "dental"),
    ("Stressed and can't sleep before exams", "mental_health"),
    ("Need a refill check for my blood pressure, feeling fine", "chronic"),
    ("Sneezing and itchy eyes, happens every spring", "allergy"),
])
def test_classify_category(text, label):
    got, probs, conf = jev.classify_category(text)
    assert got == label, (text, probs)
    assert set(probs) == set(CATEGORIES)
    assert abs(sum(probs.values()) - 1) < 1e-6
    assert 0 <= conf <= 1


@pytest.mark.parametrize("case", ROUTING, ids=[c["id"] for c in ROUTING])
def test_every_routing_case_gets_a_specific_category(case):
    label, _, _ = jev.classify_category(case["text"])
    assert label != "general", case["text"]


def test_off_topic_is_general_with_low_confidence():
    label, _, conf = jev.classify_category("What's the capital of France?")
    assert label == "general"
    assert conf < 0.5


# ------------------------------------------------------------ OfflineJev: urgency
@pytest.mark.parametrize("text", ["Mild headache since this afternoon, took nothing yet",
                                  "Sneezing and itchy eyes, happens every spring",
                                  "Acne getting worse for months"])
def test_low_urgency(text):
    score, conf = jev.urgency_score(text)
    assert 1 <= score <= 2 and 0 <= conf <= 1


@pytest.mark.parametrize("text", ["Flu symptoms, fever 102, body aches since yesterday",
                                  "Cut my finger cooking, about 1 inch, edges open, bleeding stopped",
                                  "Twisted my ankle, swollen, can walk a little"])
def test_higher_urgency(text):
    score, _ = jev.urgency_score(text)
    assert 3 <= score <= 5


# ------------------------------------------------------------ OfflineJev: vague
@pytest.mark.parametrize("case", VAGUE, ids=[c["id"] for c in VAGUE])
def test_vague_cases_are_too_vague(case):
    prob, conf = jev.is_too_vague(case["text"])
    assert prob >= config.JEV_VAGUE_THRESHOLD, case["text"]
    assert 0 <= conf <= 1


@pytest.mark.parametrize("case", ROUTING, ids=[c["id"] for c in ROUTING])
def test_routing_cases_are_specific_enough(case):
    prob, _ = jev.is_too_vague(case["text"])
    assert prob < config.JEV_VAGUE_THRESHOLD, case["text"]


def test_empty_text_is_vague():
    assert jev.is_too_vague("")[0] >= config.JEV_VAGUE_THRESHOLD


# ------------------------------------------------------------ OfflineJev: rerank, guard
def test_rerank_prefers_matching_doc():
    docs = ["Sports injuries, sprains and knee pain.",
            "Treats stomach bugs, dehydration and food-related illness.",
            "Skin rashes and acne."]
    scores = jev.rerank("vomiting stomach cramps food poisoning", docs)
    assert len(scores) == 3
    assert max(range(3), key=lambda i: scores[i]) == 1


def test_rerank_empty_docs():
    assert jev.rerank("anything", []) == []


@pytest.mark.parametrize("text", [
    "You probably have strep throat.",
    "Take ibuprofen every 6 hours.",
    "This sounds like a diagnosis of appendicitis.",
    "Ask for an antibiotic prescription.",
    "Try 500 mg of acetaminophen.",
])
def test_guard_flags_diagnosis_or_medication(text):
    assert jev.mentions_diagnosis_or_medication(text) >= config.GUARD_THRESHOLD


def test_guard_quiet_on_plain_explanation():
    text = ("Urgent care is a good fit because your symptoms need a same-day visit. "
            "Northside Urgent Care is open now and in network. If you get worse, go to the ER. "
            "This is not medical advice.")
    assert jev.mentions_diagnosis_or_medication(text) < config.GUARD_THRESHOLD


# ------------------------------------------------------------ HttpJev (mocked HTTP only)
# Shape from the TypeSafe Jev API reference: POST /v1/systemone (D-023).
QUESTIONS = {
    "emergency": {"type": "noul", "instructions": "Is this an emergency?"},
    "category": {"type": "choice", "instructions": "Symptom category?",
                 "criteria": {"ent": "ear, nose, throat", "skin": ""}},
    "urgency": {"type": "score", "instructions": "How urgent?", "criteria": ["can wait", "today"]},
}


def test_build_request_shape():
    body = build_jev_request("jev-latest", "chest feels heavy", QUESTIONS)
    assert body == {"model": "jev-latest", "state": "chest feels heavy", "questions": QUESTIONS}


def test_build_request_accepts_json_state():
    body = build_jev_request("jev-latest", {"query": "rash"}, {"q": {"type": "noul"}})
    assert body["state"] == {"query": "rash"}


@pytest.mark.parametrize("questions", [
    {},                                                                  # at least one question
    {"q": {"type": "yes_no"}},                                           # unknown type
    {"q": {"type": "choice", "criteria": {}}},                           # choice needs 1..255 options
    {"q": {"type": "choice", "criteria": {f"o{i}": "" for i in range(256)}}},
    {"q": {"type": "score", "criteria": []}},                            # score needs 1..10 levels
    {"q": {"type": "score", "criteria": [str(i) for i in range(11)]}},
    {"q": {"type": "choice", "criteria": ["not", "a", "map"]}},
    {"q": {"type": "score", "criteria": {"not": "a list"}}},
])
def test_build_request_rejects_invalid_questions(questions):
    with pytest.raises(ValueError):
        build_jev_request("jev-latest", "x", questions)


def test_parse_response_returns_answers_by_name():
    answers = parse_jev_response({"model": "jev-1.14.0", "answers": {
        "emergency": {"type": "noul", "noul": 0.8}}, "usage": {"input_tokens": 10, "output_tokens": 1}})
    assert answers["emergency"]["noul"] == 0.8


@pytest.mark.parametrize("payload", [{"unexpected": True}, {"answers": []}, None, "text"])
def test_parse_response_rejects_bad_shape(payload):
    with pytest.raises(JevError):
        parse_jev_response(payload)


def fake_session(payload=None, status=200, exc=None):
    session = MagicMock(spec=requests.Session)
    if exc:
        session.post.side_effect = exc
    else:
        resp = MagicMock()
        resp.status_code = status
        resp.json.return_value = payload
        resp.text = json.dumps(payload)
        session.post.return_value = resp
    return session


def reply(**answers):
    return {"model": "jev-1.14.0", "answers": answers, "usage": {"input_tokens": 12, "output_tokens": 1}}


def http(session):
    return HttpJev(api_key="k", base_url="https://jev.test/v1/systemone", model="jev-latest", session=session)


def test_http_jev_is_emergency_posts_noul_and_parses():
    session = fake_session(reply(emergency={"type": "noul", "noul": 0.9}))
    prob, conf = http(session).is_emergency("chest heavy")
    assert prob == 0.9
    assert conf == pytest.approx(0.8)  # noul has no confidence; |2p - 1| (D-023)
    args, kwargs = session.post.call_args
    assert args[0] == "https://jev.test/v1/systemone"
    assert kwargs["headers"]["Authorization"] == "Bearer k"
    assert kwargs["timeout"] == config.JEV_TIMEOUT_S
    body = kwargs["json"]
    assert body["model"] == "jev-latest" and body["state"] == "chest heavy"
    assert body["questions"]["emergency"]["type"] == "noul"


def test_http_jev_classify_category_sends_every_category_as_a_choice():
    probs = {c: 0.0 for c in CATEGORIES}
    probs["skin"] = 1.0
    session = fake_session(reply(category={"type": "choice", "choice": "skin", "confidence": 0.6,
                                           "probabilities": probs}))
    label, got_probs, conf = http(session).classify_category("rash")
    assert label == "skin" and got_probs["skin"] == 1.0 and conf == 0.6
    criteria = session.post.call_args.kwargs["json"]["questions"]["category"]["criteria"]
    assert set(criteria) == set(CATEGORIES)


def test_http_jev_classify_unknown_choice_becomes_general():
    session = fake_session(reply(category={"type": "choice", "choice": "astrology", "confidence": 0.9,
                                           "probabilities": {"astrology": 0.9}}))
    label, probs, _ = http(session).classify_category("x")
    assert label == "general" and set(probs) == set(CATEGORIES)


@pytest.mark.parametrize("score, expected", [(0.0, 1), (1.4, 2), (2.6, 4), (4.0, 5)])
def test_http_jev_urgency_maps_zero_based_score_to_1_to_5(score, expected):
    session = fake_session(reply(urgency={"type": "score", "score": score, "confidence": 0.5,
                                          "legend": {}, "probabilities": {}}))
    assert http(session).urgency_score("x") == (expected, 0.5)
    criteria = session.post.call_args.kwargs["json"]["questions"]["urgency"]["criteria"]
    assert len(criteria) == 5


def test_http_jev_is_too_vague():
    session = fake_session(reply(vague={"type": "noul", "noul": 0.2}))
    prob, conf = http(session).is_too_vague("cough for 2 days")
    assert prob == 0.2 and conf == pytest.approx(0.6)


def test_http_jev_rerank_one_score_question_per_doc():
    session = fake_session(reply(
        doc0={"type": "score", "score": 0.0, "confidence": 0.9, "legend": {}, "probabilities": {}},
        doc1={"type": "score", "score": 2.0, "confidence": 0.9, "legend": {}, "probabilities": {}},
    ))
    scores = http(session).rerank("stomach bug", ["Sports injuries.", "Stomach bugs and dehydration."])
    assert scores == [0.0, 1.0]
    questions = session.post.call_args.kwargs["json"]["questions"]
    assert set(questions) == {"doc0", "doc1"} and len(questions["doc0"]["criteria"]) == 3


def test_http_jev_rerank_empty_docs_makes_no_call():
    session = fake_session(reply())
    assert http(session).rerank("x", []) == []
    session.post.assert_not_called()


def test_http_jev_guard():
    session = fake_session(reply(guard={"type": "noul", "noul": 0.95}))
    assert http(session).mentions_diagnosis_or_medication("Take this pill") == 0.95


@pytest.mark.parametrize("status", [400, 401, 422, 500, 503])
def test_http_jev_error_status_raises(status):
    session = fake_session({"detail": "nope"}, status=status)
    with pytest.raises(JevError):
        http(session).is_emergency("x")


def test_http_jev_missing_answer_raises():
    session = fake_session(reply(other={"type": "noul", "noul": 0.5}))
    with pytest.raises(JevError):
        http(session).is_emergency("x")


def test_http_jev_timeout_raises_jev_error():
    session = fake_session(exc=requests.Timeout("slow"))
    with pytest.raises(JevError):
        http(session).is_too_vague("x")


def test_http_jev_invalid_json_raises_jev_error():
    session = fake_session(reply())
    session.post.return_value.json.side_effect = ValueError("not json")
    with pytest.raises(JevError):
        http(session).is_emergency("x")


def test_get_jev_offline_without_key():
    assert isinstance(get_jev(), OfflineJev)


def test_get_jev_http_uses_config(monkeypatch):
    monkeypatch.setenv("JEV_API_KEY", "k")
    monkeypatch.setenv("JEV_MODEL", "jev-1.13.0")
    client = get_jev()
    assert isinstance(client, HttpJev)
    assert client.base_url == "https://api.typesafe.ai/v1/systemone"
    assert client.model == "jev-1.13.0"
