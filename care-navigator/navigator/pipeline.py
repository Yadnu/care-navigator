"""Orchestrates one request (D-001 .. D-009).

validate -> redact -> red-flag screen (rules + Jev) -> parse -> recheck -> clarify if needed
-> care engine -> retrieve -> costs -> explain -> guard -> trace.
Any provider failure falls back to the offline implementation and sets `simplified`.
"""
from __future__ import annotations

from pathlib import Path
from time import perf_counter
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel

from navigator import config
from navigator.care_engine import LABELS, CareEngine
from navigator.clarifier import Clarifier, OfflineClarifier, get_clarifier
from navigator.costs import estimate
from navigator.data import load_plans, load_zips
from navigator.explainer import Explainer, TemplateExplainer, get_explainer
from navigator.guard import check
from navigator.jev_client import HttpJev, JevClient, JevError, OfflineJev, get_jev
from navigator.models import (
    CareDecision,
    CareLevel,
    Option,
    Outcome,
    Recommendation,
    Request,
    TraceStep,
)
from navigator.parser import OfflineParser, Parser, get_parser
from navigator.redact import redact
from navigator.redflags import load_rules as load_red_flag_rules
from navigator.redflags import screen_report, screen_text
from navigator.retrieval.embeddings import Embedder, EmbeddingError, get_embedder
from navigator.retrieval.retriever import RetrievalResult, Retriever, build_query
from navigator.trace import Tracer

EMERGENCY_MESSAGE = "Call 911 or go to the nearest ER."


class NavigatorResult(BaseModel):
    request_id: str
    outcome: Optional[Outcome] = None        # None when the request itself is invalid
    message: str                             # the one line to show first
    resources: list[str] = []                # emergency numbers, crisis line first
    question: Optional[str] = None           # the follow-up question, if any
    recommendation: Optional[Recommendation] = None
    errors: list[str] = []                   # clear messages about the input (zip, plan, text)
    simplified: bool = False                 # a live provider failed and offline answered
    trace: list[TraceStep] = []
    trace_path: Optional[str] = None


class _Run:
    """Per-request state."""

    def __init__(self, request: Request, simplified: bool):
        self.request = request
        self.id = uuid4().hex[:12]
        self.tracer = Tracer(self.id)
        self.simplified = simplified
        self.errors: list[str] = []


def _jev_name(jev: JevClient) -> str:
    return f"jev:{jev.model}" if isinstance(jev, HttpJev) else type(jev).__name__


class Navigator:
    def __init__(self, jev: Optional[JevClient] = None, parser: Optional[Parser] = None,
                 clarifier: Optional[Clarifier] = None, explainer: Optional[Explainer] = None,
                 embedder: Optional[Embedder] = None, engine: Optional[CareEngine] = None,
                 trace_dir: Path = config.TRACE_DIR, save_traces: bool = True):
        self.jev = jev or OfflineJev()
        self.offline_jev = OfflineJev()
        self.parser = parser or OfflineParser()
        self.clarifier = clarifier or OfflineClarifier()
        self.explainer = explainer or TemplateExplainer()
        self.template = TemplateExplainer()
        self.engine = engine or CareEngine()
        self.trace_dir = Path(trace_dir)
        self.save_traces = save_traces
        self.plans = {p["id"]: p for p in load_plans()}
        self.zips = {z["zip"] for z in load_zips()}
        self.index_simplified = False
        try:
            self.retriever = Retriever(embedder=embedder, jev=self.jev)
        except EmbeddingError:
            self.retriever, self.index_simplified = Retriever(jev=self.jev), True
        self._offline_retriever: Optional[Retriever] = None

    @classmethod
    def from_env(cls, **kwargs) -> "Navigator":
        """Live providers for every key that is set; offline for the rest."""
        return cls(jev=get_jev(), parser=get_parser(), clarifier=get_clarifier(), explainer=get_explainer(),
                   embedder=get_embedder(), **kwargs)

    @property
    def mode(self) -> str:
        live = [name for name, on in (("Claude", config.claude_enabled()), ("Jev", config.jev_enabled()),
                                      ("Voyage", config.voyage_enabled())) if on]
        return "live: " + ", ".join(live) if live else "offline"

    # -------------------------------------------------------------- helpers
    def _jev(self, run: _Run, step: str, method: str, text: str):
        start = perf_counter()
        try:
            value, used = getattr(self.jev, method)(text), _jev_name(self.jev)
        except JevError as e:
            value, used = getattr(self.offline_jev, method)(text), f"OfflineJev (fallback: {e})"
            run.simplified = True
        run.tracer.add(step, input=text, output=str(value), used=used, latency_ms=(perf_counter() - start) * 1000)
        return value

    def _search(self, run: _Run, query: str, level: str) -> RetrievalResult:
        r = run.request
        args = dict(care_type=level, plan=r.plan, zip_code=r.zip, when=r.request_time, age_group=r.age_group)
        try:
            result = self.retriever.search_text(query, **args)
        except EmbeddingError:
            if self._offline_retriever is None:
                self._offline_retriever = Retriever(jev=self.jev)
            result, run.simplified = self._offline_retriever.search_text(query, **args), True
        if result.candidates and not result.reranked:
            run.simplified = True
        return result

    def _options(self, result: RetrievalResult, plan: str) -> list[Option]:
        return [Option(match=m, cost=estimate(m.practitioner.type, plan)) for m in result.matches]

    def _finish(self, run: _Run, **fields) -> NavigatorResult:
        result = NavigatorResult(request_id=run.id, errors=run.errors, simplified=run.simplified,
                                 trace=run.tracer.steps, **fields)
        if self.save_traces:
            rec = result.recommendation
            r = run.request
            summary = {
                "outcome": result.outcome.value if result.outcome else None,
                "level": rec.decision.level.value if rec else None,
                "rule_id": rec.decision.rule_id if rec else None,
                "simplified": result.simplified,
                "errors": result.errors,
                "request": {"severity": r.severity, "zip": r.zip, "plan": r.plan,
                            "request_time": r.request_time.isoformat(), "age_group": r.age_group,
                            "followup": r.followup_answer is not None},
            }
            result.trace_path = str(run.tracer.save(self.trace_dir, summary))
        return result

    def _emergency(self, run: _Run, message: str, resources: list[str]) -> NavigatorResult:
        return self._finish(run, outcome=Outcome.EMERGENCY, message=message, resources=resources)

    # -------------------------------------------------------------- the pipeline
    def run(self, request: Request) -> NavigatorResult:
        run = _Run(request, simplified=self.index_simplified)
        tracer = run.tracer
        text = request.text.strip()
        answer = (request.followup_answer or "").strip()

        # 1. validate
        with tracer.step("validate", input=f"chars={len(text)} severity={request.severity} zip={request.zip} "
                                           f"plan={request.plan} time={request.request_time:%Y-%m-%dT%H:%M} "
                                           f"followup={bool(answer)}", used="rules") as s:
            fatal = None
            if not text:
                fatal = "Please describe your symptoms in a few words."
            elif len(text) + len(answer) > config.MAX_TEXT_CHARS:
                fatal = f"Please keep your description under {config.MAX_TEXT_CHARS:,} characters."
            plan_ok = request.plan in self.plans
            if request.zip not in self.zips:
                run.errors.append(f"Zip code {request.zip} isn't in the service area (00101 to 00105), so only "
                                  "online options can be shown. The care level still applies.")
            if not plan_ok:
                run.errors.append(f"Plan {request.plan} isn't recognised, so in-network options and copays "
                                  "can't be shown. The care level still applies.")
            if fatal:
                run.errors.insert(0, fatal)
            s.output = "; ".join(run.errors) or "ok"
        if fatal:
            return self._finish(run, message=fatal)

        # 2. redact (D-009): nothing below sees the raw text
        with tracer.step("redact", input="(raw text is never logged)", used="regex") as s:
            clean = redact(f"{text}. {answer}" if answer else text)
            s.output = clean

        # 3. red flags on raw text: rules, then Jev (D-002)
        with tracer.step("red_flags", input=clean, used=f"red_flags.yaml v{load_red_flag_rules()['version']}") as s:
            flags = screen_text(clean)
            s.output = ", ".join(f"{h.category}:{h.phrase} ({h.method})" for h in flags.hits) or "none"
        if flags.is_emergency:
            return self._emergency(run, flags.message, flags.resources)
        if self._jev(run, "jev_emergency", "is_emergency", clean)[0] >= config.JEV_EMERGENCY_THRESHOLD:
            return self._emergency(run, EMERGENCY_MESSAGE, ["911"])

        # 4. parse, then rules again on the parsed fields
        with tracer.step("parse", input=clean, used="parser") as s:
            parsed = self.parser.parse(clean, request.severity)
            s.output = parsed.report.model_dump_json()
            s.used = parsed.used + (" (fallback)" if parsed.fallback else "")
            s.tokens = parsed.tokens
            run.simplified |= parsed.fallback
        report = parsed.report
        with tracer.step("red_flags_parsed", input=s.output, used="red_flags.yaml") as s2:
            parsed_flags = screen_report(report)
            s2.output = ", ".join(f"{h.category}:{h.phrase}" for h in parsed_flags.hits) or "none"
        if parsed_flags.is_emergency:
            return self._emergency(run, parsed_flags.message, parsed_flags.resources)

        # 5. too vague? ask once (D-003)
        vague = self._jev(run, "jev_vague", "is_too_vague", clean)[0] >= config.JEV_VAGUE_THRESHOLD
        if (vague or config.confidence_action(report.confidence) == "ask") and not answer:
            with tracer.step("clarify", input=clean, used="clarifier") as s:
                asked = self.clarifier.question(report, clean)
                s.output, s.used, s.tokens = asked.question, asked.used, asked.tokens
                run.simplified |= asked.fallback
            return self._finish(run, outcome=Outcome.FOLLOW_UP, message=asked.question, question=asked.question)

        # 6. rules decide the level (D-001)
        category = self._jev(run, "jev_category", "classify_category", clean)[0]
        urgency = self._jev(run, "jev_urgency", "urgency_score", clean)[0]
        with tracer.step("care_engine", input=f"category={category} urgency={urgency} "
                                              f"confidence={report.confidence} missing={report.missing}",
                         used="care_rules.yaml") as s:
            decision = self.engine.decide(report, category, urgency, request.request_time,
                                          request.plan if plan_ok else None, request.age_group,
                                          after_followup=bool(answer))
            s.used = f"{decision.rule_id} (care_rules.yaml v{decision.rules_version})"
            s.output = decision.model_dump_json()

        # 7. retrieve practitioners (D-005, D-006); telehealth alternatives when nothing is nearby
        query = build_query(report)
        notes = list(decision.notes)
        with tracer.step("retrieve", input=query, used=f"{self.retriever.embedder.name} + bm25 + rrf") as s:
            found = self._search(run, query, decision.level.value)
            alternatives = RetrievalResult(matches=[], candidates=0, reranked=False)
            level = decision.level
            if not found.matches and level in (CareLevel.URGENT_CARE, CareLevel.PRIMARY_CARE):
                if request.zip in self.zips:  # an unknown zip is already explained in errors
                    notes.append(f"No in-network {LABELS[level]} is open within {config.MAX_DISTANCE_KM:g} km of "
                                 f"zip {request.zip} right now; online options and your plan's nurse line are below.")
                alternatives = self._search(run, query, CareLevel.TELEHEALTH.value)
            elif not found.matches and level is CareLevel.ER:
                notes.append("Go to the nearest ER or call 911.")
            elif not found.matches and level is CareLevel.TELEHEALTH:
                notes.append("No in-network telehealth is open right now; call your plan's nurse line.")
            s.output = (f"candidates={found.candidates} reranked={found.reranked} "
                        f"top={[m.practitioner.id for m in found.matches]} "
                        f"alternatives={[m.practitioner.id for m in alternatives.matches]}")

        # 8. costs (estimates)
        with tracer.step("costs", input=f"plan={request.plan}", used="plans.json + cost_ranges.json") as s:
            options = self._options(found, request.plan)
            alt_options = self._options(alternatives, request.plan)
            s.output = "; ".join(f"{o.match.practitioner.id}: {o.cost.summary()}" for o in options + alt_options)

        # 9. explain, then guard (D-007)
        with tracer.step("explain", input=f"decision={decision.level.value} options={len(options)}",
                         used="explainer") as s:
            explained = self.explainer.explain(decision, options)
            s.output, s.used, s.tokens = explained.text, explained.used, explained.tokens
            run.simplified |= explained.fallback
        with tracer.step("guard", input=explained.text, used="guard") as s:
            verdict = check(explained.text, decision, options, self.jev)
            s.used = f"guard + {verdict.used}"
            explanation = explained.text
            if not verdict.ok:
                explanation = self.template.explain(decision, options).text
                s.output = "blocked: " + "; ".join(verdict.reasons) + " -> template"
            else:
                s.output = "ok"
            run.simplified |= "fallback" in verdict.used

        plan = self.plans.get(request.plan)
        rec = Recommendation(
            decision=decision, options=options, alternatives=alt_options, explanation=explanation, notes=notes,
            nurse_line=f"{plan['nurse_line']} ({plan['nurse_line_hours']})" if plan else None,
        )
        label = LABELS[decision.level]
        return self._finish(run, outcome=Outcome.RECOMMENDATION, recommendation=rec,
                            message=f"Recommended level of care: {label[0].upper() + label[1:]}.")
