"""Per-request trace: one JSON file per request in traces/ (D-009).

Every step records name, input, output, the model or rule used, latency, and tokens/cost
when known. Inputs and outputs are redacted again here as a safety net.
"""
from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from types import SimpleNamespace
from typing import Iterator, Optional

from navigator.models import TraceStep
from navigator.redact import redact


class Tracer:
    def __init__(self, request_id: str):
        self.request_id = request_id
        self.steps: list[TraceStep] = []

    def add(self, name: str, input: str, output: str, used: str, latency_ms: float,
            tokens: Optional[int] = None, cost_usd: Optional[float] = None) -> None:
        self.steps.append(TraceStep(name=name, input=redact(str(input)), output=redact(str(output)), used=used,
                                    latency_ms=round(latency_ms, 2), tokens=tokens, cost_usd=cost_usd))

    @contextmanager
    def step(self, name: str, input: str, used: str) -> Iterator[SimpleNamespace]:
        record = SimpleNamespace(output="", used=used, tokens=None, cost_usd=None)
        start = perf_counter()
        try:
            yield record
        except Exception as e:
            record.output = f"error: {type(e).__name__}: {e}"
            raise
        finally:
            self.add(name, input, record.output, record.used, (perf_counter() - start) * 1000,
                     record.tokens, record.cost_usd)

    def save(self, directory: Path, summary: dict) -> Path:
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{self.request_id}.json"
        body = {
            "request_id": self.request_id,
            "saved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "summary": summary,
            "steps": [s.model_dump() for s in self.steps],
        }
        path.write_text(json.dumps(body, indent=2, ensure_ascii=False), encoding="utf-8")
        return path
