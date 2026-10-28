"""Orchestrates one turn of a conversation (D-001 .. D-009, D-051 .. D-053).

Each call re-runs the whole conversation (first message + every answer so far):
validate -> redact -> safety screen (Tier 1 on the whole conversation, confirmed guide danger signs,
Jev alone at >= 0.8 with high confidence) -> parse -> Tier 1 on parsed fields -> conversation state
-> interviewer (one question, guarded) -> rules decide -> retrieve -> costs -> explain -> guard ->
final answer -> final guard -> trace. At most config.MAX_QUESTIONS questions; skipping or running out
with a danger-sign topic still unanswered escalates the level by one. Provider failures fall back
offline and set `simplified`.
"""
from __future__ import annotations

from pathlib import Path
from time import perf_counter
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel

from navigator import config, final_answer, lexicon
from navigator.care_engine import LABELS, CareEngine, load_rules as load_care_rules
from navigator.costs import estimate
from navigator.data import load_plans, load_zips
from navigator.explainer import Explainer, TemplateExplainer, get_explainer
from navigator.guard import check, check_final
from navigator.guide import clusters, match_clusters, ranked_causes
from navigator.interviewer import Interviewer, OfflineInterviewer, get_interviewer, pending_danger
from navigator.jev_client import HttpJev, JevClient, JevError, OfflineJev, get_jev
from navigator.models import (
    CareLevel,
    ConversationState,
    FinalAnswer,
    Option,
    Outcome,
    Recommendation,
    Request,
    TopicAnswer,
    TraceStep,
    Turn,
)
from navigator.parser import OfflineParser, Parser, get_parser
from navigator.questions import classify, danger_sign, extract, load_bank, routine_answer
from navigator.redact import redact
from navigator.redflags import emergency_message, normalize, screen_report, screen_text
from navigator.redflags import load_rules as load_red_flag_rules
from navigator.retrieval.embeddings import Embedder, EmbeddingError, get_embedder
from navigator.retrieval.retriever import RetrievalResult, Retriever, build_query
from navigator.trace import Tracer

JEV_EMERGENCY_MESSAGE = "Call 911 or go to the nearest ER."


class NavigatorResult(BaseModel):
    request_id: str
    outcome: Optional[Outcome] = None        # None when the request itself is invalid
    message: str                             # the one line to show first
    resources: list[str] = []                # emergency numbers, crisis line first
    action: Optional[str] = None             # CALL_911 or GO_TO_ER for an emergency (D-052)
    rule_id: Optional[str] = None            # what decided: red_flags category, guide sign, Jev or care rule
    question: Optional[str] = None           # the interviewer's question, if any
    topic: Optional[str] = None              # question-bank topic of that question
    quick_replies: list[str] = []
    questions_asked: int = 0                 # questions in this conversation, including the current one
    asked_topics: list[str] = []
    state: Optional[ConversationState] = None
    recommendation: Optional[Recommendation] = None
    final: Optional[FinalAnswer] = None
    errors: list[str] = []                   # clear messages about the input (zip, plan, text)
    simplified: bool = False                 # a live provider failed and offline answered
    trace: list[TraceStep] = []
    trace_path: Optional[str] = None

    @property
    def is_emergency(self) -> bool:
        return self.outcome is not None and self.outcome.is_emergency


class _Run:
    """Per-request state."""

    def __init__(self, request: Request, simplified: bool):
        self.request = request
        self.id = uuid4().hex[:12]
        self.tracer = Tracer(self.id)
        self.simplified = simplified
        self.errors: list[str] = []
        self.turns: list[Turn] = [t for t in request.all_turns() if t.answer.strip()]
        self.asked: list[str] = [t.topic for t in self.turns]
        self.state = ConversationState()
        self.clean_text = ""


def _jev_name(jev: JevClient) -> str:
    return f"jev:{jev.model}" if isinstance(jev, HttpJev) else type(jev).__name__


class Navigator:
    def __init__(self, jev: Optional[JevClient] = None, parser: Optional[Parser] = None,
                 interviewer: Optional[Interviewer] = None, explainer: Optional[Explainer] = None,
                 embedder: Optional[Embedder] = None, engine: Optional[CareEngine] = None,
                 trace_dir: Path = config.TRACE_DIR, save_traces: bool = True):
        self.jev = jev or OfflineJev()
        self.offline_jev = OfflineJev()
        self.parser = parser or OfflineParser()
        self.interviewer = interviewer or OfflineInterviewer()
        self.explainer = explainer or TemplateExplainer()
        self.template = TemplateExplainer()
        self.engine = engine or CareEngine()
        self.trace_dir = Path(trace_dir)
        self.save_traces = save_traces
        self.plans = {p["id"]: p for p in load_plans()}
        self.zips = {z["zip"] for z in load_zips()}
        towns: dict[str, list[str]] = {}
        for z in load_zips():
            towns.setdefault(z["city"], []).append(z["zip"])
        self.service_area = "; ".join(f"{city} {min(zs)} to {max(zs)}" for city, zs in towns.items())
        self.index_simplified = False
        try:
            self.retriever = Retriever(embedder=embedder, jev=self.jev)
        except EmbeddingError:
            self.retriever, self.index_simplified = Retriever(jev=self.jev), True
        self._offline_retriever: Optional[Retriever] = None

    @classmethod
    def from_env(cls, **kwargs) -> "Navigator":
        """Live providers for every key that is set; offline for the rest."""
        return cls(jev=get_jev(), parser=get_parser(), interviewer=get_interviewer(), explainer=get_explainer(),
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

    def _search(self, run: _Run, query: str, level: str) -> tuple[RetrievalResult, str]:
        """Search with the main index; on an embedding failure use the offline one. Returns (result, used)."""
        r = run.request
        args = dict(care_type=level, plan=r.plan, zip_code=r.zip, when=r.request_time, age_group=r.age_group)
        used = f"{self.retriever.embedder.name} + bm25 + rrf"
        if self.index_simplified:
            used += " (fallback: index embedding failed)"
        try:
            result = self.retriever.search_text(query, **args)
        except EmbeddingError as e:
            if self._offline_retriever is None:
                self._offline_retriever = Retriever(jev=self.jev)
            result, run.simplified = self._offline_retriever.search_text(query, **args), True
            used = f"{self._offline_retriever.embedder.name} + bm25 + rrf (fallback: {e})"
        if result.candidates and not result.reranked:
            run.simplified = True
            used += " (rerank fallback: fused order)"
        if r.age_group == "child":  # pediatric options first for a child
            result.matches.sort(key=lambda m: m.practitioner.patient_ages != "children")
        return result, used

    def _options(self, result: RetrievalResult, plan: str) -> list[Option]:
        return [Option(match=m, cost=estimate(m.practitioner.type, plan)) for m in result.matches]

    def _finish(self, run: _Run, **fields) -> NavigatorResult:
        fields.setdefault("questions_asked", len(run.asked))
        fields.setdefault("asked_topics", list(run.asked))
        fields.setdefault("state", run.state)
        result = NavigatorResult(request_id=run.id, errors=run.errors, simplified=run.simplified,
                                 trace=run.tracer.steps, **fields)
        if self.save_traces:
            rec = result.recommendation
            r = run.request
            summary = {
                "outcome": result.outcome.value if result.outcome else None,
                "level": rec.decision.level.value if rec else None,
                "rule_id": result.rule_id,
                "simplified": result.simplified,
                "errors": result.errors,
                "request": {"severity": r.severity, "zip": r.zip, "plan": r.plan,
                            "request_time": r.request_time.isoformat(), "age_group": r.age_group,
                            "answers": len(run.turns), "skip": r.skip},
                "asked_topics": result.asked_topics,
                "clusters": run.state.clusters,
            }
            result.trace_path = str(run.tracer.save(self.trace_dir, summary))
        return result

    def _causes(self, run: _Run) -> list[dict]:
        hinted: dict[str, int] = {}
        bank = load_bank()
        for topic, value in run.state.cause_answers.items():
            entry = bank.get(topic, {})
            if entry.get("cause") and value == entry.get("cause_on"):
                hinted[entry["cause"]] = hinted.get(entry["cause"], 0) + 1
        return ranked_causes(run.state.clusters, run.clean_text, hinted)

    def _final(self, run: _Run, outcome: Outcome, where: str, **kwargs) -> FinalAnswer:
        """Build the final answer, then guard it section by section (D-053)."""
        r = run.request
        ranked = self._causes(run)
        with run.tracer.step("final_answer", input=f"outcome={outcome.value} clusters={run.state.clusters}",
                             used="final_answer (code-filled slots)") as s:
            final = final_answer.build(outcome, run.state, plan=self.plans.get(r.plan), zip_code=r.zip,
                                       age_group=r.age_group, when=r.request_time, where=where,
                                       ranked_causes=ranked, **kwargs)
            allowed = [c["cause"] for cid in run.state.clusters for c in clusters()[cid]["possible_causes"]]
            failed = check_final(final, run.clean_text, allowed)
            if "told" in failed:
                final.told = final_answer.told_template(run.state)
            if "causes" in failed:
                final.causes = []
            for name in failed.keys() - {"told", "causes"}:
                setattr(final, name, [] if name != "where" else "")
            final.fallbacks = [f"{k}: {'; '.join(v)}" for k, v in failed.items()]
            s.output = "ok" if not failed else "template for " + " | ".join(final.fallbacks)
        return final

    def _emergency(self, run: _Run, action: str, message: str, resources: list[str], rule_id: str,
                   why: Optional[str] = None) -> NavigatorResult:
        outcome = Outcome(action)
        crisis = bool(resources) and resources[0] == "988"
        where = ("Call 911 now." if outcome is Outcome.CALL_911 else "Go to the nearest ER now.") + \
            (f" {why}" if why else "")
        final = self._final(run, outcome, where, crisis=crisis)
        return self._finish(run, outcome=outcome, message=message, resources=resources, action=action,
                            rule_id=rule_id, final=final)

    def converse(self, request: Request, answers: Optional[dict[str, str]] = None,
                 default: Optional[str] = None) -> NavigatorResult:
        """Run a whole conversation: answer each question from `answers` (by topic), else `default`,
        else the question bank's routine (no-danger) answer. Used by tests, the eval runner and the CLI."""
        turns = list(request.all_turns())
        base = request.model_copy(update={"followup_answer": None})
        result = self.run(base.model_copy(update={"turns": turns}))
        for _ in range(config.MAX_QUESTIONS + 1):  # the pipeline itself stops asking at the limit
            if result.outcome is not Outcome.QUESTION:
                break
            answer = (answers or {}).get(result.topic)
            if answer is None:
                answer = default if default is not None else routine_answer(result.topic)
            turns.append(Turn(topic=result.topic, question=result.question, answer=answer))
            result = self.run(base.model_copy(update={"turns": turns}))
        return result

    # -------------------------------------------------------------- state
    def _state(self, run: _Run, first: str, answers: list[str], category: str) -> ConversationState:
        """Topics from free text (non-danger values only; a danger value counts only as an answer to
        its own question) and from direct answers, each with the person's words as evidence."""
        bank = load_bank()
        main = [a for t, a in zip(run.turns, answers) if t.topic == "main_symptom"]
        state = ConversationState(clusters=match_clusters(" . ".join([first, *main]), category, config.MAX_CLUSTERS),
                                  category=category, first_message=first, questions_asked=len(run.asked))
        for piece in [first, *answers]:
            for topic, value in extract(piece).items():
                if topic not in state.answers and danger_sign(topic, value) is None:
                    state.answers[topic] = TopicAnswer(value=value, evidence=piece)
        for turn, answer in zip(run.turns, answers):
            if turn.topic not in bank:
                continue
            value = classify(turn.topic, answer) if bank[turn.topic]["options"] else None
            if bank[turn.topic]["kind"] == "cause":
                state.cause_answers[turn.topic] = value
                continue
            state.answers[turn.topic] = TopicAnswer(value=value, evidence=answer)
            if bank[turn.topic]["danger"]:
                state.danger_asked[turn.topic] = value
        return state

    # -------------------------------------------------------------- the pipeline
    def run(self, request: Request) -> NavigatorResult:
        run = _Run(request, simplified=self.index_simplified)
        tracer = run.tracer
        text = request.text.strip()
        answers = [t.answer.strip() for t in run.turns]

        # 1. validate
        with tracer.step("validate", input=f"chars={len(text)} severity={request.severity} zip={request.zip} "
                                           f"plan={request.plan} time={request.request_time:%Y-%m-%dT%H:%M} "
                                           f"answers={len(answers)} skip={request.skip}", used="rules") as s:
            fatal = None
            if not text:
                fatal = "Please describe your symptoms in a few words."
            elif len(text) + sum(len(a) for a in answers) > config.MAX_TEXT_CHARS:
                fatal = f"Please keep your description under {config.MAX_TEXT_CHARS:,} characters."
            plan_ok = request.plan in self.plans
            if request.zip not in self.zips:
                run.errors.append(f"Zip code {request.zip} isn't in the service area ({self.service_area}), so only "
                                  "online options can be shown. The care level still applies.")
            if not plan_ok:
                run.errors.append(f"Plan {request.plan} isn't recognised, so in-network options and copays "
                                  "can't be shown. The care level still applies.")
            if fatal:
                run.errors.insert(0, fatal)
            s.output = "; ".join(run.errors) or "ok"
        if fatal:
            return self._finish(run, message=fatal)

        # 2. redact (D-009): nothing below sees the raw text or raw answers
        with tracer.step("redact", input="(raw text is never logged)", used="regex") as s:
            clean_first = redact(text)
            clean_answers = [redact(a) for a in answers]
            clean = ". ".join([clean_first, *clean_answers])
            run.clean_text = clean
            s.output = clean
        run.state = ConversationState(first_message=clean_first, questions_asked=len(run.asked))

        # 3. safety screen, every turn, on the whole conversation: Tier 1 stops at once
        with tracer.step("red_flags", input=clean, used=f"red_flags.yaml v{load_red_flag_rules()['version']}") as s:
            flags = screen_text(clean)
            s.output = ", ".join(f"{h.category}:{h.phrase} ({h.method})" for h in flags.hits) or "none"
        category = self._jev(run, "jev_category", "classify_category", clean)[0]
        run.state = self._state(run, clean_first, clean_answers, category)
        if flags.is_emergency:
            return self._emergency(run, flags.action, flags.message, flags.resources,
                                   "red_flags:" + ",".join(dict.fromkeys(h.category for h in flags.hits)))

        # 4. a guide danger sign the person confirmed (CALL_911 wins) (D-048)
        with tracer.step("danger_signs", input=str(run.state.danger_asked), used="symptom_guide.json") as s:
            confirmed = [sign for topic, value in run.state.danger_asked.items()
                         if (sign := danger_sign(topic, value))]
            s.output = "; ".join(f"{d['action']}: {d['sign']}" for d in confirmed) or "none"
        if confirmed:
            sign = next((d for d in confirmed if d["action"] == "CALL_911"), confirmed[0])
            return self._emergency(run, sign["action"], emergency_message(sign["action"], ["911"]), ["911"],
                                   f"guide:{sign['cluster']}: {sign['sign']}", why=sign["why"])

        # 5. Jev alone: an emergency only when very sure; a middling probability adds caution
        prob, confidence = self._jev(run, "jev_emergency", "is_emergency", clean)
        if prob >= config.JEV_EMERGENCY_THRESHOLD and confidence >= config.JEV_HIGH_CONFIDENCE:
            return self._emergency(run, "CALL_911", JEV_EMERGENCY_MESSAGE, ["911"], f"jev:p={prob:.2f}")
        jev_caution = prob >= config.JEV_SAFETY_THRESHOLD

        # 6. parse, then Tier 1 again on the parsed fields
        # an age answer ("8 months") is not a duration, so the parser doesn't see it
        parse_text = ". ".join([clean_first, *(a for t, a in zip(run.turns, clean_answers) if t.topic != "age")])
        with tracer.step("parse", input=parse_text, used="parser") as s:
            parsed = self.parser.parse(parse_text, request.severity)
            s.output = parsed.report.model_dump_json()
            s.used = parsed.used + (" (fallback)" if parsed.fallback else "")
            s.tokens = parsed.tokens
            run.simplified |= parsed.fallback
        report = parsed.report
        with tracer.step("red_flags_parsed", input=s.output, used="red_flags.yaml") as s2:
            parsed_flags = screen_report(report)
            s2.output = ", ".join(f"{h.category}:{h.phrase}" for h in parsed_flags.hits) or "none"
        if parsed_flags.is_emergency:
            return self._emergency(run, parsed_flags.action, parsed_flags.message, parsed_flags.resources,
                                   "red_flags_parsed:" + ",".join(dict.fromkeys(h.category for h in parsed_flags.hits)))

        # 7. the interviewer picks the next question (guarded); skip or the limit ends the questions
        state = run.state
        vague = not state.clusters and (
            (self._jev(run, "jev_vague", "is_too_vague", clean)[0] >= config.JEV_VAGUE_THRESHOLD
             and not lexicon.is_specific(normalize(clean)))
            or (config.confidence_action(report.confidence) == "ask" and not report.main_symptom))
        if not request.skip and len(run.asked) < config.MAX_QUESTIONS and (state.clusters or vague):
            with tracer.step("interviewer", input=state.model_dump_json(exclude={"first_message"}),
                             used="interviewer") as s:
                asked = self.interviewer.next(state, clean)
                s.used, s.tokens = asked.used, asked.tokens
                s.output = (f"raw={asked.raw} | guard={'; '.join(asked.guard) or 'ok'}"
                            + (" -> template" if asked.fallback else ""))
                run.simplified |= any(g.startswith("invalid output") for g in asked.guard)
            step = asked.step
            if not step.done:
                return self._finish(run, outcome=Outcome.QUESTION, message=step.question, question=step.question,
                                    topic=step.topic, quick_replies=step.quick_replies,
                                    questions_asked=len(run.asked) + 1, asked_topics=[*run.asked, step.topic])

        # 8. rules decide (D-001): the best-matching cause's typical level when a cluster matched;
        #    unanswered danger-sign topics, a skip with something unknown, lingering vagueness or a
        #    middling Jev signal escalate one level
        unanswered = pending_danger(state)
        uncertain = bool(unanswered) or (vague and not state.clusters) or jev_caution
        ranked = self._causes(run)
        cause = ranked[0] if ranked else None
        urgency = self._jev(run, "jev_urgency", "urgency_score", clean)[0]
        slots = {t: a.value for t, a in state.answers.items() if a.value is not None}
        with tracer.step("care_engine", input=f"category={category} urgency={urgency} confidence={report.confidence} "
                                              f"clusters={state.clusters} cause={cause and cause['cause']} "
                                              f"unanswered_danger={unanswered} skip={request.skip} slots={slots}",
                         used="care_rules.yaml") as s:
            decision = self.engine.decide(report, category, urgency, request.request_time,
                                          request.plan if plan_ok else None, request.age_group,
                                          slots=slots, uncertain=uncertain,
                                          cause_level=CareLevel(cause["typical_level"]) if cause else None)
            s.used = f"{decision.rule_id} (care_rules.yaml v{decision.rules_version})"
            s.output = decision.model_dump_json()
        rule = next(r for r in load_care_rules()["rules"] if r["id"] == decision.rule_id)
        if decision.level is CareLevel.ER and rule["level"] == "ER":
            # the rule itself calls for the ER (not merely an after-hours fallback of a lower
            # level): same answer shape as GO_TO_ER (D-052). An after-hours ER stays a normal
            # RECOMMENDATION at level ER so a routine injury isn't shown as an emergency.
            return self._emergency(run, "GO_TO_ER", emergency_message("GO_TO_ER", ["911"]), ["911"],
                                   decision.rule_id, why=f"Because {rule['reason']}.")

        # 9. retrieve practitioners (D-005, D-006); telehealth alternatives when nothing is nearby
        query = build_query(report)
        notes = list(decision.notes)
        with tracer.step("retrieve", input=query, used="retriever") as s:
            found, s.used = self._search(run, query, decision.level.value)
            alternatives = RetrievalResult(matches=[], candidates=0, reranked=False)
            level = decision.level
            if not found.matches and level in (CareLevel.URGENT_CARE, CareLevel.PRIMARY_CARE):
                if request.zip in self.zips:  # an unknown zip is already explained in errors
                    notes.append(f"No in-network {LABELS[level]} is open within {config.MAX_DISTANCE_KM:g} km of "
                                 f"zip {request.zip} right now; online options and your plan's nurse line are below.")
                alternatives, _ = self._search(run, query, CareLevel.TELEHEALTH.value)
            elif not found.matches and level is CareLevel.TELEHEALTH:
                notes.append("No in-network telehealth is open right now; call your plan's nurse line.")
            s.output = (f"candidates={found.candidates} reranked={found.reranked} "
                        f"top={[m.practitioner.id for m in found.matches]} "
                        f"alternatives={[m.practitioner.id for m in alternatives.matches]}")

        # 10. costs (estimates)
        with tracer.step("costs", input=f"plan={request.plan}", used="plans.json + cost_ranges.json") as s:
            options = self._options(found, request.plan)
            alt_options = self._options(alternatives, request.plan)
            s.output = "; ".join(f"{o.match.practitioner.id}: {o.cost.summary()}" for o in options + alt_options)

        # 11. explain, then guard (D-007, D-053)
        allowed = [c["cause"] for cid in state.clusters for c in clusters()[cid]["possible_causes"]]
        with tracer.step("explain", input=f"decision={decision.level.value} options={len(options)}",
                         used="explainer") as s:
            explained = self.explainer.explain(decision, options, alt_options)
            s.output, s.used, s.tokens = explained.text, explained.used, explained.tokens
            run.simplified |= explained.fallback
        with tracer.step("guard", input=explained.text, used="guard") as s:
            verdict = check(explained.text, decision, options, self.jev, alt_options, allowed_causes=allowed)
            s.used = f"guard + {verdict.used}"
            explanation = explained.text
            if not verdict.ok:
                explanation = self.template.explain(decision, options, alt_options).text
                s.output = "blocked: " + "; ".join(verdict.reasons) + " -> template"
            else:
                s.output = "ok"
            run.simplified |= "fallback" in verdict.used

        plan = self.plans.get(request.plan)
        nurse = f"{plan['nurse_line']} ({plan['nurse_line_hours']})" if plan else None
        rec = Recommendation(decision=decision, options=options, alternatives=alt_options, explanation=explanation,
                             notes=notes, nurse_line=nurse)
        final = self._final(run, Outcome.RECOMMENDATION, explanation, options=options, alternatives=alt_options,
                            level=decision.level, nurse_line=nurse)
        label = LABELS[decision.level]
        return self._finish(run, outcome=Outcome.RECOMMENDATION, recommendation=rec, rule_id=decision.rule_id,
                            final=final, message=f"Recommended level of care: {label[0].upper() + label[1:]}.")
