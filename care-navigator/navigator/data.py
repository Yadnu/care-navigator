"""Synthetic data access and opening-hours check, shared by the care engine and retrieval."""
from __future__ import annotations

import json
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from navigator.models import Practitioner

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def _load(name: str):
    return json.loads((DATA_DIR / name).read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_practitioners() -> tuple[Practitioner, ...]:
    return tuple(Practitioner(**p) for p in _load("practitioners.json"))


@lru_cache(maxsize=1)
def load_plans() -> tuple[dict, ...]:
    return tuple(_load("plans.json"))


@lru_cache(maxsize=1)
def load_zips() -> tuple[dict, ...]:
    return tuple(_load("zips.json"))


def is_open(hours: dict[str, str | None], when: datetime) -> bool:
    """Open when the day's slot is "24h" or start <= HH:MM < end."""
    slot = hours.get(DAYS[when.weekday()])
    if slot is None:
        return False
    if slot == "24h":
        return True
    start, end = slot.split("-")
    return start <= when.strftime("%H:%M") < end
