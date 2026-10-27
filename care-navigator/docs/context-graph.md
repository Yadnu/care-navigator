# Context graph

Living map of the system. Read this and `decisions.md` before any task; update it at the end of every phase.

Last updated: 2026-10-27, end of Phase 8 (all phases done).

## Request flow

```mermaid
flowchart TD
    REQ[Request: text, severity, zip, plan, time] --> VAL[validate<br/>models.py]
    VAL -->|empty or too long| MSG[Clear message<br/>no outcome]
    VAL -->|unknown zip/plan| WARN[errors listed;<br/>care level still given] --> RED
    VAL --> RED[redact.py]
    RED --> RF1[redflags.py<br/>red_flags.yaml]
    RED --> JEV1[jev_client.py<br/>is_emergency<br/>OfflineJev / HttpJev]
    LEX[lexicon.py] -.-> JEV1
    LEX -.-> PARSE
    RF1 -->|hit| EMER([EMERGENCY: call 911 / 988])
    JEV1 -->|hit| EMER
    RF1 --> PARSE[parser.py<br/>OfflineParser / ClaudeParser]
    JEV1 --> PARSE
    PARSE --> RF2[redflags.py<br/>recheck parsed fields]
    RF2 -->|hit| EMER
    RF2 --> VAGUE{too vague or<br/>low confidence?}
    VAGUE -->|yes, first time| CLAR[clarifier.py]
    CLAR --> FU([FOLLOW_UP question])
    FU -.->|answer, max once| REQ
    VAGUE -->|no, or still vague after follow-up: escalate| ENG[care_engine.py<br/>care_rules.yaml<br/>first match + gating]
    ENG --> HRS{anything open now<br/>at this level?}
    HRS -->|no| AH[rule after_hours level,<br/>then step up; never self-care]
    AH --> RET
    HRS -->|yes| RET
    RET[retrieval/retriever.py<br/>query from parsed report]
    DATA[data.py<br/>loaders + is_open] -.-> HRS
    DATA -.-> RET
    RET --> FIL[hard filters: type, plan, open now,<br/>new patients, age, distance] --> HYB[embeddings + vector_store<br/>+ bm25] --> RRF[fusion.py RRF k=60<br/>top 10] --> RR[Jev rerank<br/>tie-break: distance]
    FIL -->|no candidates| GAP[empty list:<br/>no in-network option nearby]
    GAP --> COST
    RR --> COST[costs.py]
    COST --> EXP[explainer.py<br/>Template / Claude]
    EXP --> GRD[guard.py]
    GRD -->|blocked| TPL[template explanation]
    TPL --> REC
    GRD --> REC([RECOMMENDATION])
    TRACE[(trace.py<br/>traces/*.json)]
    PIPE[pipeline.py] -.orchestrates.-> VAL
    PIPE -.provider down: offline fallback, simplified flag.-> JEV1
    PIPE -.records every step.-> TRACE
    APP[app.py Streamlit<br/>+ trace viewer] --> PIPE
    CLI[cli.py demo] --> PIPE
    EVAL[scripts/run_eval.py] --> PIPE
    TRACE -.-> APP

    subgraph data
      ZIPS[(zips.json)]
      PLANS[(plans.json)]
      PRACS[(practitioners.json)]
      COSTS[(cost_ranges.json)]
    end
    ZIPS --> VAL
    PLANS --> VAL
    PRACS --> RET
    ZIPS --> RET
    PLANS --> COST
    COSTS --> COST
```

## Nodes

| Node | Type | Depends on | Used by | Tests | Related decisions | Status |
|---|---|---|---|---|---|---|
| `navigator/__init__.py` | module | - | everything | `test_smoke.py` | - | done |
| `navigator/config.py` | config | env vars, `.env` (via `load_env_file`, entry points only) | redflags, jev_client, parser, care_engine (gating) | `test_config.py` | D-003, D-004, D-008, D-014, D-019, D-023, D-024 | done |
| `.env.example` / `.env` | config | - | `config.load_env_file` | `test_config.py` | D-024 | done (`.env` gitignored) |
| `tests/conftest.py` | test | pytest | every test | - | D-008, D-024 | done |
| `navigator/models.py` | module | pydantic | all modules | `test_models.py` | D-001, D-003 | done |
| `navigator/redact.py` | module | - | pipeline, trace | `test_redact.py` | D-009 | done |
| `navigator/redflags.py` + `red_flags.yaml` | module + config | rapidfuzz, pyyaml, config, models | pipeline | `test_redflags.py` | D-002, D-014, D-015, D-016, D-017 | done |
| `navigator/lexicon.py` | module | - | jev_client, parser | via `test_jev_client.py`, `test_parser.py` | D-021 | done |
| `navigator/jev_client.py` | module | config, lexicon, redflags.normalize, requests | pipeline, retriever, guard | `test_jev_client.py` | D-002, D-004, D-008, D-019, D-023 | done (all question types verified live) |
| `navigator/parser.py` | module | models, config, lexicon, redflags, anthropic | pipeline | `test_parser.py` | D-004, D-008, D-009, D-018, D-020 | done |
| `navigator/clarifier.py` | module | models, config, jev_client (guard), anthropic | pipeline | `test_clarifier.py` | D-003, D-004, D-028 | done |
| `navigator/care_engine.py` + `care_rules.yaml` | module + config | models, data, pyyaml | pipeline | `test_care_engine.py` | D-001, D-003, D-025, D-026, D-034, D-036 | done (23 rules, v1.2) |
| `navigator/data.py` | module | data/*.json, models | care_engine, retrieval | `test_care_engine.py` | D-027 | done |
| `navigator/retrieval/embeddings.py` | module | scikit-learn, requests, config | retriever | `test_retrieval.py` | D-008, D-030 | done (Voyage not run live) |
| `navigator/retrieval/vector_store.py` | module | numpy | retriever | `test_retrieval.py` | D-006, D-029 | done |
| `navigator/retrieval/bm25.py` | module | rank-bm25 | retriever | `test_retrieval.py` | D-006, D-030 | done |
| `navigator/retrieval/fusion.py` | module | config | retriever | `test_retrieval.py` | D-006 | done |
| `navigator/retrieval/retriever.py` | module | all retrieval, jev_client, data, models | pipeline, run_eval | `test_retrieval.py` | D-005, D-006, D-030, D-040 | done |
| `navigator/costs.py` | module | data, models, config | pipeline | `test_costs.py` | D-035 | done |
| `navigator/explainer.py` | module | models, care_engine (labels, rule reasons), anthropic | pipeline, guard | `test_explainer_guard.py` | D-004, D-007, D-034 | done (Claude not run live) |
| `navigator/guard.py` | module | jev_client, explainer, data | pipeline | `test_explainer_guard.py`, `test_pipeline.py` | D-007, D-034 | done |
| `navigator/trace.py` | module | redact, models | pipeline, app | `test_trace.py`, `test_pipeline.py` | D-009, D-035 | done |
| `navigator/pipeline.py` | module | everything above | app, cli, run_eval | `test_pipeline.py` | D-001..D-009, D-031, D-033 | done |
| `app.py` | module | pipeline, config, data, streamlit | user (`make app`) | `test_app.py` | D-038, D-039 | done |
| `cli.py` | module | pipeline, config | `make demo` | `test_cli.py` | D-038 | done |
| `scripts/run_eval.py` | module | pipeline, data, data/eval | `make eval` | `test_run_eval.py` | D-038 | done |
| `data/generate.py` + `eval_sets.py` | data | - | data files | `test_data.py`, `test_generate.py` | D-010, D-013 | done |
| `data/zips.json` | data | generate.py | validate, retriever | `test_data.py`, `test_generate.py` | D-010, D-011, D-013 | done |
| `data/plans.json` | data | generate.py | validate, costs | `test_data.py`, `test_generate.py` | D-010, D-011, D-013 | done |
| `data/practitioners.json` | data | generate.py | retriever, care_engine | `test_data.py`, `test_generate.py` | D-010, D-011, D-012, D-013 | done |
| `data/cost_ranges.json` | data | generate.py | costs | `test_data.py`, `test_generate.py` | D-010, D-011, D-013 | done |
| `data/eval/*.jsonl` | data | eval_sets.py | tests, run_eval | `test_data.py`, `test_generate.py` | D-013 | done |
| `pyproject.toml`, `requirements.txt`, `Makefile` | config | - | dev workflow | - | - | done |
| `README.md` | doc | everything | reviewers | - | - | done |

## Current status

- Done: Phases 0 to 8. All nodes above are done.
- Tests: 903 passing offline with no API keys (`python -m pytest`).
- Offline eval (`python scripts/run_eval.py --offline`): red flags 100% (40/40), routing 100% acceptable (40/40) with 0 below expected, vague -> follow-up 100% (15/15), adversarial 100% (10/10), retrieval recall@3 100% (20 queries), 0 filter violations.
- Demo (`python cli.py`): 6/6 cases as expected.
- Live verification (D-036): Claude, Jev (all question types) and Voyage called successfully; live routing 39/39 acceptable, 0 lower; six demo cases correct with guarded Claude explanations.
- In progress: -
- Not started: -

## Open questions

- The Voyage key hits its rate limit (HTTP 429) after one query in quick succession; requests fall back to offline search (D-037).
- Live Jev rerank sends one score question per document (up to 10) in one request; cost per search is roughly 10x a single classification.

- Negation ("no chest pain") still fires the red-flag screen (D-017). Acceptable over-triage for the prototype?

- `make` is not installed on the dev machine (Windows); Makefile targets are plain one-liners that can be run directly.
- `make eval` with keys in `.env` runs live (about 105 pipeline runs); the live eval hasn't been run end to end yet (live routing alone: 39/39).
- The Sonnet 5.5 evaluation judge (D-004) isn't implemented (D-038).
