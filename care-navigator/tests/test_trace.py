"""Phase 6: per-request trace with redacted inputs (D-009)."""
from __future__ import annotations

import json

from navigator.trace import Tracer


def test_steps_record_latency_and_metadata():
    t = Tracer("req-1")
    with t.step("parse", input="cough for 2 days", used="offline-parser") as s:
        s.output = "main_symptom=cough"
        s.tokens = 12
    step = t.steps[0]
    assert step.name == "parse" and step.used == "offline-parser" and step.output == "main_symptom=cough"
    assert step.latency_ms >= 0 and step.tokens == 12 and step.cost_usd is None


def test_step_is_recorded_even_when_it_raises():
    t = Tracer("req-2")
    try:
        with t.step("jev", input="x", used="jev-latest"):
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    assert t.steps[0].name == "jev" and "error" in t.steps[0].output.lower()


def test_inputs_and_outputs_are_redacted():
    t = Tracer("req-3")
    t.add("redact", input="My name is John Smith, email john@example.com", output="call 555-123-4567",
          used="regex", latency_ms=0.1)
    step = t.steps[0]
    assert "John" not in step.input and "example.com" not in step.input and "555-123" not in step.output


def test_save_writes_one_json_file_per_request(tmp_path):
    t = Tracer("req-4")
    t.add("validate", input="x", output="ok", used="rules", latency_ms=0.0)
    path = t.save(tmp_path, summary={"outcome": "FOLLOW_UP"})
    data = json.loads(path.read_text(encoding="utf-8"))
    assert path.name == "req-4.json"
    assert data["request_id"] == "req-4" and data["summary"]["outcome"] == "FOLLOW_UP"
    assert data["steps"][0]["name"] == "validate"
