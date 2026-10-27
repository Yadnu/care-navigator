"""Phase 1: data/generate.py is deterministic and byte-identical on every OS."""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "data"
OUTPUTS = [
    "zips.json", "plans.json", "cost_ranges.json", "practitioners.json",
    "eval/red_flags.jsonl", "eval/routing_cases.jsonl", "eval/vague.jsonl",
    "eval/adversarial.jsonl", "eval/retrieval_queries.jsonl",
    "eval/near_misses.jsonl", "eval/conversations.jsonl", "question_bank.json", "coverage_gaps.json",
]


def test_generator_reproduces_committed_files_byte_for_byte(tmp_path):
    for script in ("generate.py", "eval_sets.py", "question_bank_src.py", "expansion.py"):
        shutil.copy(DATA / script, tmp_path / script)
    subprocess.run([sys.executable, str(tmp_path / "generate.py")], check=True, capture_output=True)
    for name in OUTPUTS:
        assert (tmp_path / name).read_bytes() == (DATA / name).read_bytes(), name


def test_committed_files_use_lf_line_endings():
    for name in OUTPUTS:
        assert b"\r\n" not in (DATA / name).read_bytes(), name
