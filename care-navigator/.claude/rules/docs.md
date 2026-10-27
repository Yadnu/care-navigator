# Living docs

- Before any task, read `docs/context-graph.md` and `docs/decisions.md`.
- Record every non-trivial decision (thresholds, library choices, data changes, test corrections) as `D-XXX` in `docs/decisions.md` using the template at the top of that file. Supersede, don't rewrite.
- At the end of every phase update `docs/context-graph.md` (Mermaid flow, node table, current status, open questions) and the "Current phase" section of `context.md`.
- Stop at the end of each phase, show test results, and wait for "continue".
- Don't add features outside `PROMPT.md`. If something seems needed, ask and log it under "Open questions".
