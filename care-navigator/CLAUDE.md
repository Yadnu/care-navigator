# Care Navigator

4-hour take-home prototype. A person enters symptoms, severity (1-10), zip, plan and request time; the system returns EMERGENCY, a FOLLOW_UP question, or a RECOMMENDATION (care level + top 3 in-network open practitioners + cost estimates + explanation).

**Core principle: rules decide, Jev classifies, Claude reads and writes, RAG finds practitioners, and every step is traced.**

## Read first, every task
1. `PROMPT.md` – the full plan, phases and pass bars (source of truth for scope).
2. `context.md` – domain facts, data facts, current phase.
3. `docs/context-graph.md` and `docs/decisions.md` – architecture and decisions. Your change must match them.
4. `.claude/rules/` – non-negotiable rules (safety, TDD, docs, code style).

## Commands (Windows, no `make` installed – run the target directly)
- Tests: `.venv/Scripts/python -m pytest` (must pass with no API keys set)
- Data: `.venv/Scripts/python data/generate.py`
- Eval: `.venv/Scripts/python scripts/run_eval.py`
- Demo: `.venv/Scripts/python cli.py`
- App: `.venv/Scripts/python -m streamlit run app.py`
- Setup: `python -m venv .venv && .venv/Scripts/python -m pip install -r requirements.txt`

## Workflow
- Work phase by phase from `PROMPT.md`. **Stop at the end of each phase, show test results, wait for "continue".**
- Red -> green -> refactor. Commit `test: <thing>` then `feat: <thing>` after each green cycle (commits are made at the repo root, `C:\development\MirafloresAI`, staging only `care-navigator/`).
- End of each phase: update `docs/context-graph.md` (status, nodes, open questions), add decisions to `docs/decisions.md`, update the "Current phase" in `context.md`.

## Layout
- `navigator/` – the package (see context graph for every module).
- `data/` – provided synthetic data + generator; `data/README.md` describes it. Don't change data unless a test proves it wrong (log a decision).
- `tests/` – pytest; offline implementations only, mocked HTTP for real clients.
- `traces/` – per-request JSON traces (gitignored).
