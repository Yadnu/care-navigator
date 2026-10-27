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
def test_build_request_shape():
    body = build_jev_request("chest feels heavy", [
        {"id": "emergency", "type": "yes_no", "text": "Is this an emergency?"},
        {"id": "category", "type": "choice", "text": "Symptom category?", "options": ["ent", "skin"]},
        {"id": "urgency", "type": "score", "text": "Urgency 1-5?", "min": 1, "max": 5},
    ])
    assert body["state"] == "chest feels heavy"
    assert [q["id"] for q in body["questions"]] == ["emergency", "category", "urgency"]
    assert body["questions"][1]["options"] == ["ent", "skin"]


def test_build_request_rejects_unknown_question_type():
    with pytest.raises(ValueError):
        build_jev_request("x", [{"id": "q", "type": "free_text", "text": "?"}])


def test_parse_response():
    answers = parse_jev_response({"answers": [
        {"id": "emergency", "probabilities": {"yes": 0.8, "no": 0.2}, "confidence": 0.9},
    ]})
    assert answers["emergency"]["probabilities"]["yes"] == 0.8
    assert answers["emergency"]["confidence"] == 0.9


def test_parse_response_rejects_bad_shape():
    with pytest.raises(JevError):
        parse_jev_response({"unexpected": True})


def fake_session(payload=None, status=200, exc=None):
    session = MagicMock(spec=requests.Session)
    if exc:
        session.post.side_effect = exc
    else:
        resp = MagicMock()
        resp.status_code = status
        resp.json.return_value = payload
        session.post.return_value = resp
    return session


def test_http_jev_is_emergency_posts_and_parses():
    session = fake_session({"answers": [
        {"id": "emergency", "probabilities": {"yes": 0.7, "no": 0.3}, "confidence": 0.8}]})
    client = HttpJev(api_key="k", base_url="https://jev.test/v1/ask", session=session)
    prob, conf = client.is_emergency("chest heavy")
    assert (prob, conf) == (0.7, 0.8)
    args, kwargs = session.post.call_args
    assert args[0] == "https://jev.test/v1/ask"
    assert kwargs["headers"]["Authorization"] == "Bearer k"
    assert kwargs["timeout"] == config.JEV_TIMEOUT_S
    assert kwargs["json"]["questions"][0]["type"] == "yes_no"


def test_http_jev_classify_category():
    probs = {c: 0.0 for c in CATEGORIES}
    probs["skin"] = 1.0
    session = fake_session({"answers": [{"id": "category", "probabilities": probs, "confidence": 0.6}]})
    label, got_probs, conf = HttpJev(api_key="k", base_url="https://jev.test", session=session).classify_category("rash")
    assert label == "skin" and got_probs["skin"] == 1.0 and conf == 0.6


def test_http_jev_urgency_score_rounds_into_range():
    session = fake_session({"answers": [{"id": "urgency", "score": 4.6, "confidence": 0.5}]})
    assert HttpJev(api_key="k", base_url="https://jev.test", session=session).urgency_score("x") == (5, 0.5)


def test_http_jev_error_status_raises():
    session = fake_session({"error": "nope"}, status=503)
    with pytest.raises(JevError):
        HttpJev(api_key="k", base_url="https://jev.test", session=session).is_emergency("x")


def test_http_jev_timeout_raises_jev_error():
    session = fake_session(exc=requests.Timeout("slow"))
    with pytest.raises(JevError):
        HttpJev(api_key="k", base_url="https://jev.test", session=session).is_too_vague("x")


def test_get_jev_offline_without_key(monkeypatch):
    monkeypatch.delenv("JEV_API_KEY", raising=False)
    assert isinstance(get_jev(), OfflineJev)


def test_get_jev_http_with_key(monkeypatch):
    monkeypatch.setenv("JEV_API_KEY", "k")
    assert isinstance(get_jev(), HttpJev)
