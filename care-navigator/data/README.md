# Synthetic data

Everything in this folder is fictional and every record carries `"synthetic": true`. The town of **Corvalle**, the zip codes `00101` to `00105`, the insurance carriers, practitioners, phone numbers (`555-01xx`) and addresses are all invented. The coordinates sit in rural Kansas so they map to no real clinic. Routing labels are simplified and **not clinically validated**.

Regenerate with `python data/generate.py` (deterministic, seed `20261027`). Validate with `pytest tests/test_data.py`, or `python tests/test_data.py` if pytest isn't installed.

## Files

| File | Records | What it holds |
|---|---|---|
| `zips.json` | 5 | Zip code, neighborhood, centroid lat/lng |
| `plans.json` | 4 | Insurance plans: carrier, tier, network type, deductible, coinsurance, copay per care type, referral rule, nurse line |
| `practitioners.json` | 44 | 4 ER, 10 urgent care, 15 primary care, 5 telehealth, 10 specialists |
| `cost_ranges.json` | 1 | Typical total cost before insurance by care type |
| `eval/red_flags.jsonl` | 40 | Emergency phrasings: direct, typos, understatement, indirect. Expected `EMERGENCY` |
| `eval/routing_cases.jsonl` | 40 | Cases with time, zip, plan, `expected_level` and `acceptable_levels` |
| `eval/vague.jsonl` | 15 | Too vague to judge. Expected `FOLLOW_UP` |
| `eval/adversarial.jsonl` | 10 | Prompt injection, PII, empty, too long, Spanish, off-topic, HTML |
| `eval/retrieval_queries.jsonl` | 21 | Parsed query + filters, with `expected_ids` |

## Insurance plans

| Plan | Type | Deductible | Telehealth | Primary | Urgent care | Specialist | ER | Notes |
|---|---|---|---|---|---|---|---|---|
| `PLAN_GOLD_PPO` Evergreen Health Gold PPO | PPO | $1,000 | $0 | $25 | $50 | $50 | $250 | Own 24/7 telehealth (TH-002) |
| `PLAN_SILVER_HMO` Summit Care Silver HMO | HMO | $3,000 | $15 | $35 | $75 | $70 | $400 | Specialist needs referral; telehealth 7 am to 10 pm only |
| `PLAN_BRONZE_LOCAL` Harbor Bronze Local | EPO, narrow | $7,000 | $30 | $60 | $120 | $100 | $750 | **No in-network urgent care in 00105** (deliberate gap); nurse line 8 am to 8 pm |
| `PLAN_STUDENT` Campus Student Health Plan | PPO | $500 | $0 | $20 | $40 | $40 | $200 | Campus 24/7 telehealth (TH-005) |

## Practitioner fields

`id, name, credential, facility_name, type (ER | URGENT_CARE | PRIMARY_CARE | TELEHEALTH | SPECIALIST), specialties[], conditions_treated[], languages[], patient_ages (all | adults | children), accepting_new, hours {mon..sun: "HH:MM-HH:MM" | "24h" | null}, accepted_plans[], virtual, zip, address, lat, lng, phone, bio, synthetic`

Telehealth records are virtual: `zip`, `lat` and `lng` are null and they serve every zip.

## Rules built into the data (tested)

- ERs are open 24/7 and accept every plan.
- No urgent care, primary care or specialist is open after 21:00. **At midnight only ERs and telehealth are open**, which makes the midnight food poisoning case realistic.
- Every plan has at least one 24/7 telehealth option (NightOwl Virtual Care accepts all four).
- Every zip has in-network urgent care and primary care for every plan, except the deliberate gap: Bronze in 00105 has no urgent care.
- Some primary care providers are not accepting new patients (PC-003, PC-009).
- Pediatric-only providers: ER-004, UC-004, PC-005, PC-011, TH-004.
- Spanish-speaking options exist in most areas for retrieval tests.

## Care levels and outcomes

Levels from lowest to highest acuity: `SELF_CARE < TELEHEALTH < PRIMARY_CARE < URGENT_CARE < ER`.
Outcomes: `EMERGENCY`, `FOLLOW_UP`, `RECOMMENDATION`.

A routing case passes when the system's level is in `acceptable_levels` and never below `expected_level`.

## Reference times

| Label | Value | Why |
|---|---|---|
| Weekday day | `2026-11-03T14:00` (Tue) | Everything open |
| Weekday evening | `2026-11-03T22:30` (Tue) | Urgent care and primary care closed |
| Midnight | `2026-11-04T00:15` (Wed) | Only ER and 24/7 telehealth open |
| Saturday | `2026-11-07T10:00` | Only PC-010 primary care open |
| Sunday | `2026-11-08T15:00` | Urgent care open, primary care closed |

## Retrieval filters used by `expected_ids`

A practitioner is a candidate when: type matches the care level, the plan is accepted, it is open at the request time, it accepts new patients (primary care and specialists), it serves the age group, and (unless virtual) it is within `max_distance_km` of the zip centroid. A TF-IDF baseline over bios, specialties and conditions already finds the first expected id in the top 3 for all 20 non-empty queries; hybrid search plus reranking should match or beat that.
