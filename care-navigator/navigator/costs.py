"""Cost estimates: plan copay (plans.json) + typical total (cost_ranges.json). Labeled as estimates."""
from __future__ import annotations

import json
from functools import lru_cache

from navigator import config
from navigator.data import DATA_DIR, load_plans
from navigator.models import CostEstimate

HIGH_DEDUCTIBLE_USD = config.HIGH_DEDUCTIBLE_USD


@lru_cache(maxsize=1)
def _ranges() -> dict[str, list[int]]:
    return json.loads((DATA_DIR / "cost_ranges.json").read_text(encoding="utf-8"))["ranges_usd"]


def estimate(care_type: str, plan_id: str | None) -> CostEstimate:
    low, high = _ranges()[care_type]
    plan = next((p for p in load_plans() if p["id"] == plan_id), None)
    if plan is None:
        return CostEstimate(care_type=care_type, typical_range_usd=(low, high))
    deductible = plan["annual_deductible_usd"]
    note = None
    if deductible >= HIGH_DEDUCTIBLE_USD:
        note = (f"Your plan has a ${deductible:,} deductible, so you may pay more than the copay "
                f"until it is met.")
    return CostEstimate(
        care_type=care_type,
        copay_usd=plan["copays_usd"].get(care_type),
        typical_range_usd=(low, high),
        deductible_usd=deductible,
        deductible_note=note,
    )
