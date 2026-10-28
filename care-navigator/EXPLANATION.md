# Care Navigator — take-home explanation

## Choose your problem

**A. People don't know where to go for care, or what it will cost.** My roommate had
food poisoning at midnight; money was tight, and we couldn't tell whether he needed the
ER, which places were even open, or which ones our insurance would cover. This hits
anyone without a nurse line memorized or a clinician on speed dial — which is most
people, especially late at night or on a new plan. Left unsolved, people either under-react
(skip care they need) or over-react (an unnecessary, expensive ER visit), and either way they
often guess at the cost until the bill arrives.

**B. Freelancers with irregular income don't know how much to set aside for taxes.** Based
on my sister's freelance work: US freelancers have no employer withholding and must pay
estimated taxes quarterly. Left unsolved, this produces large year-end tax bills, underpayment
penalties, and missed deductions, because the income that should have been set aside each
month was already spent.

**C. Corporate apparel orders arrive incomplete.** Based on AEVIQ, my sister's custom apparel
business: HR collects sizes, styles and names from every employee, and the manufacturer plans
production from that list. Wrong sizes, misspelled names and lost special requests surface only
*after* printing, which means reprints, wasted fabric and missed deadlines.

### Why A

I chose A. It's the one I've personally lived through at the worst possible moment to be
figuring things out — sick, tired, and doing mental math on a copay at 1 a.m. — and the stakes
of getting it wrong run in both directions: too cautious wastes money people don't have, too
casual risks a real emergency. B and C are real and I believe them (secondhand, from my sister),
but I haven't personally hit either one, so my read on their true frequency and pain is weaker.

What I've *observed* directly: the decision involves at least three independent facts (urgency,
availability, cost) that live in different places (your own judgment, a directory, your plan
document), and getting any one wrong changes the right answer. What I'm *assuming*: that most
people in this situation don't have a go-to source for all three at once, and that this gap is
common rather than a one-off. I didn't survey anyone else to confirm the assumption — that's
the first thing I'd check before investing further (see "What would make me decide this isn't
worth solving" below).

## Develop your approach

**Today**, people handle this by calling a friend, searching the web for "urgent care near
me open now," calling their insurer's member line (long hold times), or just going to the ER
because it's the only option they're sure is open and sure is covered in an emergency. None of
those sources combine urgency + availability + cost in one place, so the effort of checking all
three usually means people check none of them and guess.

**A better outcome** looks like: describe what's wrong in plain words, and get back one of three
things — an unambiguous "this is an emergency, go now," a single clarifying question if the
system genuinely can't tell yet, or a recommended level of care with specific, open,
in-network options and what they'll likely cost. Critically, the system should always fail
*toward* more care, never less, when it's unsure.

**Direction and first step.** The full opportunity is a general care-navigation assistant that
also books appointments, tracks a deductible in real time, and learns a person's plan over
time. The smallest useful first step is the triage-and-routing decision itself: given symptoms,
severity, a zip code, a plan and the time of day, decide the level of care and show the nearest
open, in-network options with a cost estimate. That's narrow enough to build and test in hours,
and it's the one decision that, if wrong, has the worst consequences (sending someone to urgent
care when they need the ER, or to the ER when urgent care would do).

**Alternative considered.** I considered building this as a pure checklist/decision-tree UI
with no language model at all — the person clicks through "fever? yes/no," "vomiting? yes/no,"
etc. I didn't choose it because free text is how people actually describe symptoms ("can't keep
anything down since lunch" is three facts at once: duration, GI symptom, severity), and forcing
a rigid checklist either loses that detail or turns into a 20-click form nobody finishes. The
tradeoff is real, though: free text needs a parser and a safety net, which is most of the
engineering effort in this prototype (see "Where AI helps" below). A rigid checklist would have
been safer to build quickly and easier to audit; I judged the better user experience worth the
extra work, with the safety net (deterministic rules, never the model, make the final call) as
the mitigation.

**Where AI vs. conventional software vs. a process change helps.** This is squarely a problem
for a mix of the first two, not a process change — there's no team or workflow to change, only
software that doesn't exist yet. Conventional software (versioned, tested rule tables) makes the
one decision that matters — the care level — because it must be deterministic, explainable, and
auditable; a language model is used only where natural language is unavoidable: reading free-text
symptoms, holding a short conversation, and writing the final explanation. Retrieval (not a model)
finds the actual practitioners, so a hallucinated clinic or phone number is structurally
impossible. This split is the one architectural decision I'd defend hardest in this prototype.

**How the first step connects to the broader opportunity.** Once triage-and-routing works and is
trusted, the same conversation state (what the person described, what's ruled out, what plan
they're on) is exactly the input a booking integration or a running deductible tracker would
need — this prototype's `ConversationState` and cost-estimate code are already shaped for that,
even though booking and real-time deductible tracking are both deferred (see below).

**What I'd need to learn, and when to stop.** Before building further, I'd want to validate the
assumption above with actual users: do people really lack a combined urgency+availability+cost
view, or do most already have a workaround (a trusted nurse line, a go-to clinic) that makes this
redundant for them? I'd also want real triage-outcome data to check the rules against, since
"simplified, not clinically validated" is fine for a prototype but not for anything a real person
acts on. I'd decide this isn't worth pursuing further if either came back negative — if most
people already have a working triage habit, or if getting clinically credible routing rules
turns out to require partnerships (a telehealth or insurer backend) I can't realistically get.

## Build a working prototype

**Care Navigator**: a person describes symptoms in plain words with a severity (1-10), zip
code, insurance plan and the time of the request. The system returns one of: an emergency
instruction (call 911 / go to the nearest ER), one clarifying question, or a recommendation
— a care level, the nearest open in-network practitioners, a cost estimate, up to two
hedged possible causes, and a plain-English explanation. The one-sentence core workflow:
**realistic symptom description in → safe, costed, in-network care recommendation out**, and
the core problem-solving logic (red-flag detection, the care-level rules, retrieval, cost
calculation) genuinely runs — none of it is mocked.

- **Representative use case**: "Sore throat and fever for two days" → after a couple of
  interviewer questions, **Urgent care**, two nearby in-network practitioners, $75 copay,
  typical cost $150-$300, and a disclaimer.
- **Difficult / invalid case**: "Mild chest tightness, probably nothing" (severity 2 — an
  understated description of a possible cardiac symptom) → the red-flag rules override the low
  self-reported severity and return **CALL_911** immediately, no questions asked. A second
  invalid-input case is exercised directly in the test suite and the eval runner: an empty zip
  code, an unrecognized insurance plan, and adversarial input (a prompt-injection attempt, HTML
  injection, a 2,000+ character wall of text) are all handled without crashing and without
  changing the safety outcome.

Run it with `cd care-navigator && make demo` (or `python cli.py --offline`) for both cases
above plus four more; see [`README.md`](care-navigator/README.md) for full setup, dependencies,
sample data and the eval results (`make eval`, 12 pass bars, all met).

**Synthetic data and mocked integrations, clearly labeled**: every practitioner, plan, zip code
and phone number is fictional (`"synthetic": true` on every record); the symptom-to-cause
"possible causes" shown to the person come only from a small curated guide, never invented by a
model; Claude, the classifier ("Jev") and the embedding model are each optional and the system
runs fully offline by default with no API keys, falling back automatically if a live provider
fails.

## How AI was used

Built with Claude Code from a written plan, phase by phase, test-driven (a failing test
committed before the code that makes it pass). Output was checked by: running the real pipeline
and eval suite after every change (not just reading diffs or trusting a green checkmark); one
round of live verification against the real Claude/Jev/Voyage APIs that caught problems the
offline tests alone could not; and reading actual output and trace files by eye, which caught a
guard rule blocking a legitimate facility name and a misleading internal label. A second Claude
Code session finished an in-progress refactor this session had left partly broken, and found two
real behavior regressions in the process — a rule-ordering bug that silently downgraded several
routing decisions, and a fuzzy-text-matching false positive — by running the actual pipeline
before and after, not by inspecting the diff. Full details, including the specific decisions
logged along the way, are in [`README.md`](care-navigator/README.md#how-ai-was-used-and-how-the-output-was-checked).

**Implemented**: the full pipeline above, red-flag safety screening, the interviewer
conversation, in-network retrieval with hard filters, cost estimates for ten insurance plans,
a Streamlit app, a CLI demo and an eval runner, 1,198 tests.

**Mocked or simplified**: all data is synthetic; offline fallbacks exist for every model
(keyword heuristics, a regex parser, TF-IDF search, template text) so the system never requires
an API key; care-level rules are simplified and explicitly not clinically validated.

**Deferred**: a chat-style UI redesign and an updated architecture doc for the most recent
change (both out of scope for the time box); real provider directories and live hours; booking;
a running deductible tracker; non-English input beyond a generic follow-up question.

## Time spent and what's next

About 5 hours total — over the suggested 2-4 hour budget. Most of it built the base prototype
and its two extensions; the overrun came from a self-initiated conversational-triage
improvement (replacing a fixed Q&A flow with a guided interviewer), started late and needing
far more follow-through than planned. Full breakdown and what I'd investigate next
(re-verifying against live APIs, finishing the deferred UI/doc work, auditing the rule table
for other ordering bugs) are in [`README.md`](care-navigator/README.md#time-spent).
