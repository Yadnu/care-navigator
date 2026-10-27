"""Plain-English explanation: TemplateExplainer (offline) and ClaudeExplainer (D-004, D-007).

Input is only the CareDecision, the retrieved options and their costs: never the symptom
text. 3 to 5 sentences: why this level, the options, when to escalate, then the disclaimer.
"""
from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from typing import Any, Optional

import anthropic
from pydantic import BaseModel

from navigator import config
from navigator.care_engine import LABELS, load_rules
from navigator.models import CareDecision, CareLevel, Option

DISCLAIMER = "This is not medical advice."
GENERIC_ESCALATION = "If symptoms get worse or new ones appear, get care sooner, and call 911 in an emergency."


def split_sentences(text: str) -> list[str]:
    """Sentence split that doesn't break on "St." or "Dr."."""
    return [s for s in re.split(r"(?<!\bSt\.)(?<!\bDr\.)(?<=[.!?])\s+", text.strip()) if s]


class ExplainResult(BaseModel):
    text: str
    used: str                  # model id or "template"
    fallback: bool = False
    tokens: Optional[int] = None


class Explainer(ABC):
    @abstractmethod
    def explain(self, decision: CareDecision, options: list[Option],
                alternatives: list[Option] = ()) -> ExplainResult: ...


def _rule(decision: CareDecision) -> dict:
    return next((r for r in load_rules()["rules"] if r["id"] == decision.rule_id), {})


def _closure_note(decision: CareDecision) -> Optional[str]:
    return next((n for n in decision.notes if " is closed now " in n), None)


def _rule_note(decision: CareDecision) -> Optional[str]:
    return next((n for n in decision.notes if " is closed now " not in n), None)


def _place(option: Option) -> str:
    m = option.match
    where = "online" if m.practitioner.virtual else f"{m.distance_km:g} km"
    return f"{m.practitioner.facility_name} ({where})"


def _join(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


class TemplateExplainer(Explainer):
    def explain(self, decision: CareDecision, options: list[Option],
                alternatives: list[Option] = ()) -> ExplainResult:
        level = LABELS[decision.level]
        reason = _rule(decision).get("reason", "of the details you gave")
        why = f"{level[0].upper() + level[1:]} is the recommended level of care because {reason}"
        why += ", moved up one level because some details were unclear." if decision.escalated else "."
        sentences = [why]

        closure = _closure_note(decision)
        if closure:
            sentences.append(closure)

        if options:
            cost = options[0].cost
            low, high = cost.typical_range_usd
            if cost.cash_price_usd is not None:  # self-pay (D-044)
                price = f"the estimated cash price is ${cost.cash_price_usd:,} without insurance"
            elif cost.copay_usd is not None:
                price = (f"the estimated copay is ${cost.copay_usd:,}, with a typical total of ${low:,}-${high:,} "
                         f"before insurance")
            else:
                price = f"a typical total is ${low:,}-${high:,} before insurance (estimate)"
            where = "Options open now" if cost.cash_price_usd is not None else "In-network options open now"
            sentences.append(f"{where}: {_join([_place(o) for o in options])}; {price}.")
        elif decision.level is CareLevel.SELF_CARE:
            sentences.append("No visit is needed right now, and your plan's nurse line can help if you are unsure.")
        elif alternatives:
            sentences.append(f"No in-network {level} is open nearby right now; online options: "
                             f"{_join([_place(o) for o in alternatives])}.")
        else:
            sentences.append(f"No in-network {level} is open nearby right now, so check the other options listed.")

        sentences.append(_rule_note(decision) or GENERIC_ESCALATION)
        sentences.append(DISCLAIMER)
        return ExplainResult(text=" ".join(sentences), used="template")


SYSTEM_PROMPT = """You write a short, plain-English explanation for a care navigation tool.
You get a JSON object with the care decision (already made by rules) and the retrieved options.
Write 3 to 5 sentences: why this level of care, the options (use only the names given), and when to get more care.
- State the decision's level of care exactly as given; never recommend a different level.
- If "options" is empty, say no in-network option at that level is open nearby and name the "alternatives" (online visits).
- You may name another level only to say it is closed, or as "if ..., go to the ER".
- For when to get more care, use only the notes given (or say to get care sooner if things get worse); never list warning signs or symptoms of your own.
- Write to the person directly. Never mention rules, a rule id, notes, JSON or how the decision was made internally.
- "reason" is a general statement about this kind of problem, not a list of the person's symptoms; never say the person has any symptom it mentions.
- Never name a diagnosis, a condition, a medication or a treatment.
- Do not invent practitioners, addresses, phone numbers, plans or prices.
- Copy the costs as given and call them estimates.
- End with exactly: This is not medical advice."""


def _option_payload(o: Option) -> dict:
    return {
        "facility_name": o.match.practitioner.facility_name,
        "name": o.match.practitioner.name,
        "type": o.match.practitioner.type,
        "virtual": o.match.practitioner.virtual,
        "distance_km": o.match.distance_km,
        "copay_usd": o.cost.copay_usd,
        "typical_total_usd": list(o.cost.typical_range_usd),
    }


def explainer_payload(decision: CareDecision, options: list[Option], alternatives: list[Option] = ()) -> dict:
    return {
        "decision": {
            "level": decision.level.value,
            "reason": _rule(decision).get("reason", ""),
            "escalated": decision.escalated,
            "notes": decision.notes,
        },
        "options": [_option_payload(o) for o in options],
        "alternatives": [_option_payload(o) for o in alternatives],
    }


class ClaudeExplainer(Explainer):
    def __init__(self, client: Any = None, model: str = config.CLAUDE_MODEL,
                 fallback: Explainer | None = None):
        self.client = client or anthropic.Anthropic(timeout=config.CLAUDE_TIMEOUT_S, max_retries=1)
        self.model = model
        self.fallback = fallback or TemplateExplainer()

    def explain(self, decision: CareDecision, options: list[Option],
                alternatives: list[Option] = ()) -> ExplainResult:
        tokens = None
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=config.CLAUDE_MAX_TOKENS,
                output_config={"effort": "low"},
                system=SYSTEM_PROMPT,
                messages=[{"role": "user",
                           "content": json.dumps(explainer_payload(decision, options, alternatives))}],
            )
            usage = getattr(response, "usage", None)
            tokens = usage.input_tokens + usage.output_tokens if usage else None
            text = next((b.text for b in response.content if b.type == "text"), "").strip()
            if response.stop_reason != "refusal" and text:
                return ExplainResult(text=text, used=self.model, tokens=tokens)
        except anthropic.APIError:
            pass
        offline = self.fallback.explain(decision, options, alternatives)
        return offline.model_copy(update={"fallback": True, "tokens": tokens})


def get_explainer() -> Explainer:
    return ClaudeExplainer() if config.claude_enabled() else TemplateExplainer()
