"""Phase 2: PII redaction (D-009)."""
from __future__ import annotations

import pytest

from navigator.redact import redact


def test_adversarial_pii_case():
    text = "My name is John Smith, phone 555-123-4567, email john@example.com, I have a cough"
    assert redact(text) == "My name is [NAME], phone [PHONE], email [EMAIL], I have a cough"


@pytest.mark.parametrize("text, expected", [
    ("reach me at a.b+tag@mail.example.org please", "reach me at [EMAIL] please"),
    ("JANE_DOE99@Example.COM", "[EMAIL]"),
])
def test_emails(text, expected):
    assert redact(text) == expected


@pytest.mark.parametrize("phone", [
    "555-123-4567", "(555) 123-4567", "555.123.4567", "+1 555 123 4567", "5551234567", "555-0123",
])
def test_phone_formats(phone):
    assert redact(f"call {phone} after 5") == "call [PHONE] after 5"


@pytest.mark.parametrize("text, expected", [
    ("born 03/14/1988", "born [DATE]"),
    ("DOB: 1988-03-14, cough", "DOB: [DATE], cough"),
    ("dob 14-3-88", "dob [DATE]"),
    ("born March 14, 1988", "born [DATE]"),
    ("born 14 March 1988", "born [DATE]"),
    ("born Sept 3rd 1990", "born [DATE]"),
])
def test_dates(text, expected):
    assert redact(text) == expected


@pytest.mark.parametrize("text, expected", [
    ("my name is maria and i have a fever", "my name is [NAME] and i have a fever"),
    ("Hi, my name's Sam. Chest pain", "Hi, my name's [NAME]. Chest pain"),
    ("Name: Ana Lucia Perez - ear pain", "Name: [NAME] - ear pain"),
    ("MY NAME IS LEE, sore throat", "MY NAME IS [NAME], sore throat"),
])
def test_names_after_name_phrases(text, expected):
    assert redact(text) == expected


@pytest.mark.parametrize("text", [
    "Sore throat and fever for two days",
    "My 4 year old has ear pain and a fever of 101 since this morning",
    "Fever 100.5 and sore throat, tonight",
    "bleeding that won't stop after 20 minutes of pressure",
    "Vomiting since 22:30, severity 5, zip 00101",
    "my baby is 2 months old and has a fever of 101",
    "Knee pain from running for 3 weeks, no swelling",
    "Cut my finger cooking, about 1 inch",
])
def test_symptom_text_is_left_alone(text):
    assert redact(text) == text


def test_empty_and_whitespace():
    assert redact("") == ""
    assert redact("   ") == "   "


def test_redaction_is_idempotent():
    once = redact("My name is John Smith, phone 555-123-4567")
    assert redact(once) == once
