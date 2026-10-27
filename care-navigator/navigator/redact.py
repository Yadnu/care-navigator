"""PII redaction applied before any model call and before tracing (D-009).

Removes emails, phone numbers, dates and names introduced by "my name is" / "name:".
Order matters: emails first (they contain digits), then dates, then phones.
"""
from __future__ import annotations

import re

_MONTH = (r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?")

EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", re.IGNORECASE)
DATE = re.compile(
    r"\b(?:"
    r"\d{4}-\d{1,2}-\d{1,2}"                                   # 1988-03-14
    r"|\d{1,2}[/-]\d{1,2}[/-]\d{2,4}"                          # 03/14/1988, 14-3-88
    rf"|{_MONTH}\s+\d{{1,2}}(?:st|nd|rd|th)?,?\s+\d{{4}}"      # March 14, 1988
    rf"|\d{{1,2}}(?:st|nd|rd|th)?\s+{_MONTH},?\s+\d{{4}}"      # 14 March 1988
    r")\b",
    re.IGNORECASE,
)
PHONE = re.compile(
    r"(?<![\w.])(?:"
    r"(?:\+?1[\s.-]?)?(?:\(\d{3}\)|\d{3})[\s.-]?\d{3}[\s.-]?\d{4}"  # 10 digits, optional +1
    r"|\d{3}[-.]\d{4}"                                                # 555-0123
    r")(?![\w.])"
)
# Up to 3 words after the intro; trailing words that start the rest of the sentence are kept.
NAME = re.compile(
    r"(\b(?:my name is|my name's|name:)\s*)([A-Za-z][A-Za-z'-]*(?: [A-Za-z][A-Za-z'-]*){0,2})",
    re.IGNORECASE,
)
NAME_STOP = {
    "and", "but", "or", "i", "im", "i'm", "with", "have", "has", "had", "am", "is", "was",
    "my", "me", "the", "a", "an", "from", "in", "at", "on", "for", "since", "who", "it",
}


def _redact_name(m: re.Match) -> str:
    words = m.group(2).split(" ")
    name = []
    for word in words:
        if word.lower() in NAME_STOP:
            break
        name.append(word)
    if not name:
        return m.group(0)
    return m.group(1) + "[NAME]" + m.group(2)[len(" ".join(name)):]


def redact(text: str) -> str:
    """Return text with PII replaced by [EMAIL], [DATE], [PHONE] and [NAME]."""
    if not text:
        return text
    text = EMAIL.sub("[EMAIL]", text)
    text = DATE.sub("[DATE]", text)
    text = PHONE.sub("[PHONE]", text)
    return NAME.sub(_redact_name, text)
