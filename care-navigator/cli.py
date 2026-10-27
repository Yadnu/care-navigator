"""Run the six demo cases and print the results.

    python cli.py              # live providers for any key in .env, offline for the rest
    python cli.py --offline    # ignore .env, run fully offline
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Optional

from navigator import config
from navigator.care_engine import LABELS
from navigator.models import CareLevel, Outcome, Request
from navigator.pipeline import Navigator, NavigatorResult

WEEKDAY_2PM = datetime(2026, 11, 3, 14, 0)   # Tue: everything open
MIDNIGHT = datetime(2026, 11, 4, 0, 15)      # Wed: only ER and 24/7 telehealth open


@dataclass
class DemoCase:
    key: str
    title: str
    request: Request
    expect: str
    check: Callable[[NavigatorResult], bool]


def _level(result: NavigatorResult) -> Optional[CareLevel]:
    return result.recommendation.decision.level if result.recommendation else None


def _req(text: str, severity: int, zip_code: str = "00101", plan: str = "PLAN_SILVER_HMO",
         when: datetime = WEEKDAY_2PM) -> Request:
    return Request(text=text, severity=severity, zip=zip_code, plan=plan, request_time=when)


DEMO_CASES = [
    DemoCase("representative", "1. Representative: sore throat and fever, 14:00",
             _req("Sore throat and fever for two days", 4),
             "Urgent care, nearby in-network options with costs",
             lambda r: _level(r) is CareLevel.URGENT_CARE and bool(r.recommendation.options)),
    DemoCase("midnight", "2. Midnight food poisoning, 00:15",
             _req("Vomiting and stomach cramps since dinner, can keep water down", 5, when=MIDNIGHT),
             "Telehealth (urgent care closed), with 'go to the ER if you can't keep fluids down'",
             lambda r: _level(r) is CareLevel.TELEHEALTH
             and any("go to the ER" in n for n in r.recommendation.notes)),
    DemoCase("chest", "3. Difficult: understated chest tightness",
             _req("Mild chest tightness, probably nothing", 2),
             "EMERGENCY",
             lambda r: r.outcome is Outcome.EMERGENCY),
    DemoCase("vague", "4. Difficult: too vague",
             _req("I just feel off", 3),
             "One follow-up question",
             lambda r: r.outcome is Outcome.FOLLOW_UP and bool(r.question)),
    DemoCase("gap", "5. Difficult: Bronze plan in 00105 needs urgent care (coverage gap)",
             _req("Cough and sore throat", 3, zip_code="00105", plan="PLAN_BRONZE_LOCAL"),
             "'No in-network option nearby' plus telehealth and the nurse line",
             lambda r: _level(r) is CareLevel.URGENT_CARE and not r.recommendation.options
             and bool(r.recommendation.alternatives) and bool(r.recommendation.nurse_line)),
    DemoCase("bad_zip", "6. Difficult: invalid zip code",
             _req("Sore throat and fever for two days", 4, zip_code="99999"),
             "Clear zip message, care level still given",
             lambda r: bool(r.errors) and _level(r) is CareLevel.URGENT_CARE),
]


def run_demo(nav: Navigator) -> list[tuple[DemoCase, NavigatorResult]]:
    return [(case, nav.run(case.request)) for case in DEMO_CASES]


def _option_lines(label: str, options) -> list[str]:
    lines = []
    for o in options:
        p, m = o.match.practitioner, o.match
        where = "online" if p.virtual else f"{m.distance_km:g} km, {p.address}"
        who = p.facility_name if p.name == p.facility_name else f"{p.facility_name} - {p.name}"
        lines.append(f"  {label}: {who} ({where}; {p.phone})")
        lines.append(f"      matched: {m.matched_text}")
        lines.append(f"      cost: {o.cost.summary()}")
    return lines


def format_result(case: DemoCase, result: NavigatorResult) -> str:
    r = case.request
    lines = [f"{case.title}",
             f"  input: \"{r.text}\" | severity {r.severity} | zip {r.zip} | {r.plan} | {r.request_time:%a %H:%M}",
             f"  expected: {case.expect}",
             f"  outcome: {result.outcome.value if result.outcome else 'INVALID'} - {result.message}"]
    lines += [f"  error: {e}" for e in result.errors]
    if result.outcome is Outcome.EMERGENCY:
        lines.append(f"  resources: {', '.join(result.resources)}")
    rec = result.recommendation
    if rec:
        d = rec.decision
        label = LABELS[d.level]
        lines.append(f"  level: {label[0].upper() + label[1:]} (rule {d.rule_id}, rules v{d.rules_version}"
                     f"{', escalated' if d.escalated else ''})")
        lines += _option_lines("option", rec.options)
        lines += _option_lines("alternative", rec.alternatives)
        lines += [f"  note: {n}" for n in rec.notes]
        if rec.nurse_line:
            lines.append(f"  nurse line: {rec.nurse_line}")
        lines.append(f"  explanation: {rec.explanation}")
    if result.simplified:
        lines.append("  (simplified answer: a live provider failed and the offline version answered)")
    lines.append(f"  check: {'as expected' if case.check(result) else 'NOT as expected'}"
                 + (f" | trace: {result.trace_path}" if result.trace_path else ""))
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Care Navigator demo cases.")
    parser.add_argument("--offline", action="store_true", help="ignore .env and run fully offline")
    parser.add_argument("--no-traces", action="store_true", help="don't write trace files")
    args = parser.parse_args(argv)

    if not args.offline:
        config.load_env_file()
    nav = Navigator() if args.offline else Navigator.from_env()
    nav.save_traces = not args.no_traces

    print(f"Care Navigator demo | mode: {nav.mode if not args.offline else 'offline'}")
    print("Synthetic data only. Not medical advice.\n")
    results = run_demo(nav)
    for case, result in results:
        print(format_result(case, result))
        print()
    ok = sum(case.check(result) for case, result in results)
    print(f"{ok}/{len(results)} demo cases as expected")
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
