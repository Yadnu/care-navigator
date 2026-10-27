"""Phase 7: Streamlit app smoke tests with streamlit.testing (offline)."""
from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parents[1] / "app.py")


def all_text(at: AppTest) -> str:
    parts = []
    for kind in ("markdown", "info", "warning", "error", "success", "caption", "subheader", "header", "text"):
        parts += [getattr(el, "value", "") or "" for el in getattr(at, kind)]
    return "\n".join(str(p) for p in parts)


def submit(text, severity=4, zip_choice="00101", plan="PLAN_SILVER_HMO", when="Weekday 14:00 (Tue 3 Nov 2026)"):
    at = AppTest.from_file(APP, default_timeout=60).run()
    at.text_area(key="symptoms").input(text)
    at.slider(key="severity").set_value(severity)
    at.selectbox(key="zip").set_value(zip_choice)
    at.selectbox(key="plan").set_value(plan)
    at.selectbox(key="when").set_value(when)
    at.button(key="submit").click()
    return at.run()


def test_app_loads_with_offline_banner_and_disclaimer():
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert not at.exception
    text = all_text(at)
    assert "offline" in text.lower()
    assert "synthetic data" in text.lower() and "not medical advice" in text.lower()


def test_time_defaults_to_now():
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert at.selectbox(key="when").value == "Now"


def test_recommendation_with_practitioners_costs_and_trace():
    at = submit("Sore throat and fever for two days")
    assert not at.exception
    text = all_text(at)
    assert "Urgent care" in text and "Downtown QuickCare" in text and "$75" in text
    assert "This is not medical advice." in text
    assert any("Trace" in e.label for e in at.expander)
    assert "care_engine" in text and "retrieve" in text  # trace viewer lists every step


def test_emergency_is_shown_prominently():
    at = submit("Mild chest tightness, probably nothing", severity=2)
    assert any("Call 911" in e.value for e in at.error)


def test_follow_up_question_then_answer():
    at = submit("I just feel off", severity=3)
    assert at.text_input(key="followup_answer") is not None
    at.text_input(key="followup_answer").input("sore throat and fever for two days")
    at.button(key="submit_followup").click()
    at.run()
    assert not at.exception
    assert "Urgent care" in all_text(at)


def test_safety_check_quick_replies_history_and_skip():
    at = submit("my arm hurts", severity=3)
    assert not at.exception
    assert any("chest pain or pressure" in i.value for i in at.info)    # question from the bank
    assert [b.label for b in at.button if b.key and b.key.startswith("reply_")] == ["No", "Yes"]
    at.button(key="reply_0").click()                                     # answer "No"
    at.run()
    assert not at.exception
    assert "You: No" in all_text(at)                                     # conversation history
    at.button(key="skip").click()                                        # "Skip, just tell me where to go"
    at.run()
    text = all_text(at)
    assert "Recommended level of care" in text and "moved up one level" in text


def test_midnight_override():
    at = submit("Vomiting and stomach cramps since dinner, can keep water down", severity=5,
                when="Midnight 00:15 (Wed 4 Nov 2026)")
    text = all_text(at)
    assert "Telehealth" in text and "NightOwl Virtual Care" in text and "go to the ER" in text


def test_coverage_gap_and_invalid_zip_messages():
    gap = submit("Cough and sore throat", severity=3, zip_choice="00105", plan="PLAN_BRONZE_LOCAL")
    assert "No in-network urgent care" in all_text(gap)
    at = AppTest.from_file(APP, default_timeout=60).run()
    at.text_area(key="symptoms").input("Sore throat and fever for two days")
    at.selectbox(key="zip").set_value("Other")
    at.run()
    at.text_input(key="zip_other").input("99999")
    at.selectbox(key="when").set_value("Weekday 14:00 (Tue 3 Nov 2026)")
    at.button(key="submit").click()
    at.run()
    assert "99999" in all_text(at)


@pytest.mark.parametrize("text", ["", "<script>alert(1)</script> headache"])
def test_bad_input_does_not_crash(text):
    at = submit(text)
    assert not at.exception
