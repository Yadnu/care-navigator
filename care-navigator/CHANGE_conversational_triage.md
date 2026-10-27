# Change request: conversational triage

Follow TDD and PROMPT.md section 2.4 (no hallucination). Read `docs/context-graph.md` and `docs/decisions.md` first. Stop after each part, paste the `pytest -q` and `make eval` output, and wait for "continue".

---

## Part 0: Set up the files and reconcile safety rules (do this first)

### 0.1 Move and build the guide

1. Move `symptom_prompt/build_symptom_guide.py` to `data/build_symptom_guide.py` (use `git mv` if tracked). Delete the empty `symptom_prompt/` folder.
2. If this file (`CHANGE_conversational_triage.md`) is not in the repo root, save it there so later sessions can `@` it.
3. Normalize line endings to LF for both files (and add `*.py text eol=lf` and `*.json text eol=lf` to `.gitattributes` if missing).
4. Confirm the script writes to `data/symptom_guide.json` (it writes next to itself, so after the move it will). Run `python data/build_symptom_guide.py` and paste the output line.
5. Add `make guide` to the Makefile, and make `make data` also run it.

### 0.2 Decisions to log before coding

- Integrate the guide so the app may mention **hedged possible causes**. Log a decision superseding D-007 and D-034. Diagnosis wording ("you have X") and medications stay forbidden. The guard switches to an allow-list: possible causes only from the matched cluster in `symptom_guide.json`, always hedged.
- **One source of truth for each kind of rule:** `red_flags.yaml` holds the Tier 1 immediate phrases (no questions asked). `symptom_guide.json` `danger_signs` holds what the interviewer screens for during the conversation. The same sign must never have two different actions.

### 0.3 Reconcile danger signs (tests first)

1. Write `tests/test_safety_consistency.py`: fail if any sign appears in both files with a different action (`CALL_911` vs `GO_TO_ER`).
2. "Can't keep fluids down" is `GO_TO_ER`, not `CALL_911`. It becomes `CALL_911` only together with confusion, fainting, extreme sleepiness, or blood in the vomit. Update `red_flags.yaml` to match.
3. Add to `data/eval/near_misses.jsonl`: "can't keep water down since this morning" (expected `GO_TO_ER`, must not be `CALL_911`).
4. Red-flag recall must stay at 100%.
5. List every other mismatch you find as a table (sign, `red_flags.yaml` action, guide action, your proposed action). **Wait for my OK** before changing those.

Then stop, paste `pytest -q` and `make eval`, and wait for "continue" before Part 1.

---

## Why

The app is too deterministic. "I am vomiting continuously" (severity 4, zip 00103, PLAN_HSA_BRONZE_HMO) jumps straight to "Call 911" without listening. It should behave like a good triage nurse:

1. Ask about other symptoms and what might have caused it (what they ate, sick contacts, travel, recent injury).
2. Screen for danger signs on every turn.
3. Finish with a clear answer: what you told me, what it could be (hedged), where to go and why, the closest option with its cost under your plan, and when to go sooner or call 911.

## Principles that do not change

- Unmistakable emergencies still stop immediately (Tier 1). Asking questions during a possible heart attack or stroke costs time.
- Rules make the final care-level decision. Claude runs the conversation and writes the wording.
- Every fact shown (names, addresses, distances, prices, causes, danger signs) comes from data. Claude never invents facts.
- Possible causes are allowed ONLY from `symptom_guide.json` for the matched cluster, always hedged. Never "you have X". Never medications or doses.

---

## Part 1: The conversation loop

Each user turn runs this loop:

1. **Safety screen (rules + Jev), every turn, on the new message and the full conversation.**
   - Tier 1 phrases and any guide `danger_signs` with action `CALL_911` -> outcome `CALL_911`, stop.
   - Guide `danger_signs` with action `GO_TO_ER` confirmed by the person -> outcome `GO_TO_ER`, stop.
   - Jev alone triggers an emergency only at probability >= 0.8 with high confidence (config.py).
2. **Update the conversation state.** Structured `ConversationState`: matched clusters (from guide `match_terms` plus Jev category), answers per topic with an `evidence` quote from the person's words, danger signs asked and their answers, possible-cause answers, question count.
3. **Interviewer picks the next step** (Claude Haiku 5.5, temperature 0.3; offline fallback uses guide topics with template wording). Input: the state plus, for each matched cluster, `ask_about`, `possible_cause_questions` and `danger_signs`. Output JSON only:
   ```json
   {"done": false, "topic": "fluids_kept_down", "question": "...", "quick_replies": ["Yes", "Some", "No, nothing stays down"], "reason": "..."}
   ```
   Interviewer rules:
   - One question per turn, under 30 words, plain language, warm tone. It can acknowledge what they said ("That sounds rough.").
   - Order: first screen the matched clusters' danger signs that haven't been asked, then the most important `ask_about` topics, then one `possible_cause_questions` item.
   - Ask about other symptoms they haven't mentioned when the cluster suggests it ("Any fever or belly pain with the vomiting?").
   - Typically 3 to 5 questions; never more than 6. Set `done: true` as soon as the rules have enough to decide.
   - Never give advice, a diagnosis or a care level during the conversation.
4. **Question guard (code).** Reject and fall back to the template if: `topic` is not in the matched clusters' `ask_about`, a danger sign or a possible-cause question; the text names a condition, medication or care level; more than 30 words; or it repeats a topic already answered.
5. **Decision (rules).** When `done` or after 6 questions: the care engine decides `CALL_911`, `GO_TO_ER`, or a level (`URGENT_CARE`, `PRIMARY_CARE`, `TELEHEALTH`, `SELF_CARE`) using the state, the guide's `typical_level` for the best-matching possible cause, the time of request, open hours and plan coverage. Unanswered danger-sign topics escalate one level.
6. The person can press **"Skip, just tell me where to go"** at any time; the engine decides with what it has and escalates one level for anything unknown.

---

## Part 2: The final answer

Build it from slots that code fills; Claude Haiku 5.5 only writes connecting sentences (same grounding guard as before). Sections:

1. **What you told me.** 2 to 3 bullets summarizing the state, each backed by an evidence quote from the conversation.
2. **What it could be.** Up to 2 possible causes from the matched cluster's `possible_causes`, with their `description`, phrased as "One common possibility is...". End with "A clinician needs to confirm this." Skip this section for `CALL_911` and mental health.
3. **Where to go and why.** The decided level and the reason (rule explanation or guide `why`).
4. **Closest options.** For `CALL_911`/`GO_TO_ER`: the 2 nearest ERs to the zip (pediatric ER first for a child) with name, address, phone, distance in km, "Open 24/7". Otherwise: the top 3 retrieved practitioners that are open now and in network, with distance and hours today. If none, say so and offer telehealth plus the plan's nurse line.
5. **What it may cost with your plan.** From `plans.json` `services`: the copay; whether the deductible applies; for the ER, whether the copay is waived if admitted and the plan's `emergency_rule`; for HSA or high-deductible plans, "you pay the full allowed cost until your deductible is met" with the deductible amount; for `SELF_PAY`, the cash price. Label it as an estimate.
6. **Go sooner or call 911 if.** The matched cluster's `watch_for` items plus the most relevant danger signs.
7. **Safety lines.** `CALL_911`: "Call 911 now. Do not drive yourself." `GO_TO_ER`: "Go now and have someone else drive. Call 911 if it gets worse." Mental health: 988 and 911 first. Nurse line only for non-911 outcomes.

---

## Part 3: Guards (extend `guard.py`)

- Every possible cause named is in the matched cluster's `possible_causes`.
- Hedging is present; the words "you have" never precede a cause.
- No medication names or doses (keyword list plus the Jev check).
- Every number, name, address, phone and price exists in the data or was computed by code (distance).
- Every "What you told me" bullet has an evidence quote found in the conversation.
- On any failure, fall back to the template version of that section and record the reason in the trace.

---

## Part 4: Data and tests (write tests first)

- `tests/test_symptom_guide.py`: schema; every danger sign has action `CALL_911` or `GO_TO_ER` and a `why`; every possible cause has a valid `typical_level`; the mental health cluster has no possible causes and no `ask_about`.
- Rebuild the offline `question_bank.json` from the guide's `ask_about` topics so offline mode still works.
- `data/eval/conversations.jsonl` (synthetic: true). Each case has: a first message, the context (zip, plan, age, time), a scripted answer per topic (a fake interviewer asks topics in guide order), expected outcome, acceptable levels, max questions, topics that must be asked, and expected final-answer facts. Include at least:
  1. "I am vomiting continuously", 00103, PLAN_HSA_BRONZE_HMO, now. Answers: some fluids stay down, no blood, no dizziness, ate leftover takeout, roommate fine, 8 hours. Expected: `URGENT_CARE` or `TELEHEALTH`; possible causes include food poisoning or a stomach bug; cost section shows the HSA deductible note.
  2. Same start, but "nothing stays down" and "dizzy when I stand". Expected `GO_TO_ER`; the 2 nearest ERs to 00103 by computed distance; HSA ER cost note; `emergency_rule` shown.
  3. Same start, "yes" to blood. Expected `CALL_911`, no possible-causes section.
  4. "vomiting blood". Expected `CALL_911` with 0 questions.
  5. "pain in my left hand since I played volleyball": asks swelling, use, numbness, cardiac screen. Expected `URGENT_CARE`; possible causes sprain or small fracture.
  6. "my arm hurts" plus "chest feels tight and I'm sweating". Expected `CALL_911`.
  7. "headache", came on slowly after screens. Expected `SELF_CARE` or `TELEHEALTH`.
  8. "headache", sudden and worst ever. Expected `CALL_911`.
  9. "stomach pain", lower right, worsening, fever. Expected `GO_TO_ER`.
  10. "my kid has a fever", 8 months old, 101F, drinking well, 2 pm. Expected `URGENT_CARE` or `TELEHEALTH` with pediatric options first.
  11. Midnight food poisoning, PLAN_SILVER_HMO, 00101, fluids stay down. Expected `TELEHEALTH` (NightOwl open, Summit telehealth closed).
  12. SELF_PAY, tight budget, midnight vomiting, fluids stay down. Expected `TELEHEALTH` with the $59 cash price.
- Unit tests with a **FakeInterviewer** that deliberately returns bad outputs: a question naming a diagnosis, a medication, a topic not in the guide, 50 words, or a repeated topic. The guard must catch each one.
- Unit tests with a **FakeExplainer** that names a cause not in the guide, says "you have food poisoning", or adds a price not in the data. The guard must block each one.

**Metrics for `make eval`:**
- Red-flag recall: 100% (`CALL_911` or `GO_TO_ER` as expected)
- False emergency rate on `near_misses.jsonl` and `routing_cases.jsonl`: 0%
- Conversation accuracy: >= 90% within acceptable levels, never lower than expected
- Average questions per conversation (report) and conversations over 6 questions (must be 0)
- Possible causes from the guide: 100%; medication mentions: 0; ungrounded facts: 0

**Optional live eval (`make eval-live`, needs API keys, never run in tests):** Claude Sonnet 5.5 role-plays the patient from a hidden case card for each conversation case, answering only what it's asked, while the real interviewer runs. Report the same metrics. This tests the real conversation without scripting it.

---

## Part 5: UI

- Switch to a chat layout (`st.chat_message`, `st.chat_input`). Keep zip, plan, who it's for and time of request in the sidebar.
- Show quick-reply buttons under each question, plus free text.
- A visible "Skip, just tell me where to go" button.
- Final answer as cards: What you told me, What it could be, Where to go, Closest options, Cost with your plan, Go sooner if.
- Banners: red for `CALL_911`, orange for `GO_TO_ER`.
- The trace viewer shows every turn: safety screen result, interviewer JSON, guard result, and the final decision with its rule id.

---

## Part 6: Docs

- New decision: LLM-driven interviewer with guardrails replaces the fixed question flow (supersedes the earlier follow-up decisions).
- New decision: possible causes allowed from a curated, hedged guide; diagnosis and medications still never allowed.
- New decision: emergency split into `CALL_911` and `GO_TO_ER`.
- Update the context graph with `symptom_guide.json`, the interviewer, the question guard and the new outcomes.
