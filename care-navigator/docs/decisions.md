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
- Status: accepted
- Context: No Jev API docs are available, and the plan forbids guessing silently.
- Decision: All request building lives in `build_jev_request` and response reading in `parse_jev_response`, both marked `TODO: verify against Jev docs`. Assumed shape: POST `{state, questions: [{id, type: yes_no|choice|score, text, options|min|max}]}` with `Authorization: Bearer <JEV_API_KEY>`; response `{answers: [{id, probabilities|score, confidence}]}`. Endpoint from `JEV_BASE_URL` (placeholder default). Any network error, non-200 or unreadable body raises `JevError`; the pipeline (Phase 6) falls back to `OfflineJev`. Tested with mocked HTTP only.
- Alternatives considered: Leaving `HttpJev` unimplemented (rejected: the plan asks for a real client behind the interface).
- Consequences: Must be checked against real docs before `JEV_API_KEY` is used.
