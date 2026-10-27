"""Phase 6: cost estimates from plans.json + cost_ranges.json."""
from __future__ import annotations

import pytest

from navigator.costs import HIGH_DEDUCTIBLE_USD, estimate


def test_copay_and_typical_range_for_plan():
    c = estimate("URGENT_CARE", "PLAN_SILVER_HMO")
    assert c.copay_usd == 75
    assert c.typical_range_usd == (150, 300)
    assert c.label == "Estimate"


@pytest.mark.parametrize("plan, high", [("PLAN_GOLD_PPO", False), ("PLAN_STUDENT", False),
                                        ("PLAN_SILVER_HMO", True), ("PLAN_BRONZE_LOCAL", True)])
def test_deductible_mentioned_only_when_high(plan, high):
    c = estimate("PRIMARY_CARE", plan)
    assert (c.deductible_note is not None) is high
    if high:
        assert f"${c.deductible_usd:,}" in c.deductible_note and c.deductible_usd >= HIGH_DEDUCTIBLE_USD


def test_specialist_uses_specialist_copay():
    assert estimate("SPECIALIST", "PLAN_GOLD_PPO").copay_usd == 50


def test_self_care_has_no_copay():
    c = estimate("SELF_CARE", "PLAN_GOLD_PPO")
    assert c.copay_usd is None and c.typical_range_usd == (0, 20)


def test_unknown_plan_gives_range_only():
    c = estimate("ER", "PLAN_NOPE")
    assert c.copay_usd is None and c.deductible_usd is None and c.typical_range_usd == (1200, 3500)


def test_summary_is_labeled_as_estimate():
    s = estimate("URGENT_CARE", "PLAN_BRONZE_LOCAL").summary()
    assert "estimate" in s.lower() and "$120" in s and "$150" in s and "$300" in s and "$7,000" in s
