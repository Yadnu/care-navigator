# Code style

- Python 3.11+, type hints, `from __future__ import annotations`. Pydantic v2 for every schema in `navigator/models.py`.
- Small modules, one responsibility each, matching the layout in `PROMPT.md`. Don't over-engineer.
- Every model sits behind an interface with an offline implementation that is the default (D-008). Real clients switch on only when their env var is set (`config.py`).
- Thresholds, model ids and limits live in `navigator/config.py`, not inline.
- Rules and phrase lists live in YAML (`red_flags.yaml`, `care_rules.yaml`), versioned, each rule with an id.
- Data paths resolve relative to the package (`Path(__file__)`), never the working directory.
- All data synthetic; never add real people, clinics, places or patient data.
