"""Synthetic data access and opening-hours check, shared by the care engine and retrieval."""
from __future__ import annotations

import json
import math
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


def haversine_km(a_lat: float, a_lng: float, b_lat: float, b_lng: float) -> float:
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp, dl = p2 - p1, math.radians(b_lng - a_lng)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(h))


def is_open(hours: dict[str, str | None], when: datetime) -> bool:
    """Open when the day's slot is "24h" or start <= HH:MM < end."""
    slot = hours.get(DAYS[when.weekday()])
    if slot is None:
        return False
    if slot == "24h":
        return True
    start, end = slot.split("-")
    return start <= when.strftime("%H:%M") < end
