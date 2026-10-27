# Decision log

Every non-trivial decision goes here. Newest at the bottom. Never edit an accepted entry's decision; supersede it with a new entry.

Template:

```
## D-XXX: <short title>
- Date: YYYY-MM-DD
- Status: accepted | superseded by D-YYY
- Context: why a decision was needed
- Decision: what we chose
- Alternatives considered: what we rejected and why
- Consequences: trade-offs and follow-ups
```

---

## D-001: Rules make every safety and coverage decision
- Date: 2026-10-27
- Status: accepted
- Context: A care navigator that sends someone to the wrong level of care can cause harm. Model output is non-deterministic and hard to test exhaustively.
- Decision: Deterministic, versioned rules (`red_flags.yaml`, `care_rules.yaml`, retrieval hard filters) make every safety and coverage decision. Models never pick the care level.
- Alternatives considered: Letting an LLM choose the level from symptoms (rejected: untestable, can be prompt-injected); hybrid voting between model and rules (rejected: unclear accountability).
- Consequences: Rules are simplified and not clinically validated; coverage of phrasing relies on the classifier and parser feeding the rules good inputs.

## D-002: Defense in depth for red flags
- Date: 2026-10-27
- Status: accepted
- Context: Emergency phrasing varies widely (typos, understatement, indirect wording). Any single detector will miss some.
- Decision: Three independent checks: keyword/fuzzy rules on raw text, the Jev emergency classifier, and rules again on parsed fields. Any one firing routes to EMERGENCY.
- Alternatives considered: Keyword rules only (rejected: misses indirect wording); classifier only (rejected: opaque, unavailable offline).
- Consequences: Higher false-positive rate toward the ER, which is the accepted direction of error (see D-003).

## D-003: Fail toward more care
- Date: 2026-10-27
- Status: accepted
- Context: Uncertainty, missing fields and provider failures are inevitable.
- Decision: Uncertain or missing information escalates one care level. At most one follow-up question per request; after that, escalate instead of asking again.
- Alternatives considered: Asking repeated questions until confident (rejected: poor experience, delays care); defaulting to the ER on any doubt (rejected: over-triage burdens ERs and users).
- Consequences: Some cases land one level higher than needed. Routing evals accept "expected or one higher", never lower.

## D-004: Model roles
- Date: 2026-10-27
- Status: accepted
- Context: Different tasks need different model properties (calibrated classification vs. language understanding/generation).
- Decision: Jev for classification (emergency yes/no, symptom category, urgency score, "too vague?", rerank, output guard). Claude Haiku 5.5 (`claude-haiku-5-5`) for extraction, the follow-up question and the explanation. Claude Sonnet 5.5 (`claude-sonnet-5-5`) only offline as an evaluation judge.
- Alternatives considered: One LLM for everything (rejected: uncalibrated probabilities, higher cost/latency).
- Consequences: Two optional providers to integrate; both sit behind interfaces (D-008).

## D-005: RAG only for practitioner matching
- Date: 2026-10-27
- Status: accepted
- Context: Retrieval over medical content could leak into guidance the system must not give.
- Decision: Retrieval is used only to match practitioners to the parsed symptom report, never to retrieve medical guidance.
- Alternatives considered: RAG over triage guidelines (rejected: out of scope, clinical risk).
- Consequences: The explanation is constrained to the decision and practitioner records (D-007).

## D-006: Retrieval order
- Date: 2026-10-27
- Status: accepted
- Context: Semantic search must never surface an out-of-network, closed or distant practitioner.
- Decision: Metadata hard filters first (care type, plan, distance, open at request time, accepting new patients), then hybrid search (embeddings + BM25 merged with reciprocal rank fusion, k = 60), then rerank.
- Alternatives considered: Search then filter (rejected: top-k may be all filtered out, and filter violations become possible).
- Consequences: Zero filter violations by construction; an empty candidate set is a valid, explicit outcome.

## D-007: Explainer sees only the decision and retrieved records
- Date: 2026-10-27
- Status: accepted
- Context: Generated text could invent practitioners, plans or a different care level.
- Decision: The explainer input is only the `CareDecision`, retrieved practitioners and cost estimates. Names, addresses and plans are copied from records, never generated.
- Alternatives considered: Giving the explainer the raw symptom text (rejected: invites diagnosis and injection).
- Consequences: Explanations are less personalised; the guard (Phase 6) enforces this.

## D-008: Offline-first
- Date: 2026-10-27
- Status: accepted
- Context: The prototype must run and pass every test with zero API keys.
- Decision: Every model sits behind an interface with an offline implementation (`OfflineJev`, `OfflineParser`, `LocalTfidfEmbedder`, `TemplateExplainer`). Real clients switch on via `ANTHROPIC_API_KEY`, `JEV_API_KEY`, `VOYAGE_API_KEY`.
- Alternatives considered: Requiring keys (rejected: hard constraint); recorded fixtures only (rejected: no runnable offline path).
- Consequences: Offline quality bounds what tests can prove; real clients are tested with mocked HTTP only.

## D-009: Redact PII before any model call
- Date: 2026-10-27
- Status: accepted
- Context: Users may type names, emails, phone numbers or dates of birth.
- Decision: Redact names ("my name is X"), emails, phone numbers and dates before any model call. Traces store redacted text only.
- Alternatives considered: Redacting only in traces (rejected: PII would still reach third-party models).
- Consequences: Regex redaction can over-redact (e.g. durations that look like dates); tests cover tricky inputs.

## D-010: Synthetic data with fake zip codes
- Date: 2026-10-27
- Status: accepted
- Context: Real clinics, people or locations could mislead users or raise privacy issues.
- Decision: All data is synthetic and labeled `"synthetic": true`, using clearly fake zip codes `00101` to `00105`.
- Alternatives considered: Real public provider directories (rejected: out of scope, accuracy and licensing).
- Consequences: Retrieval quality on real data is unproven.
