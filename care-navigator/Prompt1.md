Two changes. Follow TDD and the accuracy rules in PROMPT.md section 2.4. Read data/README.md, docs/context-graph.md and docs/decisions.md first. Stop after each part, paste the pytest and make eval output, and wait for "continue".

==================================================================
PART A: Ask for more details instead of stopping at keywords
==================================================================

Problem: "I have pain in my left hand ever since I played volleyball" returns EMERGENCY. The system jumps to 911 on keywords. It should have a short conversation first, and only stop immediately for unmistakable emergencies.

A1. Reproduce first. Run that input, open its trace, and paste the exact step that fired (rule id, matched phrase, fuzzy score or Jev probability). Do not guess the cause.

A2. Three-tier red flags (replace the current keyword stop):
- Tier 1, IMMEDIATE EMERGENCY (no questions): only unmistakable phrases and combinations. Examples: crushing or squeezing chest pain, chest pain with sweating or shortness of breath, can't breathe or lips turning blue, face drooping, slurred speech with arm weakness, worst headache of my life with sudden onset, bleeding that won't stop, throat or tongue swelling, unresponsive, seizure, suicidal intent (show 988 and 911), infant under 3 months with fever.
- Tier 2, POSSIBLE EMERGENCY (ask safety questions first): a single weak signal, such as arm, jaw or back pain alone, "short of breath" without context, headache, abdominal pain, dizziness, vomiting, or Jev emergency probability between 0.5 and 0.8. Ask up to 2 targeted safety questions from the question bank. Any "yes" to a danger sign -> EMERGENCY. Otherwise continue routing.
- Tier 3, ROUTINE: no danger signs. Go to normal clarification and routing.
- Jev alone triggers EMERGENCY only at probability >= 0.8 with high confidence. Thresholds live in config.py.
- Fuzzy matching: correct typos per word (threshold >= 90), then exact phrase match. No partial_ratio on full sentences.
- Injury context (played, fell, twisted, lifted, hit, after exercise or sports) points to injury rules unless a Tier 1 sign is also present.

A3. Multi-turn clarification:
- New outcome types: SAFETY_CHECK (Tier 2 question) and FOLLOW_UP (missing detail question), alongside EMERGENCY and RECOMMENDATION.
- Ask ONE question at a time, maximum 3 questions per conversation (safety questions count). Choose the most important missing slot for the symptom category.
- Questions come ONLY from data/question_bank.json (create it, synthetic: true). Each entry: slot, question text, quick-reply options, which categories it applies to, and which answers are danger signs. Claude may rephrase a question for natural tone but may not invent new questions or add medical content. The offline mode uses the bank text as-is.
- Slots to include at minimum: main_symptom, duration, severity_now, location_detail, injury_mechanism, swelling_or_deformity, can_use_or_bear_weight, associated_cardiac_symptoms (chest pain or pressure, shortness of breath, sweating, nausea), headache_onset, breathing_at_rest, fluids_kept_down, urine_output, fever_value, child_age, abdominal_location_and_trend.
- Keep conversation state per session. After each answer, re-run the pipeline on the full conversation. Answers go through redaction and the parser's evidence checks like the first message.
- Stop asking when the care-level rules have what they need, or after 3 questions. Remaining uncertainty escalates one level (fail toward more care).
- At any point, a Tier 1 sign in any answer -> EMERGENCY immediately.
- UI: show the question with quick-reply buttons plus a free-text box, the conversation history, and a "Skip, just tell me where to go" button that routes with what is known (escalating one level).

A4. Eval sets (write tests first, all synthetic: true):
- data/eval/near_misses.jsonl (20+ non-emergencies sharing words with red flags), each with expected_outcome and acceptable_levels. Include: "pain in my left hand since I played volleyball", "sore left arm after my flu shot", "left wrist hurts after I fell skating", "chest muscles sore after bench press yesterday, no shortness of breath", "short of breath after running, normal again in 5 minutes", "headache after a long day at the screen", "cut my hand, bleeding stopped with pressure", "stomach ache after spicy food, mild".
- data/eval/conversations.jsonl (12+ scripted conversations): first message, scripted answers keyed by slot, expected final outcome, acceptable levels, max questions, and slots that must be asked. Include:
  1. volleyball hand pain -> asks injury/swelling/use -> URGENT_CARE
  2. "my arm hurts" + "no chest pain, lifted boxes" -> PRIMARY_CARE or URGENT_CARE
  3. "my arm hurts" + "my chest feels tight and I'm sweating" -> EMERGENCY
  4. "I feel off" -> "throwing up since dinner" -> "can keep water down", at 00:15 -> TELEHEALTH
  5. "headache" -> "came on slowly after work" -> SELF_CARE or TELEHEALTH
  6. "headache" -> "worst of my life, came on suddenly" -> EMERGENCY
  7. "stomach pain" -> "lower right, getting worse, fever" -> EMERGENCY
  8. "stomach pain" -> "upper, burning, after spicy food" -> TELEHEALTH or PRIMARY_CARE
  9. "short of breath" -> "only after stairs, fine at rest" -> PRIMARY_CARE
  10. "short of breath" -> "yes, even sitting still" -> EMERGENCY
  11. "my kid has a fever" -> "8 months old, 101, drinking well" -> URGENT_CARE or TELEHEALTH
  12. "crushing chest pain" -> EMERGENCY with 0 questions
- Add to make eval: false-emergency rate on near_misses and routing cases (target 0%), red-flag recall (must stay 100%), conversation accuracy (target >= 90%), average questions asked (report it), and conversations exceeding 3 questions (must be 0).

A5. Docs: mark D-003 as superseded by a new decision (three-tier red flags, up to 3 questions from a question bank). Update the context graph.

==================================================================
PART B: More detailed insurance data, more plans, more zip codes
==================================================================

Extend data/generate.py (keep it deterministic and keep every existing ID and existing test passing). Everything stays fictional and synthetic: true.

B1. Plans: 10 total. Keep the 4 existing IDs and add:
- PLAN_PLATINUM_PPO (Evergreen Health, same network as Gold)
- PLAN_HSA_BRONZE_HMO (Summit Care, high deductible, HSA eligible, same network as Silver HMO)
- PLAN_COMMUNITY_MEDICAID (fictional Medicaid-style: $0 premium and deductible, tiny copays, referral required, narrower network)
- PLAN_SENIOR_ADVANTAGE (fictional Medicare Advantage-style HMO, age 65+, $0 premium, OOP max)
- PLAN_MARKETPLACE_EPO (fictional individual marketplace silver EPO)
- SELF_PAY (no insurance, cash prices per service)

Every plan has these fields:
id, name, carrier, plan_type, metal_tier, network_name, plan_year, eligibility, premium_monthly_usd, deductible_usd {individual, family}, out_of_pocket_max_usd {individual, family}, coinsurance_pct, services {TELEHEALTH, PRIMARY_CARE, SPECIALIST, URGENT_CARE, ER, AMBULANCE, LAB, XRAY, ADVANCED_IMAGING: {copay_usd, deductible_applies, coinsurance_applies, note}}, er_copay_waived_if_admitted, out_of_network {covered, coinsurance_pct, note}, emergency_rule ("ER covered at in-network cost sharing anywhere, simplified"), referral_required_for_specialist, prior_auth_required_for [], hsa_eligible, telehealth_partner_ids [], nurse_line, nurse_line_hours, member_services, cash_prices_usd (SELF_PAY only), copays_usd (flat view for the 5 care types, kept for backward compatibility).

B2. Zip codes: 12 total in 3 fictional towns.
- Corvalle (urban): existing 00101 to 00105.
- Brightwater (suburban, about 20 km away): 00201 to 00204, with 1 ER, 5 urgent care, 12 primary care, 4 specialists.
- Pinecrest (rural, about 35 km away): 00301 to 00303, with 1 critical access hospital ER, 1 urgent care with short hours, 1 primary care per zip (some not accepting new patients), no specialists.
- Add area_type (urban, suburban, rural) to each zip.

B3. Practitioners: keep the 44 existing records; generate new ones from varied bio templates so semantic search still matters. Add TH-006 (senior-focused 24/7 telehealth) and TH-007 (Medicaid-style plan's 24/7 telehealth). Network rules:
- Platinum is accepted wherever Gold is; HSA Bronze wherever Silver HMO is.
- Medicaid-style: a deliberate subset (about half of primary care and urgent care, few specialists).
- Senior plan: adult and all-ages providers only, never pediatric-only.
- SELF_PAY: accepted everywhere except plan-owned telehealth (TH-002, TH-003, TH-007).
- Every ER accepts every plan. NightOwl (TH-001) accepts every plan, including SELF_PAY at $59.
- Every new urgent care, primary care and specialist closes by 21:00, so at midnight only ERs and telehealth are open.

B4. Coverage gaps: compute, for each zip and plan, whether there is in-network urgent care, primary care (accepting new patients) and a specialist within 15 km. Save to data/coverage_gaps.json. Gaps must exist only in rural Pinecrest, for the Medicaid-style plan's specialists, and the existing Bronze 00105 in-zip urgent care gap. Corvalle and Brightwater must have no urgent care or primary care gaps for commercial plans.

B5. Eval additions:
- routing_cases: self-pay with a tight budget, midnight food poisoning in 00101 -> TELEHEALTH (NightOwl, $59 cash); rural ankle sprain in 00303 on Bronze -> acceptable URGENT_CARE, TELEHEALTH or PRIMARY_CARE; 72-year-old with a cough on the Senior plan -> PRIMARY_CARE; child ear infection on the Medicaid-style plan in 00201 -> URGENT_CARE.
- retrieval_queries: 8+ new queries in Brightwater and Pinecrest with expected_ids, including one that returns empty because of a rural gap.

B6. Tests first (extend tests/test_data.py): plan schema with every field above; every plan has every service; copays_usd matches services; Platinum/HSA network rules hold; no pediatric-only provider accepts the Senior plan; every ER and NightOwl accept every plan; computed gaps match coverage_gaps.json and the rules in B4; the midnight rule still holds; all retrieval expected_ids pass the hard filters.

B7. Costs: costs.py shows the plan's cost for the service, says when the deductible applies or the copay is waived if admitted, and shows cash prices for SELF_PAY. Update data/README.md with a plan comparison table and the gap summary. Log decisions and update the context graph.