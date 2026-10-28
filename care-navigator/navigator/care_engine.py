"""Deterministic care-level rules (D-001, D-003, D-025).

Picks the first matching rule from care_rules.yaml, applies confidence gating, then makes
sure something at the chosen level is open now. Models never choose the level.
"""
from __future__ import annotations

from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Optional

import yaml

from navigator.data import is_open, load_practitioners
from navigator.models import CareDecision, CareLevel, Practitioner, SymptomReport

RULES_PATH = Path(__file__).with_name("care_rules.yaml")

# A missing duration or body area alone doesn't escalate: no rule reads body area, and rules
# that need a duration never match without one (D-025). A missing main symptom does.
NON_MATERIAL_MISSING = {"duration", "body_area"}

LABELS = {
    CareLevel.SELF_CARE: "self-care",
    CareLevel.TELEHEALTH: "telehealth",
    CareLevel.PRIMARY_CARE: "primary care",
    CareLevel.URGENT_CARE: "urgent care",
    CareLevel.ER: "the ER",
}


def _sentence_case(label: str) -> str:
    return label[0].upper() + label[1:]


@lru_cache(maxsize=1)
def load_rules() -> dict:
    return yaml.safe_load(RULES_PATH.read_text(encoding="utf-8"))


def _matches(when: dict, report: SymptomReport, category: str, urgency: int,
             slots: Optional[dict[str, str]] = None, cause_level: Optional[CareLevel] = None) -> bool:
    if when.get("cause_level") and cause_level is None:
        return False
    if "slots_any" in when:
        slots = slots or {}
        if not any(slots.get(slot) in values for slot, values in when["slots_any"].items()):
            return False
    if "category" in when and category not in when["category"]:
        return False
    if urgency < when.get("min_urgency", 1) or urgency > when.get("max_urgency", 5):
        return False
    if report.severity < when.get("min_severity", 1) or report.severity > when.get("max_severity", 10):
        return False
    if "min_duration_hours" in when:
        if report.duration_hours is None or report.duration_hours < when["min_duration_hours"]:
            return False
    if "symptom_any" in when:
        symptom = (report.main_symptom or "").lower()
        if not any(word in symptom for word in when["symptom_any"]):
            return False
    return True


def should_escalate(report: SymptomReport, after_followup: bool) -> bool:
    """Medium confidence escalates unless only non-material fields are missing;
    a main symptom still missing after the one follow-up escalates (D-003, D-025)."""
    material_missing = set(report.missing) - NON_MATERIAL_MISSING
    if report.confidence == "medium" and (not report.missing or material_missing):
        return True
    return after_followup and (report.confidence == "low" or "main_symptom" in report.missing)


class CareEngine:
    def __init__(self, rules: Optional[dict] = None, practitioners: Optional[Iterable[Practitioner]] = None):
        self.rules = rules or load_rules()
        self.practitioners = tuple(load_practitioners() if practitioners is None else practitioners)

    def _rule(self, report: SymptomReport, category: str, urgency: int,
              slots: Optional[dict[str, str]] = None, cause_level: Optional[CareLevel] = None) -> dict:
        for rule in self.rules["rules"]:
            if _matches(rule.get("when") or {}, report, category, urgency, slots, cause_level):
                return rule
        raise LookupError("care_rules.yaml has no catch-all rule")

    def _available(self, level: CareLevel, when: datetime, plan: Optional[str], age_group: str) -> bool:
        if level is CareLevel.SELF_CARE:
            return True
        plan_known = plan is not None and any(plan in p.accepted_plans for p in self.practitioners)
        excluded_ages = "adults" if age_group == "child" else "children"
        return any(
            p.type == level.value
            and is_open(p.hours, when)
            and (not plan_known or plan in p.accepted_plans)
            and p.patient_ages != excluded_ages
            for p in self.practitioners
        )

    def decide(self, report: SymptomReport, category: str, urgency: int, request_time: datetime,
               plan: Optional[str] = None, age_group: str = "adult", after_followup: bool = False,
               slots: Optional[dict[str, str]] = None, uncertain: bool = False,
               cause_level: Optional[CareLevel] = None) -> CareDecision:
        """`uncertain`: questions are used up or skipped with something still unknown; one level more care.
        `cause_level`: the guide's typical level for the best-matching possible cause (D-051)."""
        rule = self._rule(report, category, urgency, slots, cause_level)
        level = cause_level if rule["level"] == "CAUSE" else CareLevel(rule["level"])
        base = level
        notes = [rule["note"]] if rule.get("note") else []

        escalated = uncertain or should_escalate(report, after_followup)
        if escalated:
            level = level.escalate()

        if not self._available(level, request_time, plan, age_group):
            closed = level
            after_hours = CareLevel(rule["after_hours"])
            level = after_hours if level is base else level.escalate()
            while level is not CareLevel.ER and not self._available(level, request_time, plan, age_group):
                level = level.escalate()
            notes.insert(0, f"{_sentence_case(LABELS[closed])} is closed now ({request_time:%H:%M}), "
                            f"so the next open option is {LABELS[level]}.")

        return CareDecision(level=level, rule_id=rule["id"], escalated=escalated,
                            rules_version=str(self.rules["version"]), notes=notes)
