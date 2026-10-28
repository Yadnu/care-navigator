"""The final answer, built from slots that code fills (D-053).

Sections: what you told me (each bullet with an evidence quote), what it could be (up to 2 hedged
possible causes from the matched clusters; never for CALL_911 or mental health), where to go and
why, the closest options (2 nearest ERs for an emergency, pediatric first for a child), the cost
under the plan (an estimate), when to go sooner or call 911, and the safety lines.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from navigator import config
from navigator.care_engine import LABELS
from navigator.costs import _ranges
from navigator.data import DAYS, haversine_km, load_practitioners, load_zips
from navigator.guide import clusters
from navigator.models import (CareLevel, ConversationState, ErOption, FinalAnswer, Option, Outcome, PossibleCause,
                              ToldBullet)
from navigator.questions import load_bank

CONFIRM = "A clinician needs to confirm this."
SAFETY = {
    Outcome.CALL_911: "Call 911 now. Do not drive yourself.",
    Outcome.GO_TO_ER: "Go now and have someone else drive. Call 911 if it gets worse.",
}
CRISIS = "Call or text 988 (Suicide & Crisis Lifeline) now, or call 911 if you are in danger."
EST = "Estimate"


# ------------------------------------------------------------------ what you told me
def told_bullets(state: ConversationState, limit: int = 3) -> list[ToldBullet]:
    """The first message, then the answers (danger-sign topics first), each with its own words."""
    bullets = [ToldBullet(text="What's bothering you", evidence=state.first_message)] if state.first_message else []
    bank = load_bank()
    ordered = sorted(state.answers.items(), key=lambda kv: not bank.get(kv[0], {}).get("danger"))
    for topic, answer in ordered:
        if len(bullets) >= limit:
            break
        if topic == "main_symptom" or answer.value is None or answer.evidence == state.first_message:
            continue
        label = next((o["label"] for o in bank[topic]["options"] if o["value"] == answer.value), answer.value)
        bullets.append(ToldBullet(text=f"{bank[topic]['question'].rstrip('?')}: {label}", evidence=answer.evidence))
    return bullets


def told_template(state: ConversationState) -> list[ToldBullet]:
    """Guard fallback: only the first message, quoted."""
    return [ToldBullet(text="What's bothering you", evidence=state.first_message)]


# ------------------------------------------------------------------ closest ERs
def _zip(zip_code: str) -> Optional[dict]:
    return next((z for z in load_zips() if z["zip"] == zip_code), None)


def _hours_today(hours: dict, when: datetime) -> str:
    if all(hours.get(d) == "24h" for d in DAYS):
        return "Open 24/7"
    slot = hours.get(DAYS[when.weekday()])
    return "Closed today" if slot is None else ("Open 24 hours today" if slot == "24h" else f"Today {slot}")


def nearest_ers(zip_code: str, age_group: str, when: datetime, n: int = config.NEAREST_ERS) -> list[ErOption]:
    """The n nearest ERs to the zip by computed distance; for a child a pediatric ER comes first,
    for an adult ERs that only see children are left out."""
    z = _zip(zip_code)
    if z is None:
        return []
    out = []
    for p in load_practitioners():
        if p.type != "ER" or p.lat is None:
            continue
        pediatric = p.patient_ages == "children" or any("pediatric" in s for s in p.specialties)
        if age_group != "child" and p.patient_ages == "children":
            continue
        out.append(ErOption(name=p.facility_name, address=p.address, phone=p.phone,
                            distance_km=round(haversine_km(z["lat"], z["lng"], p.lat, p.lng), 1),
                            hours=_hours_today(p.hours, when), pediatric=pediatric))
    out.sort(key=lambda e: (age_group == "child" and not e.pediatric, e.distance_km))
    return out[:n]


def er_line(e: ErOption) -> str:
    return f"{e.name}, {e.address}, {e.phone}, {e.distance_km:g} km, {e.hours}"


def option_line(o: Option, when: datetime) -> str:
    p, m = o.match.practitioner, o.match
    where = "online" if p.virtual else f"{p.address}, {m.distance_km:g} km"
    return f"{p.facility_name} ({p.name}), {where}, {p.phone}, {_hours_today(p.hours, when)}"


# ------------------------------------------------------------------ cost
def cost_lines(plan: Optional[dict], care_type: str) -> list[str]:
    """What the visit may cost under the plan, from plans.json `services`. Always an estimate."""
    if care_type == CareLevel.SELF_CARE.value:
        return [f"{EST}: no visit cost for self-care at home."]
    low, high = _ranges()[care_type]
    if plan is None:
        return [f"{EST}: plan not recognised; a typical total is ${low:,}-${high:,} before insurance."]
    service = plan["services"][care_type]
    lines = []
    if plan["plan_type"] == "SELF_PAY":
        lines.append(f"{EST}: cash price ${service['copay_usd']:,} (no insurance).")
    else:
        deductible = plan["deductible_usd"]["individual"]
        high_deductible = plan.get("hsa_eligible") or deductible >= config.HIGH_DEDUCTIBLE_USD
        if service["deductible_applies"] and high_deductible:
            lines.append(f"{EST}: you pay the full allowed cost until your deductible is met "
                         f"(${deductible:,} deductible); a typical total is ${low:,}-${high:,}.")
        else:
            lines.append(f"{EST}: ${service['copay_usd']:,} copay; a typical total is ${low:,}-${high:,} before insurance.")
            lines.append("The deductible applies to this service first." if service["deductible_applies"]
                         else "The deductible does not apply to this service.")
        if service["coinsurance_applies"]:
            lines.append(f"After the deductible, you pay {plan['coinsurance_pct']}% coinsurance.")
    if care_type == CareLevel.ER.value:
        if plan.get("er_copay_waived_if_admitted"):
            lines.append("The ER copay is waived if you are admitted.")
        lines.append(f"Your plan's emergency rule: {plan['emergency_rule']}.")
    return lines


# ------------------------------------------------------------------ go sooner if
def go_sooner(state: ConversationState, limit_signs: int = 2) -> list[str]:
    items = [w for cid in state.clusters for w in clusters()[cid]["watch_for"]]
    signs = [d["sign"] for cid in state.clusters for d in clusters()[cid]["danger_signs"] if d["action"] == "CALL_911"]
    items += [f"Call 911 if: {s}" for s in signs[:limit_signs]]
    if not items:
        items = ["symptoms get worse or new ones appear"]
    return list(dict.fromkeys(items))


def causes_section(outcome: Outcome, state: ConversationState, ranked: list[dict]) -> list[PossibleCause]:
    if outcome is Outcome.CALL_911 or "mental_health" in state.clusters:
        return []
    return [PossibleCause(cause=c["cause"], description=c["description"]) for c in ranked]


def build(outcome: Outcome, state: ConversationState, *, plan: Optional[dict], zip_code: str, age_group: str,
          when: datetime, where: str, ranked_causes: list[dict], options: list[Option] = (),
          alternatives: list[Option] = (), level: Optional[CareLevel] = None, nurse_line: Optional[str] = None,
          crisis: bool = False) -> FinalAnswer:
    final = FinalAnswer(told=told_bullets(state), where=where,
                        causes=[] if crisis else causes_section(outcome, state, ranked_causes),
                        go_sooner=go_sooner(state))
    if outcome.is_emergency:
        ers = nearest_ers(zip_code, age_group, when)
        final.options = [er_line(e) for e in ers] or ["Call 911 or go to the nearest ER."]
        final.cost = cost_lines(plan, CareLevel.ER.value)
        final.safety = ([CRISIS] if crisis else []) + [SAFETY[outcome]]
        return final
    shown = list(options) or list(alternatives)
    final.options = [option_line(o, when) for o in shown]
    if not options and level is not CareLevel.SELF_CARE:
        final.options.insert(0, f"No in-network {LABELS[level]} is open nearby right now."
                             + (" Online options are below." if alternatives else ""))
        if nurse_line:
            final.options.append(f"Your plan's nurse line: {nurse_line}")
    care_type = (alternatives[0].match.practitioner.type if not options and alternatives else level.value)
    final.cost = cost_lines(plan, care_type)
    final.safety = ["If it gets worse or you feel faint, call 911."]
    if nurse_line:
        final.safety.append(f"Questions? Your plan's nurse line: {nurse_line}")
    return final


def render(final: FinalAnswer) -> str:
    """Plain text for the CLI and the guard."""
    out = ["What you told me:"] + [f"- {b.text} (\"{b.evidence}\")" for b in final.told]
    if final.causes:
        out.append("What it could be:")
        out += [f"- One common possibility is {c.cause}: {c.description}" for c in final.causes]
        out.append(CONFIRM)
    out += ["Where to go and why:", final.where, "Closest options:"] + [f"- {o}" for o in final.options]
    out += ["What it may cost with your plan:"] + [f"- {c}" for c in final.cost]
    out += ["Go sooner or call 911 if:"] + [f"- {g}" for g in final.go_sooner]
    out += final.safety
    return "\n".join(out)
