"""CHANGE_conversational_triage.md Part 0.3: one action per danger sign across red_flags.yaml and
symptom_guide.json (D-048)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from navigator.questions import danger_action, load_bank
from navigator.redflags import load_rules, screen_text

DATA = Path(__file__).resolve().parents[1] / "data"
GUIDE = json.loads((DATA / "symptom_guide.json").read_text(encoding="utf-8"))
SIGNS = [(c["id"], d["sign"], d["action"]) for c in GUIDE["clusters"] for d in c["danger_signs"]]
ACTIONS = {"CALL_911", "GO_TO_ER"}

# Mismatches found in Part 0.3 and listed for the user's decision. Strict xfail: once a mismatch is
# resolved this test starts passing and pytest fails until the entry is removed from this list.
PENDING_APPROVAL: set[tuple[str, str]] = set()  # all 14 rows approved and applied (D-049)


def _params():
    for cluster, sign, action in SIGNS:
        marks = [pytest.mark.xfail(strict=True, reason="awaiting user OK (change request Part 0.3 item 5)")] \
            if (cluster, sign) in PENDING_APPROVAL else []
        yield pytest.param(cluster, sign, action, marks=marks, id=f"{cluster}: {sign[:40]}")


@pytest.mark.parametrize("cluster, sign, guide_action", list(_params()))
def test_a_sign_in_both_files_has_one_action(cluster, sign, guide_action):
    result = screen_text(sign)
    if result.is_emergency:  # the sign is also a Tier 1 phrase or combination
        assert result.action == guide_action, (sign, result.categories, result.action)


def test_every_tier1_category_has_an_action():
    for category, spec in load_rules()["categories"].items():
        assert spec.get("action") in ACTIONS, category


def test_guide_actions_are_valid():
    assert {a for _, _, a in SIGNS} <= ACTIONS


# ------------------------------------------------------------------ "can't keep fluids down" (item 2)
@pytest.mark.parametrize("text", ["I can't keep fluids down", "can't keep any water down since this morning",
                                  "unable to keep any fluids down for many hours"])
def test_cant_keep_fluids_down_is_go_to_er(text):
    result = screen_text(text)
    assert result.is_emergency and result.action == "GO_TO_ER"


@pytest.mark.parametrize("text", [
    "can't keep fluids down and I'm confused",
    "can't keep any water down and I fainted",
    "can't keep anything down, extremely sleepy",
    "can't keep fluids down and there's blood in the vomit",
    "can't keep water down and vomiting blood",
])
def test_cant_keep_fluids_down_with_a_serious_sign_is_call_911(text):
    assert screen_text(text).action == "CALL_911"


def test_call_911_wins_when_both_actions_hit():
    result = screen_text("can't keep water down and I have chest pain")
    assert {h.category for h in result.hits} >= {"severe_dehydration", "cardiac"}
    assert result.action == "CALL_911"


def test_go_to_er_message_says_go_now_and_call_911_if_worse():
    result = screen_text("I can't keep fluids down")
    assert "ER" in result.message and "911" in result.message and result.message != screen_text("chest pain").message


def test_question_bank_fluids_danger_answer_is_go_to_er():
    assert danger_action("fluids_kept_down") == "GO_TO_ER"
    for topic, entry in load_bank().items():
        if entry["danger"]:
            assert danger_action(topic) in ACTIONS, topic
