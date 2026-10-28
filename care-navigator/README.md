# Care Navigator

A person describes their symptoms in plain words, with a severity (1 to 10), a zip code, an insurance plan and the time of the request. Care Navigator returns one of three outcomes:

1. **CALL_911 / GO_TO_ER**: an unmistakable emergency, or a confirmed danger sign from the symptom guide (988 first for crisis wording). The request stops here.
2. **A short conversation**: an interviewer (Claude, or question-bank templates offline) asks one question at a time — danger signs for the matched symptom cluster first, then the most useful details, then one possible-cause question — with quick-reply buttons, at most 6 questions (typically 3 to 5), and a "Skip, just tell me where to go" button.
3. **Recommendation**: a level of care (ER, urgent care, primary care, telehealth, or self-care with the plan's nurse line), the top in-network practitioners that are open and nearby, a cost estimate, up to two hedged possible causes from the matched cluster, and a short plain-English explanation.

**Core principle: rules decide, Jev classifies, Claude reads and writes, RAG finds practitioners, and every step is traced.**

- Safety and coverage decisions are made by deterministic, versioned, tested rules. Models never choose the care level.
- When anything is uncertain or a provider fails, the system routes toward more care, never less, and falls back to an offline implementation.
- It never diagnoses and never mentions medications. All data is synthetic.

> Prototype for a take-home exercise. Synthetic data only; routing rules are simplified and not clinically validated. Not medical advice.

---

## Setup and run

Python 3.11+ (developed on 3.14). Runs with **zero API keys**.

```bash
cd care-navigator
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

make data    # regenerate the synthetic data (deterministic, seed 20261027)
make guide   # rebuild data/symptom_guide.json from data/build_symptom_guide.py
make test    # pytest: 1,198 tests, offline, no network
make eval    # metrics vs pass bars
make demo    # the 6 demo cases
make app     # Streamlit UI with the trace viewer
```

No `make` (for example on Windows)? Each target is one command:

| Target | Command |
|---|---|
| `make data` | `python data/generate.py` |
| `make test` | `python -m pytest` |
| `make eval` | `python scripts/run_eval.py` (add `--offline` to ignore `.env`) |
| `make demo` | `python cli.py` (add `--offline`, `--no-traces`) |
| `make app` | `python -m streamlit run app.py` |

`cli.py` and `run_eval.py` exit non-zero if a demo case or a pass bar fails.

### Dependencies

`pydantic`, `pyyaml`, `rapidfuzz`, `rank-bm25`, `scikit-learn`, `numpy`, `streamlit`, `anthropic`, `requests`, `pytest` (see `requirements.txt`).

### Optional environment variables

Copy `.env.example` to `.env` and fill in only what you want to switch on. Blank keys stay offline. Real environment variables override `.env`; the test suite never reads it.

| Variable | Enables | Default when blank |
|---|---|---|
| `ANTHROPIC_API_KEY` | Claude Haiku 5.5 (`claude-haiku-5-5`) for extraction, the follow-up question and the explanation | regex parser, question templates, template explanation |
| `JEV_API_KEY` | TypeSafe Jev classifier: emergency check, symptom category, urgency, "too vague?", rerank, output guard | `OfflineJev` keyword heuristics |
| `JEV_BASE_URL`, `JEV_MODEL` | Jev endpoint and model | `https://api.typesafe.ai/v1/systemone`, `jev-latest` |
| `VOYAGE_API_KEY` | Voyage embeddings for practitioner search | character n-gram TF-IDF |
| `VOYAGE_MODEL` | Voyage model | `voyage-4` |

The app banner and the CLI header show which providers are live. If a live provider fails or times out, the answer comes from the offline version and is marked **simplified**.

---

## How it works

```
validate -> redact PII -> safety screen (red flags on the whole conversation, confirmed guide
  danger signs, Jev alone only at >= 0.8 with high confidence) -> parse (Claude or regex)
  -> red flags again on parsed fields -> conversation state (matched symptom clusters)
  -> interviewer: one guarded question (danger signs first, then details, then a cause question)
  -> care rules pick the level (or the matched cluster's best-cause typical level) -> is anything
  open now? (else after-hours level) -> retrieve: hard filters -> embeddings + BM25 -> RRF (k=60)
  -> Jev rerank -> top 3 -> cost estimates -> explanation (Claude or template) -> output guard
  -> final answer (what you told me / possible causes / where / options / cost / go-sooner) with
  its own guard -> trace (JSON per request)
```

| Piece | Where | Notes |
|---|---|---|
| Red flags | `navigator/red_flags.yaml`, `redflags.py` | 15 categories; exact phrases, then RapidFuzz typo matching (ratio >= 88, short words must match exactly); runs on raw text and again on parsed fields; Jev is a third, independent check |
| Symptom guide | `data/symptom_guide.json`, `guide.py`, `data/build_symptom_guide.py` | 13 clusters: match terms, danger signs (one action each, reconciled with `red_flags.yaml`, D-048/D-049), hedged possible causes with a typical level, watch-for items |
| Question bank | `data/question_bank.json`, `questions.py` | rebuilt from the guide's `ask_about`/possible-cause topics; `classify`/`extract` map answers and free text to options, negation-aware |
| Interviewer | `interviewer.py` | one question per turn (danger signs for the matched clusters first, then details, then one cause question); Claude's output is guarded (`guard_question`) and falls back to the question bank's template on any failure |
| Care rules | `navigator/care_rules.yaml` (v3.0, 26 rules) | first match wins; most specific (severity/category/slot) rules take priority, with a `cause_level` fallback (the matched cluster's best cause) just above the catch-all |
| Final answer | `final_answer.py`, `guard.py: check_final` | code-filled slots (told / possible causes / where / options / cost / go-sooner); each section is guarded independently and falls back to its template on failure |
| Retrieval | `navigator/retrieval/` | filters: care type, plan, open now, accepting new patients, age group, within 3 km (unless virtual); in-memory vector store; query built from the parsed report, never raw text |
| Explanation and guard | `explainer.py`, `guard.py` | the explainer sees only the decision and retrieved records; the guard blocks a different level, an ungrounded or unhedged possible cause, unlisted practitioners, a price or phone not in the data, diagnosis/medication wording, or a missing disclaimer |
| Trace | `trace.py`, `traces/*.json` | every step: input (redacted), output, model or rule, latency, tokens |

Living docs: `docs/context-graph.md` and `docs/decisions.md` predate the conversational-triage change (`CHANGE_conversational_triage.md`) and were not updated for it in this pass — see "Implemented, mocked, deferred" below.

---

## Sample data

Everything is fictional and labeled `"synthetic": true`: three towns (Corvalle, Brightwater, Pinecrest), zip codes `00101` to `00303`, carriers, plans, practitioners, phone numbers and addresses. Coordinates sit in rural Kansas so they map to no real clinic. See `data/README.md`.

| File | Contents |
|---|---|
| `zips.json` | 12 zip codes in 3 towns: Corvalle (urban, 00101-00105), Brightwater (suburban, 00201-00204, about 20 km away), Pinecrest (rural, 00301-00303, about 35 km away) |
| `plans.json` | 10 plans: Gold, Silver, Bronze, Student, Platinum, HSA Bronze, a Medicaid-style plan, a senior (65+) plan, a marketplace EPO and self-pay; premium, deductible, out-of-pocket max and cost sharing for 9 services each |
| `practitioners.json` | 73 records: 6 ER (24/7), 16 urgent care (close by 21:00), 30 primary care (daytime), 7 telehealth, 14 specialists |
| `coverage_gaps.json` | for each zip and plan, in-network urgent care, primary care and a specialist within 15 km (34 gaps, all rural or Medicaid-style specialists) |
| `cost_ranges.json` | typical total cost range per care type (estimates) |
| `eval/*.jsonl` | 40 red flags, 44 routing cases, 15 vague, 10 adversarial, 32 retrieval queries, 22 near misses, 12 scripted conversations (interviewer topics, possible causes and cost checks, D-051) |

Built in on purpose: at midnight only ERs and telehealth are open; the Bronze plan has no in-network urgent care in `00105`; rural Pinecrest has no specialists and one urgent care with short hours. See `data/README.md` for the plan comparison table and the gap summary.

## Demo cases (`make demo`)

Run on Tue 3 Nov 2026 14:00 unless noted; zip `00101`, Silver HMO unless noted.

| # | Input | Expected output |
|---|---|---|
| 1 | "Sore throat and fever for two days", severity 4 | **Urgent care** (after a few interviewer questions): Downtown QuickCare and Riverwalk Urgent Care (0.69 km), $75 copay, typical total $150-$300, $3,000 deductible note |
| 2 | "Vomiting and stomach cramps since dinner, can keep water down", severity 5, **00:15** | **Telehealth**: urgent care is closed, NightOwl Virtual Care first, a "go sooner" warning about fluids in the final answer |
| 3 | "Mild chest tightness, probably nothing", severity 2 | **CALL_911**: "Call 911 or go to the nearest ER." |
| 4 | "I just feel off" | **QUESTION**: one question about the main symptom and where it is felt |
| 5 | "Cough and sore throat", Bronze plan, zip `00105` | **Urgent care**, "No in-network urgent care is open within 3 km of zip 00105", online alternatives and the nurse line 1-800-555-0103 |
| 6 | "Sore throat and fever for two days", zip `99999` | "Zip code 99999 isn't in the service area...", **urgent care** still given, online alternatives |

Cases 1, 2, 5 and 6 run the whole conversation (`nav.converse`, routine no-danger answers); case 4 stops after one question (`nav.run`) to show the interviewer in isolation.

## Results

Offline (`python scripts/run_eval.py --offline`):

| Metric | Result | Pass bar |
|---|---|---|
| Red-flag recall | 100% (40/40) | 100% |
| False-emergency rate (near misses + non-emergency routing) | 0% (0/64) | 0% |
| Routing: expected outcome and acceptable level | 100% (44/44) | >= 90% |
| Routing: below the expected level | 0 | 0 |
| Vague -> a question | 100% (15/15) | 100% |
| Adversarial safe handling | 100% (10/10) | 100% |
| Near misses in an acceptable level | 100% (22/22) | >= 90% |
| Conversation accuracy (interviewer topics, causes, cost) | 100% (12/12) | >= 90% |
| Average questions asked | 3.44 (78 runs) | report |
| Conversations over 6 questions | 0 | 0 |
| Retrieval recall@3 | 100% (30 queries) | >= 90% |
| Retrieval filter violations | 0 | 0 |

The question count rose from the earlier slot-filling design's 0.39 average to 3.44: the interviewer now deliberately screens every matched cluster's danger signs and asks a possible-cause question before recommending (CHANGE_conversational_triage.md), instead of asking only when a required field was missing.

Live, with Claude, Jev and Voyage, was verified earlier in the project's history (routing 39/39, demo cases correct) before the conversational-triage rewrite; the live run has not been repeated end to end since (see "Time spent" below).

---

## Implemented, mocked, deferred

**Implemented**
- The whole pipeline above, with offline and live implementations behind interfaces for Claude (parser, interviewer, explainer), Jev and embeddings.
- The conversational-triage rewrite (`CHANGE_conversational_triage.md` Parts 0-4): a curated symptom guide (13 clusters) replaces the old fixed slot-filling flow; the interviewer screens danger signs, then details, then one possible-cause question; the final answer names up to two hedged possible causes, grounded and guarded section by section.
- PII redaction (names after "my name is", emails, phones, dates) before any model call and again in traces.
- Opening hours and after-hours routing, coverage-gap handling with online alternatives and the nurse line, invalid zip and plan messages.
- Danger signs with one action each (`CALL_911` or `GO_TO_ER`, reconciled across `red_flags.yaml` and `symptom_guide.json`, D-048/D-049), negation, per-word typo matching, questions only from `data/question_bank.json`.
- Ten plans with per-service cost sharing; the cost line says when the deductible applies, when the ER copay is waived on admission, and shows cash prices for self-pay.
- Streamlit app (single-question-per-turn, as before the rewrite; see "Deferred"), CLI demo, eval runner, 1,198 tests.

**Mocked or simplified**
- All data is synthetic.
- Offline models: `OfflineJev` (keyword heuristics), regex parser, TF-IDF embeddings, template explainer and interviewer (question-bank order).
- Care rules are simplified and not clinically validated.
- Relative durations are approximations ("since dinner" = 5 hours).
- The Jev HTTP client follows TypeSafe's published API reference and was verified with live calls earlier in the project; it is tested with mocked HTTP only.
- Costs are copay plus a typical range, labeled as estimates.

**Deferred**
- Part 5 of the change request: a chat-style Streamlit layout (`st.chat_message`) with cards for the final answer's sections and danger banners. The app was kept working against the new API (topics, `CALL_911`/`GO_TO_ER`) but not redesigned, to stay inside the time box.
- Part 6: updating `docs/context-graph.md` and `docs/decisions.md` for the new interviewer/guide/final-answer architecture (they still describe the pre-rewrite pipeline).
- Part 4's dedicated FakeInterviewer/FakeExplainer guard unit tests; the guards are exercised indirectly through `test_pipeline.py` and `test_explainer_guard.py` instead.
- Real provider directories and live opening hours.
- Out-of-pocket estimates (deductible progress, coinsurance).
- Booking and wait times.
- Other languages (non-English input gets the follow-up question offline).
- The Claude Sonnet 5.5 evaluation judge for explanation quality.
- ChromaDB or another persistent vector store (in-memory is enough for 73 records).

Known limitations: the Voyage key used in development is rate-limited after about one query in quick succession, so live runs usually fall back to offline search (marked simplified). A live Jev rerank asks one question per candidate (up to 10). The live Claude/Jev/Voyage verification above predates the conversational-triage rewrite and has not been repeated against it.

---

## How AI was used, and how the output was checked

The project was built with Claude Code (Claude Opus 5.5) from a written plan, phase by phase, stopping after each phase for review.

- **Test-driven development.** Every module started with failing tests (committed as `test: ...`), then code (`feat: ...`). Tests were never deleted or weakened; the few test corrections are recorded with reasons (D-016, D-032, D-036).
- **Eval runner.** `scripts/run_eval.py` checks every eval set against the pass bars. Retrieval filters are re-checked by an independent implementation, including a 1,600-search grid with zero violations.
- **Reading the output.** Demo output and traces were read by eye after each phase. This caught a guard rule that blocked facility names containing "Medicine", a misleading "matched: food poisoning", a coverage gap hidden by a 10 km radius (D-031), and wording bugs.
- **Live verification.** One round with real Claude, Jev and Voyage found problems the offline tests could not. Rules leaned on a single classifier output (routing dropped to 35/39 with 3 cases too low), Claude left some durations empty, the guard question was too broad, and Claude invented warning signs. All were fixed test-first (D-036); live routing went to 39/39.
- **API shapes.** Model ids and SDK usage were checked against Anthropic's reference (Haiku 5.5 rejects `temperature`, D-018); the Jev and Voyage request shapes were checked against their published API docs (D-023, D-030).
- **Finishing the conversational-triage refactor.** A second Claude Code session (Claude Sonnet 5) picked up the change request's uncommitted, partly-broken state: two test files still imported the deleted `clarifier` module, and `cli.py`, `app.py` and `scripts/run_eval.py` still referenced the old `Outcome` values. Every fix was checked by running the real pipeline before and after (not just reading the diff): this is how a rule-ordering bug was found (`R-30`, a catch-all "use the guide's cause" rule, was placed above several more specific severity-based rules, silently routing vomiting/diarrhea cases to telehealth that should have gone to urgent care) and a fuzzy-match false positive (the routine answer "All over" scored 0.90 similarity against "overdose" under the existing Jaro-Winkler red-flag matcher, exactly at the threshold, misfiring a false emergency). Both were root-caused and fixed (rule reordering; renaming the routine label), not patched around, and the full eval suite was re-run to confirm 0% false-emergency rate and no regressions before and after each fix.

## Time spent

Roughly 7 hours end to end (first commit 11:03, last commit 18:05 the same day), well past the exercise's suggested 2-4 hour budget. The first ~4 hours built the base prototype (schemas, red flags, Jev/Claude adapters, care rules, RAG retrieval, costs, explainer and guard, the Streamlit app, CLI and eval runner, then two extension prompts for red-flag tiers/question bank and for plans/zips/coverage). The remaining time went into a self-initiated change request (`CHANGE_conversational_triage.md`) that replaced the fixed slot-filling flow with a guided interviewer and hedged possible causes, which turned out to need far more follow-through (porting ~900 lines of tests and the CLI/app/eval entry points to the new topic-based model, plus fixing a rule-ordering regression and a fuzzy-match false positive it introduced) than the time box allows. In hindsight the extension work should have stayed smaller and better bounded to the time limit; see "Deferred" below for what it left unfinished (the chat UI redesign and updated architecture docs).

**What I'd investigate next**: re-run the live Claude/Jev/Voyage verification against the new interviewer (it was only verified against the earlier slot-filling design); finish the Part 5 chat UI and Part 6 docs; add the dedicated FakeInterviewer/FakeExplainer guard unit tests from Part 4; look for other rule-ordering issues like the one fixed here (R-30 was first placed above several more specific rules, silently overriding them).
