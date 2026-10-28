"""Pydantic schemas shared across the pipeline."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated, Literal, Optional

from pydantic import BaseModel, Field

Confidence = Literal["high", "medium", "low"]
Probability = Annotated[float, Field(ge=0.0, le=1.0)]


class Outcome(str, Enum):
    CALL_911 = "CALL_911"              # emergency: call 911 now (D-052)
    GO_TO_ER = "GO_TO_ER"              # emergency: go to the ER now, someone else drives (D-052)
    QUESTION = "QUESTION"              # the interviewer asks one question (D-051)
    RECOMMENDATION = "RECOMMENDATION"

    @property
    def is_emergency(self) -> bool:
        return self in (Outcome.CALL_911, Outcome.GO_TO_ER)


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


class Turn(BaseModel):
    """One question asked by the system and the person's answer."""

    topic: str                             # question-bank topic (D-050)
    question: str = ""
    answer: str


class Request(BaseModel):
    text: str
    severity: int = Field(ge=1, le=10)
    zip: str
    plan: str
    request_time: datetime
    age_group: Literal["adult", "child"] = "adult"
    turns: list[Turn] = []                 # the conversation so far (D-041)
    skip: bool = False                     # "Skip, just tell me where to go"
    followup_answer: Optional[str] = None  # shorthand for one answer to the main-symptom question

    def all_turns(self) -> list[Turn]:
        extra = [Turn(topic="main_symptom", answer=self.followup_answer)] if self.followup_answer else []
        return [*self.turns, *extra]


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


class Match(BaseModel):
    """A retrieved practitioner. Everything shown about it comes from the record (D-007)."""

    practitioner: Practitioner
    distance_km: Optional[float]  # None for virtual practitioners
    score: float
    matched_text: str             # the record text that best matches the query


class CostEstimate(BaseModel):
    """Plan copay plus typical total cost, always labeled as an estimate."""

    care_type: str
    copay_usd: Optional[int] = None            # None for self-care, self-pay or an unknown plan
    cash_price_usd: Optional[int] = None       # self-pay only (D-044)
    typical_range_usd: tuple[int, int]
    deductible_usd: Optional[int] = None
    deductible_note: Optional[str] = None      # only when the deductible is high
    deductible_applies: bool = False           # this service counts against the deductible first
    coinsurance_pct: Optional[int] = None      # when coinsurance applies to this service
    waived_if_admitted: bool = False           # ER copay waived if admitted
    label: str = "Estimate"

    def summary(self) -> str:
        low, high = self.typical_range_usd
        parts = [f"{self.label}: "]
        if self.cash_price_usd is not None:
            parts.append(f"${self.cash_price_usd:,} cash price (no insurance); ")
        elif self.copay_usd is not None:
            parts.append(f"${self.copay_usd:,} copay; ")
        parts.append(f"typical total ${low:,}-${high:,} before insurance.")
        if self.deductible_applies:
            extra = f", then {self.coinsurance_pct}% coinsurance" if self.coinsurance_pct else ""
            parts.append(f" The deductible applies to this service first{extra}.")
        if self.waived_if_admitted:
            parts.append(" The ER copay is waived if you are admitted.")
        if self.deductible_note:
            parts.append(f" {self.deductible_note}")
        return "".join(parts)


class Option(BaseModel):
    match: Match
    cost: CostEstimate


class Recommendation(BaseModel):
    decision: CareDecision
    options: list[Option] = []          # top in-network practitioners at the recommended level
    alternatives: list[Option] = []     # telehealth when nothing at the level is available nearby
    explanation: str = ""
    notes: list[str] = []
    nurse_line: Optional[str] = None    # from the plan record


class TraceStep(BaseModel):
    name: str
    input: str
    output: str
    used: str  # model id or rule id
    latency_ms: float
    tokens: Optional[int] = None
    cost_usd: Optional[float] = None


# ------------------------------------------------------------------ conversation (D-051)
class TopicAnswer(BaseModel):
    value: Optional[str]                   # the bank option, None when the answer was unclear
    evidence: str                          # the person's own (redacted) words


class ConversationState(BaseModel):
    """What the interviewer and the rules know so far. Built by code from the conversation."""

    clusters: list[str] = []               # matched guide clusters, best first
    category: str = "general"              # Jev category
    answers: dict[str, TopicAnswer] = {}   # detail and danger topics
    danger_asked: dict[str, Optional[str]] = {}   # danger topics asked -> value
    cause_answers: dict[str, Optional[str]] = {}  # possible-cause questions asked -> value
    questions_asked: int = 0
    first_message: str = ""                # redacted

    def answered(self, topic: str) -> bool:
        return topic in self.answers or topic in self.cause_answers


class InterviewerStep(BaseModel):
    """The interviewer's JSON output: one question, or done."""

    done: bool
    topic: Optional[str] = None
    question: Optional[str] = None
    quick_replies: list[str] = []
    reason: str = ""


# ------------------------------------------------------------------ final answer (D-053)
class ToldBullet(BaseModel):
    text: str
    evidence: str                          # a quote from the conversation


class PossibleCause(BaseModel):
    cause: str
    description: str


class ErOption(BaseModel):
    """A nearby ER from the records; the distance is computed by code."""

    name: str
    address: Optional[str]
    phone: str
    distance_km: float
    hours: str                             # "Open 24/7" or today's hours
    pediatric: bool = False


class FinalAnswer(BaseModel):
    told: list[ToldBullet] = []
    causes: list[PossibleCause] = []       # empty for CALL_911 and mental health
    where: str = ""                        # the level and why
    options: list[str] = []                # closest options, one line each
    cost: list[str] = []                   # labelled as an estimate
    go_sooner: list[str] = []
    safety: list[str] = []
    fallbacks: list[str] = []              # sections the guard replaced with the template
