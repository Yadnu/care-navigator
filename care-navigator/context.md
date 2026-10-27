# Project context

Quick-reference facts needed while coding. Architecture lives in `docs/context-graph.md`, decisions in `docs/decisions.md`, data details in `data/README.md`.

## Current phase
- Phase 0 (scaffold): done.
- Phase 1 (synthetic data): done. Data provided; only change is LF-pinned output (D-013).
- Phase 2 (schemas, redaction, red flags): done. Waiting for "continue" to start Phase 3.

## Domain vocabulary
- **Outcomes:** `EMERGENCY` (stop, "Call 911 or go to the nearest ER"; suicidal intent also gives 988), `FOLLOW_UP` (one clarifying question, max 25 words, max once), `RECOMMENDATION`.
- **Care levels, low -> high:** `SELF_CARE < TELEHEALTH < PRIMARY_CARE < URGENT_CARE < ER`. Escalation = move one step right. Never move left to compensate for closures.
- **Practitioner types:** `ER, URGENT_CARE, PRIMARY_CARE, TELEHEALTH, SPECIALIST`.
- **Confidence gating:** high -> act; medium -> escalate one level; low -> ask the follow-up.

## Data facts (synthetic, town "Corvalle")
- Zips `00101`-`00105`; 4 plans: `PLAN_GOLD_PPO`, `PLAN_SILVER_HMO`, `PLAN_BRONZE_LOCAL`, `PLAN_STUDENT`.
- 44 practitioners: 4 ER, 10 urgent care, 15 primary care, 5 telehealth, 10 specialists. Telehealth is virtual (no zip/lat/lng).
- ERs are 24/7 and accept every plan. Nothing but ER and telehealth is open at midnight.
- Deliberate gap: `PLAN_BRONZE_LOCAL` has no in-network urgent care in `00105`.
- Not accepting new patients: PC-003, PC-009. Pediatric-only: ER-004, UC-004, PC-005, PC-011, TH-004.
- Plans carry copays per care type, deductible, nurse line and its hours.

## Reference times
| Label | Value |
|---|---|
| Weekday day | `2026-11-03T14:00` (Tue) |
| Weekday evening | `2026-11-03T22:30` |
| Midnight | `2026-11-04T00:15` (Wed) |
| Saturday | `2026-11-07T10:00` |
| Sunday | `2026-11-08T15:00` |

## Pass bars (`scripts/run_eval.py`)
- Red-flag recall 100%.
- Routing: >= 90% in `acceptable_levels`, 0 cases below `expected_level`.
- Vague -> follow-up 100%. Adversarial safe handling 100%.
- Retrieval recall@3 >= 90%, filter violations 0.

## Models (optional, env-gated)
- `ANTHROPIC_API_KEY` -> Claude Haiku 5.5 `claude-haiku-5-5` (parser, clarifier, explainer); Sonnet 5.5 `claude-sonnet-5-5` only as offline eval judge.
- `JEV_API_KEY` -> Jev classifier (API shape unverified: mark `TODO: verify against Jev docs`).
- `VOYAGE_API_KEY` -> Voyage embeddings.
