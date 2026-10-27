# Test-driven development

- Red -> green -> refactor for every module. Write the test, run it, show it fails for the right reason, then write the minimum code.
- No production code without a failing test that requires it.
- Never delete, skip or weaken a test to make it pass. If a test is wrong, explain why and record a decision in `docs/decisions.md`.
- Tests run offline with no API keys. Real clients (Claude, Jev, Voyage) are tested with mocked clients/HTTP only; no test touches the network.
- `pytest` from `care-navigator/` must stay green after every cycle.
- Commit after each green cycle: `test: <thing>` then `feat: <thing>` (refactors: `refactor: <thing>`).
