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

## D-011: Fake zip codes and a fictional town
- Date: 2026-10-27
- Status: accepted
- Context: D-010 requires data that can't be mistaken for real places, but retrieval needs real-looking geometry for haversine distance filters.
- Decision: Use the fictional town "Corvalle" with zips `00101` to `00105` (not issued as real zips) and centroids a few km apart in rural Kansas, where they map to no real clinic. Phones use `555-01xx`.
- Alternatives considered: Real zips with fake clinics (rejected: could be mistaken for real locations); no coordinates (rejected: distance filter untestable).
- Consequences: Distances are realistic; nothing resolves to a real address.

## D-012: Deliberate coverage gap for testing
- Date: 2026-10-27
- Status: accepted
- Context: The "no in-network option nearby" path must be demonstrable and tested, and real networks do have gaps.
- Decision: `PLAN_BRONZE_LOCAL` has no in-network urgent care in zip `00105`. `tests/test_data.py` asserts the gap stays; retrieval must return an empty list cleanly and the pipeline must offer telehealth and the nurse line instead.
- Alternatives considered: Simulating the gap only in a test fixture (rejected: the demo and eval need it in the real data).
- Consequences: Any data change that "fixes" the gap fails the data tests.

## D-013: Byte-identical data on every OS
- Date: 2026-10-27
- Status: accepted
- Context: Rerunning `data/generate.py` on Windows produced CRLF files (`Path.write_text` translates `\n`), and `core.autocrlf` re-checked out the committed data as CRLF, so "reruns produce identical files" depended on the machine. Content was otherwise identical.
- Decision: The generator writes with `newline="\n"`; `.gitattributes` pins `data/*.json`, `data/eval/*.jsonl` and the `Makefile` to LF. `tests/test_generate.py` regenerates into a temp dir and compares bytes, and asserts LF endings. This is the only change to the provided data folder.
- Alternatives considered: Comparing parsed JSON instead of bytes (rejected: hides non-determinism such as key order); asking everyone to disable autocrlf (rejected: fragile).
- Consequences: Data files are LF everywhere; the determinism guarantee is enforced by a test.

## D-014: Red-flag fuzzy matching threshold
- Date: 2026-10-27
- Status: accepted
- Context: Red flags must survive typos ("chest pian", "cant breath") without firing on near misses like "can keep water down" (the midnight TELEHEALTH case) or "I can breathe fine".
- Decision: Normalize text (lowercase, apostrophes removed, punctuation to spaces). Try every phrase of a category as an exact word-boundary match first; only if none hits, slide a window of the phrase's token count over the text and take the best RapidFuzz `fuzz.ratio`. A window counts when ratio >= 88 (`config.FUZZY_THRESHOLD`) and every token shorter than 4 chars (`config.FUZZY_MIN_TOKEN_LEN`) matches exactly. Observed scores: "chest pian" 90, "cant breath" 96.
- Alternatives considered: Plain `fuzz.partial_ratio` (rejected: when the text is shorter than the phrase it scores 100 for "chest" vs "chest pain", and "can keep water down" scores ~95 against "cant keep water down"); threshold 85 (rejected: "can"/"cant" style flips get through without the short-token rule); 92 (rejected: misses "chest pian").
- Consequences: Typos inside short words (<4 chars) are not tolerated; Jev and the parser cover those. Tests pin both directions (typos caught, near misses quiet).

## D-015: Red-flag categories, patterns and coverage split
- Date: 2026-10-27
- Status: accepted
- Context: The eval set uses more categories than the plan lists (infant_fever, neuro, head_injury, poisoning, pregnancy, trauma, abdominal, infection), and some flags need two facts at once (age + fever, head hit + vomiting).
- Decision: `red_flags.yaml` (v1.0, "simplified, not clinically validated") uses the eval set's category names (`allergic_reaction` for severe allergic reaction, `mental_health_crisis` for suicidal intent). Each category has `phrases` (exact + fuzzy) and/or `patterns` (lists of regexes that must all match). `mental_health_crisis` returns resources `["988", "911"]` with the 988 message first; all others return `["911"]`. Keyword screen catches 100% of the 28 `keyword`/`fuzzy_keyword` cases and 5 of the 12 `parsed_or_jev` cases. Left for Jev / parsed-field checks (Phase 3): RF-005 (elephant on chest), RF-009 (struggling to catch breath), RF-015 (sudden vision loss + headache), RF-017 (confused, can't lift arm), RF-024 (hard to swallow, lips swelling), RF-034 (lower right belly pain + fever), RF-040 (car crash, neck pain, tingling hands).
- Alternatives considered: Adding phrases until all 40 pass (rejected: overfits the eval set and hides the defense-in-depth design).
- Consequences: Phase 3 must cover the seven cases above with OfflineJev / parser rules; the end-to-end red-flag recall bar (100%) depends on it.

## D-016: Test correction, fuzzy typo case
- Date: 2026-10-27
- Status: accepted
- Context: `test_typos_are_caught_by_fuzzy_match` used "my face is drooping on one sde". It contains the exact phrase "face is drooping", so the screen (correctly) matched exactly and the "method is fuzzy" assertion failed. The test input was wrong, not the code.
- Decision: Changed the input to "my fase is droopng on one side" so the typo sits inside the phrase. The assertion (fuzzy method) is unchanged.
- Alternatives considered: Dropping the method assertion (rejected: weakens the test).
- Consequences: None for behaviour.

## D-017: No negation handling in the keyword screen
- Date: 2026-10-27
- Status: accepted
- Context: "no chest pain" contains "chest pain". Negation detection is error-prone and a miss would route an emergency down.
- Decision: The keyword screen ignores negation; "no chest pain" fires. This errs toward more care (D-003).
- Alternatives considered: NegEx-style negation windows (rejected: risk of suppressing real flags such as "not sure but chest pain").
- Consequences: Some over-triage to EMERGENCY. Logged as an open question in the context graph.

## D-018: Claude parser request shape on Claude Haiku 5.5
- Date: 2026-10-27
- Status: accepted
- Context: The plan asks for "temperature 0". Claude Haiku 5.5 returns HTTP 400 for any non-default sampling parameter (`temperature`, `top_p`, `top_k`), and API version `2026-10-21` rejects them on every model.
- Decision: `ClaudeParser` sends no sampling parameters. Output is made predictable by a forced tool call (`tool_choice: {"type": "tool", "name": "record_symptoms"}`, which Haiku 5.5 accepts) with `strict: true` and `additionalProperties: false`, plus Pydantic validation. Invalid output or a `refusal` stop reason -> one retry -> `OfflineParser`. An API error (timeout, 5xx, connection) skips the retry and goes straight offline, because the SDK already retries once (`max_retries=1`). Severity is never taken from the model; it is passed through from the request.
- Alternatives considered: Sending `temperature=0` (rejected: 400); structured outputs via `output_config.format` (viable, but the plan specifies tool use and the forced tool already gives a schema guarantee).
- Consequences: Extraction can vary slightly between runs; the rules downstream are deterministic. If a future model rejects forced `tool_choice` (as Opus 5.5 and Sonnet 5.5 do), switch to `auto` plus a prompt instruction.

## D-019: Jev thresholds and offline heuristics
- Date: 2026-10-27
- Status: accepted
- Context: Jev returns probabilities; the pipeline needs yes/no decisions, and offline mode needs a transparent stand-in.
- Decision: Probabilities >= 0.5 count as "yes" for emergency, too-vague and the output guard (`config.JEV_EMERGENCY_THRESHOLD`, `JEV_VAGUE_THRESHOLD`, `GUARD_THRESHOLD`). `OfflineJev` uses pattern combinations (all patterns in a combo must match) for indirect emergencies, a weighted lexicon for category (symptom term 2, body area 1, ties go to the earlier category), +/- cue counts for urgency (base 2, clamped 1-5), "named symptom, or body area + pain word" for vagueness, stem overlap for rerank, and a pattern list for diagnosis/medication. Offline confidences are fixed (0.6; vague 0.7) to signal "heuristic".
- Alternatives considered: A small trained classifier offline (rejected: opaque, more setup, not needed for 44 records and ~100 eval rows).
- Consequences: Keyword screen + OfflineJev together catch 40/40 red flags; OfflineJev alone catches all 12 `parsed_or_jev` cases. Zero emergency or vague false positives on routing cases. The heuristics are tuned on the eval phrasing and will generalise less well than a real classifier.

## D-020: Relative durations are approximations
- Date: 2026-10-27
- Status: accepted
- Context: People say "since dinner", "this morning", "tonight" instead of hours.
- Decision: `OfflineParser` maps relative phrases to fixed hours (yesterday 24, breakfast 10, lunch 8, morning 6, dinner 5, afternoon 3, tonight 2; "for days/weeks/months" 72/336/2160). Explicit amounts ("2 days", "two days", "an hour") are computed; "N year(s) old" is ignored as an age.
- Alternatives considered: Computing from the request time (for example "since dinner" at 00:15 = about 5 h) (rejected for now: more code, and the rules only need short vs. multi-day).
- Consequences: Duration is coarse; rules must use wide bands, not exact hours.

## D-021: Shared lexicon module
- Date: 2026-10-27
- Status: accepted
- Context: OfflineJev (category, vagueness) and OfflineParser (main symptom, body area) must agree on what counts as a symptom, or the vague check and the parser's confidence could disagree.
- Decision: Add `navigator/lexicon.py` (not in the planned layout) with symptom terms by category, body areas and pain words. Categories: respiratory, ent, gastrointestinal, musculoskeletal, skin, eye, urinary, wound, dental, mental_health, chronic, allergy, fever, neuro, plus `general` when nothing is recognised.
- Alternatives considered: Duplicating word lists in both modules (rejected: they would drift).
- Consequences: Phase 4 `care_rules.yaml` keys on these category names.

## D-022: Jev HTTP shape is unverified
- Date: 2026-10-27
- Status: superseded by D-023
- Context: No Jev API docs are available, and the plan forbids guessing silently.
- Decision: All request building lives in `build_jev_request` and response reading in `parse_jev_response`, both marked `TODO: verify against Jev docs`. Assumed shape: POST `{state, questions: [{id, type: yes_no|choice|score, text, options|min|max}]}` with `Authorization: Bearer <JEV_API_KEY>`; response `{answers: [{id, probabilities|score, confidence}]}`. Endpoint from `JEV_BASE_URL` (placeholder default). Any network error, non-200 or unreadable body raises `JevError`; the pipeline (Phase 6) falls back to `OfflineJev`. Tested with mocked HTTP only.
- Alternatives considered: Leaving `HttpJev` unimplemented (rejected: the plan asks for a real client behind the interface).
- Consequences: Must be checked against real docs before `JEV_API_KEY` is used.

## D-023: HttpJev follows the TypeSafe Jev API reference
- Date: 2026-10-27
- Status: accepted
- Context: Jev is TypeSafe's classifier. Its public docs (docs.typesafe.ai/models and /api) show the D-022 guess was wrong: a different endpoint, questions as a map not a list, `noul` instead of yes/no, a required `model`, zero-based scores, and answers keyed by question name.
- Decision: `HttpJev` posts to `https://api.typesafe.ai/v1/systemone` (override `JEV_BASE_URL`) with `Authorization: Bearer <JEV_API_KEY>` and body `{model, state, questions: {name: {type: noul|choice|score, instructions, criteria}}}`. `model` comes from `JEV_MODEL`, default `jev-latest`. `build_jev_request` checks the documented limits locally (at least one question; choice 1-255 named options; score 1-10 ordered levels). Mapping to our interface:
  - `is_emergency`, `is_too_vague`, `mentions_diagnosis_or_medication`: `noul` questions. `noul` answers carry no confidence, so confidence = |2p - 1| (0 at p = 0.5, 1 at p = 0 or 1).
  - `classify_category`: one `choice` question whose criteria are our categories with short descriptions; an unknown choice maps to `general`.
  - `urgency_score`: `score` with 5 levels; the zero-based expected value + 1, rounded half up and clamped to 1-5.
  - `rerank`: one request with a 3-level `score` question per document; score / 2 gives 0-1.
  A missing answer, non-200 (including 400/422 validation errors), network error or bad JSON raises `JevError`. Still tested with mocked HTTP only.
- Alternatives considered: Keeping our own shape behind an adapter (rejected: it would never work against the real API); separate requests per method in one batch (rejected: the interface calls one method at a time).
- Consequences: The client matches the documented contract. Live smoke test on 2026-10-27: `is_emergency("chest pain and sweating")` returned HTTP 200 from `jev-1.14.0` with `noul` 0.95 (confidence 0.9), 279 input tokens; only the `noul` path has been exercised live, the `choice` and `score` paths are covered by mocked tests only. Auth failure status codes aren't documented; any non-200 is treated as an error and the pipeline falls back to `OfflineJev`.

## D-024: Loading .env
- Date: 2026-10-27
- Status: accepted
- Context: The user keeps keys in `care-navigator/.env`. Loading it on import could switch real providers on during tests, which must never touch the network.
- Decision: `config.load_env_file()` (no new dependency) reads `KEY=value` lines, skips comments, blank values and malformed lines, strips quotes, and never overrides a variable already in the environment. Entry points (`cli.py`, `app.py`, `scripts/run_eval.py`) call it; importing `config` does not. `tests/conftest.py` clears all provider variables for every test as a second guard.
- Alternatives considered: `python-dotenv` (rejected: a dependency for 15 lines); loading on import (rejected: tests could go live).
- Consequences: Phase 7 entry points must call `config.load_env_file()` first.

## D-025: When medium confidence escalates
- Date: 2026-10-27
- Status: accepted
- Context: The plan says medium confidence escalates one level. `OfflineParser` marks a report medium whenever the duration isn't stated, which is true for about half the routing cases ("Pink eye, crusty eyes"). Escalating all of them pushes 10+ cases out of `acceptable_levels` (for example, a twisted ankle to the ER in daytime).
- Decision: Escalate one level when (a) confidence is medium and either nothing is listed as missing (the parser itself was unsure) or a material field is missing (anything except duration and body area), or (b) after the one follow-up, the main symptom is still missing. A missing duration alone does not escalate, because rules that depend on duration (`min_duration_hours`, the long-standing rule R-05) never match when it is unknown, so an unknown duration is treated as recent rather than as a long-standing, lower-acuity problem. No rule reads body area.
- Alternatives considered: Literal "medium -> escalate" (rejected: over-triages 10+ cases); dropping the parser's medium label for missing duration (rejected: the label is still useful for the follow-up question).
- Consequences: 38/39 non-emergency routing cases land exactly on `expected_level`, 1 lands one level higher (RT-008, closed urgent care -> ER), 0 lower.

## D-026: Time of day is handled by opening hours and per-rule after-hours levels
- Date: 2026-10-27
- Status: accepted
- Context: The same symptom needs different answers by time: daytime food poisoning -> urgent care, midnight -> telehealth (RT-002/RT-004); an evening ankle injury must not drop to telehealth (RT-008 accepts only urgent care or higher).
- Decision: Each rule has a `level` and an `after_hours` level (never SELF_CARE). The engine checks whether any practitioner of the chosen type is open at the request time, accepts the plan (ignored if the plan is unknown or missing) and sees the age group. If none is, it moves to the rule's `after_hours` level (virtual-friendly problems -> TELEHEALTH; injuries needing an exam -> ER), then steps up until something is open; ER is always the last stop. SELF_CARE needs no open practitioner. A note says what was closed and where the person is going instead. Distance is not checked here; that is retrieval's hard filter (Phase 5), so a coverage gap shows up as an empty retrieval result, not a different level.
- Alternatives considered: Time-of-day conditions inside rules (rejected: duplicates every rule for day/night and drifts from real opening hours); always stepping up when closed (rejected: midnight food poisoning would go to the ER, against the eval).
- Consequences: Care levels follow the synthetic opening hours exactly; changing the data changes routing at night.

## D-027: Shared data access module
- Date: 2026-10-27
- Status: accepted
- Context: The care engine and retrieval both need practitioners, plans, zips and the opening-hours check.
- Decision: Add `navigator/data.py` (not in the planned layout): cached loaders returning Pydantic `Practitioner` models and plan/zip dicts, plus `is_open(hours, when)` (start inclusive, end exclusive, "24h", null = closed).
- Alternatives considered: Putting `is_open` in `care_engine.py` and importing it from retrieval (rejected: odd dependency direction).
- Consequences: One place to change if the data moves to a real directory.

## D-028: Follow-up question validation
- Date: 2026-10-27
- Status: accepted
- Context: The follow-up question must be one question, at most 25 words, and never suggest a diagnosis or a care level, whether a template or Claude wrote it.
- Decision: `is_valid_question` requires exactly one "?" at the end, <= 25 words, no care-level words (ER, emergency, urgent care, telehealth, primary care, self-care, 911, 988, hospital, clinic, nurse line, doctor, ambulance), and the diagnosis/medication guard below threshold. `OfflineClarifier` uses templates keyed by the first missing field (main symptom, then duration, then body area). `ClaudeClarifier` (Haiku 5.5, `effort: low`, no sampling params) gets one attempt; invalid output, a refusal or an API error falls back to the template. Asking at most once is enforced by the pipeline (Phase 6) via `after_followup`.
- Alternatives considered: Retrying Claude on invalid output (rejected: the template is always valid and cheaper).
- Consequences: Claude's question can be rejected for harmless wording such as "doctor"; the template then applies.

## D-029: In-memory vector store instead of ChromaDB
- Date: 2026-10-27
- Status: accepted
- Context: Retrieval needs cosine search with metadata filtering over 44 practitioner records.
- Decision: `InMemoryVectorStore` (numpy): `add(ids, vectors, metadatas)` and `search(vector, k, where=predicate)`. The retriever passes the hard-filter survivors as the `where` predicate, so semantic search only ever ranks allowed records.
- Alternatives considered: ChromaDB (rejected for the prototype: install, persistence directory and setup for 44 rows, no benefit at this size). It is the production path once the directory is real and large.
- Consequences: Everything is rebuilt in memory at start-up (well under a second with TF-IDF; one batch call with Voyage).

## D-030: Hybrid retrieval details
- Date: 2026-10-27
- Status: accepted
- Context: D-006 fixes the order (filters -> hybrid -> RRF k=60 -> rerank); the parts still needed concrete choices.
- Decision:
  - Hard filters: type = care level, plan accepted, open at request time, accepting new patients (primary care and specialists only, matching `data/README.md`), serves the age group, and within `max_km` (default 10 km, haversine from the zip centroid) unless virtual. An unknown zip drops all in-person options (distance can't be checked) and keeps virtual ones. SELF_CARE retrieves nothing.
  - Indexed text per practitioner: facility name, specialties, conditions, bio and languages (languages so "Spanish-speaking" queries work).
  - Semantic side: offline `LocalTfidfEmbedder` uses character 3-5-gram TF-IDF (robust to word forms such as "sprain/sprains" and typos). `VoyageEmbedder` (`VOYAGE_API_KEY`) calls `POST https://api.voyageai.com/v1/embeddings` with `input_type` document/query, model `VOYAGE_MODEL` (default `voyage-4`), batches of 128, vectors normalized; any failure raises `EmbeddingError`. Request shape checked against Voyage's API reference; tested with mocked HTTP only.
  - Lexical side: `rank-bm25` over word tokens with stopwords removed and light suffix stripping.
  - Fusion: RRF k = 60 over the two rankings; top 10 go to Jev rerank. Final order: rerank score, then distance (virtual = 0), then fused score. If rerank raises `JevError`, fused order is used and `reranked=False` is recorded.
  - Query: built from the parsed `SymptomReport` (main symptom + body area), never the raw text, so injected instructions can't steer retrieval.
  - Each match carries `matched_text`: the record segment (condition, specialty or bio sentence) sharing the most terms with the query.
- Alternatives considered: Word-level TF-IDF (rejected: misses "sprain" vs "sprains" without a stemmer); ordering by distance before relevance (rejected: the plan says distance is the tie-break).
- Consequences: recall@3 = 1.0 on the 20 non-empty retrieval queries (top-1 correct on all 20), zero filter violations across a 1,600-search grid, the coverage-gap query returns an empty list. Voyage hasn't been called live. The default radius was later changed to 3 km (D-031).

## D-031: "Nearby" means 3 km
- Date: 2026-10-27
- Status: accepted
- Context: Zip centroids are 4-10 km apart and every zip has its own in-network urgent and primary care except the deliberate gap (D-012). With a 10 km default, the whole town counts as nearby and the Bronze/00105 gap never shows (UC-001 is 4.8 km away), so demo case 5 can't happen.
- Decision: `config.MAX_DISTANCE_KM = 3.0` (the person's own neighbourhood; matches the eval's gap query RQ-019). Retrieval eval queries still pass their own `max_distance_km`.
- Alternatives considered: 10 km (rejected: hides the coverage gap); widening the radius when fewer than 3 results are found (rejected: also hides the gap and makes "nearby" vary per request).
- Consequences: Most requests show 1-2 in-person options, not 3. The gap note names the radius ("within 3 km of zip 00105").

## D-032: Test correction, number of options in the representative case
- Date: 2026-10-27
- Status: accepted
- Context: `test_representative_case` and the embedding-fallback test asserted exactly 3 options. That was my assumption, not the plan's ("top 3" = up to 3). With the 3 km radius (D-031) the representative case has 2 open in-network urgent cares.
- Decision: Assert 1 to 3 options (and "some options" for the fallback test). Every other assertion (level, copay $75, typical $150-$300, 3-5 sentences, disclaimer) is unchanged.
- Alternatives considered: Widening the radius to get 3 (rejected, see D-031).
- Consequences: None for behaviour.

## D-033: Pipeline behaviour on invalid or incomplete input
- Date: 2026-10-27
- Status: accepted
- Context: The plan asks for clear messages for empty text, too-long text and invalid zip or plan, while still giving the care level where possible.
- Decision: Empty text and text over 2,000 characters (`config.MAX_TEXT_CHARS`) stop the request with `outcome=None` and a clear message; nothing is sent to any model. An unknown zip or plan doesn't stop it: the rules still pick the level, `errors` explains the limitation, the engine ignores an unknown plan for the opening-hours check, and retrieval drops in-person options for an unknown zip (D-030) and everything for an unknown plan (nothing is in-network). When the level is urgent or primary care and nothing in-network is open within 3 km, the result says so, lists telehealth `alternatives` and shows the plan's nurse line. The follow-up answer is appended to the original text and re-screened from the start (red flags first); `after_followup=True` means the pipeline never asks a second question (D-003). Off-topic and non-English text in offline mode get the follow-up question.
- Alternatives considered: A fourth outcome such as INVALID (rejected: the plan fixes three outcomes); truncating long text (rejected: the end of a long message may hold the red flag).
- Consequences: Everything above is covered by `tests/test_pipeline.py` including all 10 adversarial cases.

## D-034: Explanation and guard details
- Date: 2026-10-27
- Status: accepted
- Context: D-007 limits the explainer's input; the guard needs concrete rules that the template can always pass.
- Decision: Each rule in `care_rules.yaml` (now v1.1) has a plain-English `reason`; two notes were reworded to avoid "you have", which the diagnosis guard treats as diagnosis wording. `TemplateExplainer` writes 4-5 sentences: why (level + reason, plus "moved up one level" if escalated), the closure note if any, the options with distance and the first option's copay and typical total, the rule's escalation note (or a generic one), then "This is not medical advice." `ClaudeExplainer` gets only `{decision, options}` as JSON (level, rule, reason, notes; facility, name, type, distance, copay, typical total), no symptom text, `effort: low`, no sampling params. The guard blocks when: the disclaimer is missing; the decision's level isn't named; another level is named outside a sentence that says it's closed / not in network or a conditional "if ..., go to the ER"; a directory practitioner or any "Dr. X" not in the retrieved list is named; or Jev (OfflineJev if Jev is down) flags a diagnosis or medication. Retrieved record names are removed before the level and diagnosis checks, because names like "Downtown Internal Medicine" are trusted record text. On block, the template is used and the trace says why.
- Alternatives considered: Guarding only with Jev (rejected: level and name checks are deterministic and cheap).
- Consequences: The template passes the guard on all 39 non-emergency routing cases (tested). A Claude explanation that paraphrases a level differently ("walk-in clinic") may fail the "level named" check and fall back to the template.

## D-035: Costs and traces
- Date: 2026-10-27
- Status: accepted
- Context: The plan asks for copay + typical range labeled as estimates, deductible when high, and a JSON trace per request.
- Decision: `costs.estimate(care_type, plan)` returns the plan's copay for that type and the typical total from `cost_ranges.json`, labeled "Estimate"; the deductible is mentioned at or above $3,000 (`config.HIGH_DEDUCTIBLE_USD`: Silver and Bronze). Unknown plan -> typical range only; self-care -> no copay. `Tracer` records each step (name, input, output, model or rule, latency, tokens) and re-applies `redact()` to every input and output as a safety net on top of redacting before any model call; the raw text is never logged. One JSON file per request in `traces/` (gitignored), with a summary (outcome, level, rule, simplified, errors, request fields without text). Token counts are recorded for Claude steps; dollar cost is left empty because only totals, not input/output splits, are kept.
- Alternatives considered: Logging raw text with access controls (rejected: D-009).
- Consequences: The trace viewer (Phase 7) reads these files or the in-memory `result.trace`.
