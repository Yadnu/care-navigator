# Synthetic data

Everything in this folder is fictional and every record carries `"synthetic": true`. The towns of **Corvalle**, **Brightwater** and **Pinecrest**, the zip codes `00101` to `00303`, the insurance carriers and plans, practitioners, phone numbers (`555-01xx`, `1-800-555-0xxx`) and addresses are all invented. The coordinates sit in rural Kansas so they map to no real clinic. Routing labels and plan rules are simplified and **not clinically or actuarially validated**.

Regenerate with `python data/generate.py` (deterministic, seed `20261027`; the Part B data lives in `expansion.py`, the question bank in `question_bank_src.py`, the eval sets in `eval_sets.py`). Validate with `pytest tests/test_data.py tests/test_data_insurance.py tests/test_generate.py`.

## Files

| File | Records | What it holds |
|---|---|---|
| `zips.json` | 12 | Zip code, neighborhood, town, `area_type` (urban, suburban, rural), centroid lat/lng |
| `plans.json` | 10 | Plans with premium, deductible and out-of-pocket max (individual/family), coinsurance, per-service cost sharing for 9 services, out-of-network rules, referral and prior-auth rules, HSA flag, telehealth partners, nurse line and member services; `copays_usd` is the flat 5-care-type view kept for older code |
| `practitioners.json` | 73 | Corvalle: 4 ER, 10 urgent care, 15 primary care, 10 specialists. Brightwater: 1 ER, 5 urgent care, 12 primary care, 4 specialists. Pinecrest: 1 critical access ER, 1 urgent care, 3 primary care. 7 telehealth |
| `coverage_gaps.json` | 120 rows, 34 gaps | For each zip and plan: in-network urgent care, primary care (accepting new) and a specialist within 15 km, plus urgent care in the zip itself |
| `cost_ranges.json` | 1 | Typical total cost before insurance by care type |
| `question_bank.json` | 15 | Every question the system may ask, with quick replies and danger answers |
| `eval/red_flags.jsonl` | 40 | Emergency phrasings: direct, typos, understatement, indirect. Expected `EMERGENCY` |
| `eval/routing_cases.jsonl` | 44 | Cases with time, zip, plan, `expected_level` and `acceptable_levels` |
| `eval/vague.jsonl` | 15 | Too vague to judge. Expected a question |
| `eval/adversarial.jsonl` | 10 | Prompt injection, PII, empty, too long, Spanish, off-topic, HTML |
| `eval/retrieval_queries.jsonl` | 32 | Parsed query + filters, with `expected_ids` |
| `eval/near_misses.jsonl` | 21 | Not emergencies but share words with red flags |
| `eval/conversations.jsonl` | 12 | Scripted multi-turn conversations with answers by slot |

## Towns and zips

| Town | Area type | Zips | Distance from Corvalle |
|---|---|---|---|
| Corvalle | urban | 00101 to 00105 | - |
| Brightwater | suburban | 00201 to 00204 | about 20 km north |
| Pinecrest | rural | 00301 to 00303 | about 35 km south |

## Plan comparison

Per-visit amounts are what the member pays for an in-network visit (cash price for self-pay). "Ded." means the deductible applies to that service first.

| Plan | Type | Premium / month | Deductible (ind / fam) | OOP max (ind) | Telehealth | Primary | Urgent care | Specialist | ER | Notes |
|---|---|---|---|---|---|---|---|---|---|---|
| `PLAN_GOLD_PPO` Evergreen Health Gold | PPO, gold | $520 | $1,000 / $2,000 | $5,000 | $0 | $25 | $50 | $50 | $250, waived if admitted | Own 24/7 telehealth (TH-002) |
| `PLAN_SILVER_HMO` Summit Care Silver | HMO, silver | $410 | $3,000 / $6,000 | $8,000 | $15 | $35 | $75 | $70, referral | $400 (ded.), waived if admitted | Telehealth 7 am to 10 pm (TH-003) |
| `PLAN_BRONZE_LOCAL` Harbor Bronze Local | EPO, bronze, narrow | $290 | $7,000 / $14,000 | $9,200 | $30 | $60 | $120 | $100 (ded.) | $750 (ded., 40%) | **No in-network urgent care in 00105**; nurse line 8 am to 8 pm |
| `PLAN_STUDENT` Campus Student Health | PPO | $180 | $500 / $1,000 | $3,000 | $0 | $20 | $40 | $40 | $200, waived if admitted | Campus 24/7 telehealth (TH-005) |
| `PLAN_PLATINUM_PPO` Evergreen Health Platinum | PPO, platinum | $720 | $250 / $500 | $3,000 | $0 | $15 | $30 | $30 | $150, waived if admitted | Same network as Gold |
| `PLAN_HSA_BRONZE_HMO` Summit Care HSA Bronze | HMO, bronze, HSA | $260 | $4,000 / $8,000 | $7,500 | ded. | ded. | ded. | ded., referral | ded. | Full cost until the deductible, then 30%; same network as Silver |
| `PLAN_COMMUNITY_MEDICAID` Community Care | Medicaid-style | $0 | $0 | $100 | $0 | $2 | $3 | $3, referral | $8 | Narrower network: about half of primary and urgent care, one specialist; own 24/7 telehealth (TH-007) |
| `PLAN_SENIOR_ADVANTAGE` Golden Years | Medicare Advantage-style HMO, 65+ | $0 | $0 | $4,500 | $0 | $0 | $45 | $40, referral | $95, waived if admitted | Adult and all-ages providers only; senior telehealth (TH-006) |
| `PLAN_MARKETPLACE_EPO` Prairie Marketplace Silver | EPO, silver | $410 | $4,500 / $9,000 | $8,700 | $10 | $40 | $75 | $80 | $500 (ded., 30%) | Individual marketplace; same network as Silver |
| `SELF_PAY` (no insurance) | self-pay | - | - | - | $59 cash | $140 cash | $175 cash | $220 cash | $1,400 cash | Accepted everywhere except plan-owned telehealth (TH-002, TH-003, TH-007) |

Every plan also lists ambulance, lab, X-ray and advanced imaging cost sharing, out-of-network rules, prior authorization and member services. Emergency care is covered at in-network cost sharing at any ER (simplified).

## Network rules (tested)

- Every ER and NightOwl Virtual Care (TH-001) accept every plan, including self-pay.
- Platinum is accepted wherever Gold is; HSA Bronze and the marketplace EPO wherever Silver is.
- The Medicaid-style network is a deliberate subset: about half of primary care and urgent care, and one specialist (SP-008).
- The senior plan is never accepted by pediatric-only providers, except the pediatric ER (every ER accepts every plan; the age filter keeps adults out). See D-045.
- Self-pay is accepted everywhere except plan-owned telehealth (TH-002, TH-003, TH-007).

## Coverage gaps (15 km, `coverage_gaps.json`)

| Where | Plan | Missing within 15 km |
|---|---|---|
| Pinecrest (00301 to 00303) | every plan except Student and Medicaid-style | specialist |
| Pinecrest (00301 to 00303) | Student, Medicaid-style | urgent care and specialist |
| Brightwater (00201 to 00204) | Medicaid-style | specialist |

There are no urgent care or primary care gaps for commercial plans in Corvalle or Brightwater. Separately, Bronze still has **no in-network urgent care inside 00105** (the original demo gap); the nearest is 4.8 km away, so it is not a 15 km gap, but it is outside the app's 3 km "nearby" radius.

## Rules built into the data (tested)

- ERs are open 24/7. No urgent care, primary care or specialist is open after 21:00, so **at midnight only ERs and telehealth are open**.
- Every plan has at least one 24/7 telehealth option (NightOwl accepts all ten).
- Some primary care providers are not accepting new patients (PC-003, PC-009, PC-023, PC-029).
- Pediatric-only providers: ER-004, UC-004, UC-013, PC-005, PC-011, PC-018, TH-004.
- Spanish-speaking options exist in most areas for retrieval tests.

## Care levels and outcomes

Levels from lowest to highest acuity: `SELF_CARE < TELEHEALTH < PRIMARY_CARE < URGENT_CARE < ER`.
Outcomes: `EMERGENCY`, `SAFETY_CHECK`, `FOLLOW_UP`, `RECOMMENDATION`.

A routing case passes when the system's level is in `acceptable_levels` and never below `expected_level`.

## Reference times

| Label | Value | Why |
|---|---|---|
| Weekday day | `2026-11-03T14:00` (Tue) | Everything open |
| Weekday evening | `2026-11-03T22:30` (Tue) | Urgent care and primary care closed |
| Midnight | `2026-11-04T00:15` (Wed) | Only ER and 24/7 telehealth open |
| Saturday | `2026-11-07T10:00` | Only PC-010 and PC-018 primary care open |
| Sunday | `2026-11-08T15:00` | Urgent care open, primary care closed |

## Retrieval filters used by `expected_ids`

A practitioner is a candidate when: type matches the care level, the plan is accepted, it is open at the request time, it accepts new patients (primary care and specialists), it serves the age group, and (unless virtual) it is within `max_distance_km` of the zip centroid.
