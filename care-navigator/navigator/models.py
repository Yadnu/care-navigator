"""Pydantic schemas shared across the pipeline."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated, Literal, Optional

from pydantic import BaseModel, Field

Confidence = Literal["high", "medium", "low"]
Probability = Annotated[float, Field(ge=0.0, le=1.0)]


class Outcome(str, Enum):
    EMERGENCY = "EMERGENCY"
    FOLLOW_UP = "FOLLOW_UP"
    RECOMMENDATION = "RECOMMENDATION"


class CareLevel(str, Enum):
    """Care levels from lowest to highest acuity."""

    SELF_CARE = "SELF_CARE"
    TELEHEALTH = "TELEHEALTH"
    PRIMARY_CARE = "PRIMARY_CARE"
    URGENT_CARE = "URGENT_CARE"
    ER = "ER"

    @property
    def rank(self) -> int:
        return list(CareLevel).index(self)

    def escalate(self) -> CareLevel:
        """One level more care, capped at ER (D-003)."""
        levels = list(CareLevel)
        return levels[min(self.rank + 1, len(levels) - 1)]

    def __lt__(self, other: CareLevel) -> bool:
        return self.rank < other.rank

    def __gt__(self, other: CareLevel) -> bool:
        return self.rank > other.rank

    def __le__(self, other: CareLevel) -> bool:
        return self.rank <= other.rank

    def __ge__(self, other: CareLevel) -> bool:
        return self.rank >= other.rank


class Request(BaseModel):
    text: str
    severity: int = Field(ge=1, le=10)
    zip: str
    plan: str
    request_time: datetime
    age_group: Literal["adult", "child"] = "adult"
    followup_answer: Optional[str] = None


class SymptomReport(BaseModel):
    main_symptom: Optional[str]
    body_area: Optional[str] = None
    duration_hours: Optional[float] = Field(default=None, ge=0)
    severity: int = Field(ge=1, le=10)
    red_flags: list[str] = []
    missing: list[str] = []
    confidence: Confidence


class JevAnswers(BaseModel):
    emergency_prob: Probability
    emergency_confidence: Probability
    category: str
    category_probs: dict[str, float]
    category_confidence: Probability
    urgency: int = Field(ge=1, le=5)
    urgency_confidence: Probability
    vague_prob: Probability
    vague_confidence: Probability


class CareDecision(BaseModel):
    level: CareLevel
    rule_id: str
    escalated: bool
    rules_version: str
    notes: list[str] = []  # rule notes and opening-hours adjustments, shown to the person


class Practitioner(BaseModel):
    id: str
    name: str
    credential: Optional[str]
    facility_name: str
    type: Literal["ER", "URGENT_CARE", "PRIMARY_CARE", "TELEHEALTH", "SPECIALIST"]
    specialties: list[str]
    conditions_treated: list[str]
    languages: list[str]
    patient_ages: Literal["all", "adults", "children"]
    accepting_new: bool
    hours: dict[str, Optional[str]]
    accepted_plans: list[str]
    virtual: bool
    zip: Optional[str]
    address: Optional[str]
    lat: Optional[float]
    lng: Optional[float]
    phone: str
    bio: str
    synthetic: Literal[True]


class Recommendation(BaseModel):
    decision: CareDecision
    practitioners: list[Practitioner] = []
    explanation: str = ""
    notes: list[str] = []


class TraceStep(BaseModel):
    name: str
    input: str
    output: str
    used: str  # model id or rule id
    latency_ms: float
    tokens: Optional[int] = None
    cost_usd: Optional[float] = None
