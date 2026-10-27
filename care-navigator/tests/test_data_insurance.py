"""Prompt1 Part B: plans, zips, practitioners, network rules and coverage gaps (D-044)."""
from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path
from typing import Literal, Optional

import pytest
from pydantic import BaseModel

DATA = Path(__file__).resolve().parents[1] / "data"
SERVICES = ["TELEHEALTH", "PRIMARY_CARE", "SPECIALIST", "URGENT_CARE", "ER", "AMBULANCE", "LAB", "XRAY",
            "ADVANCED_IMAGING"]
CARE_TYPES = ["TELEHEALTH", "PRIMARY_CARE", "SPECIALIST", "URGENT_CARE", "ER"]
NEW_PLANS = ["PLAN_PLATINUM_PPO", "PLAN_HSA_BRONZE_HMO", "PLAN_COMMUNITY_MEDICAID", "PLAN_SENIOR_ADVANTAGE",
             "PLAN_MARKETPLACE_EPO", "SELF_PAY"]
ORIGINAL_PLANS = ["PLAN_GOLD_PPO", "PLAN_SILVER_HMO", "PLAN_BRONZE_LOCAL", "PLAN_STUDENT"]
COMMERCIAL = ["PLAN_GOLD_PPO", "PLAN_SILVER_HMO", "PLAN_BRONZE_LOCAL", "PLAN_STUDENT", "PLAN_PLATINUM_PPO",
              "PLAN_HSA_BRONZE_HMO", "PLAN_MARKETPLACE_EPO"]
MEDICAID, SENIOR = "PLAN_COMMUNITY_MEDICAID", "PLAN_SENIOR_ADVANTAGE"
PLAN_OWNED_TELEHEALTH = {"TH-002", "TH-003", "TH-007"}
GAP_RADIUS_KM = 15


def load(name):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def load_jsonl(name):
    return [json.loads(l) for l in (DATA / "eval" / name).read_text(encoding="utf-8").splitlines() if l.strip()]


ZIPS, PLANS, PRACS = load("zips.json"), load("plans.json"), load("practitioners.json")
ZIP_BY, PLAN_BY, PRAC_BY = {z["zip"]: z for z in ZIPS}, {p["id"]: p for p in PLANS}, {p["id"]: p for p in PRACS}


def km(a_lat, a_lng, b_lat, b_lng):
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp, dl = p2 - p1, math.radians(b_lng - a_lng)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(h))


# ------------------------------------------------------------------ B1 plans
class Service(BaseModel):
    copay_usd: int
    deductible_applies: bool
    coinsurance_applies: bool
    note: str


class Amounts(BaseModel):
    individual: Optional[int]
    family: Optional[int]


class OutOfNetwork(BaseModel):
    covered: bool
    coinsurance_pct: Optional[int]
    note: str


class FullPlan(BaseModel):
    id: str
    name: str
    carrier: str
    plan_type: str
    metal_tier: Optional[str]
    network_name: Optional[str]
    plan_year: int
    eligibility: str
    premium_monthly_usd: int
    deductible_usd: Amounts
    out_of_pocket_max_usd: Amounts
    coinsurance_pct: int
    services: dict[str, Service]
    er_copay_waived_if_admitted: bool
    out_of_network: OutOfNetwork
    emergency_rule: str
    referral_required_for_specialist: bool
    prior_auth_required_for: list[str]
    hsa_eligible: bool
    telehealth_partner_ids: list[str]
    nurse_line: str
    nurse_line_hours: str
    member_services: str
    copays_usd: dict[str, int]
    synthetic: Literal[True]


def test_ten_plans_keeping_the_original_ids():
    assert [p["id"] for p in PLANS][:4] == ORIGINAL_PLANS
    assert set(PLAN_BY) == set(ORIGINAL_PLANS) | set(NEW_PLANS) and len(PLANS) == 10


@pytest.mark.parametrize("plan", PLANS, ids=[p["id"] for p in PLANS])
def test_plan_schema_every_service_and_flat_copays(plan):
    FullPlan(**plan)
    assert set(plan["services"]) == set(SERVICES)
    assert plan["copays_usd"] == {ct: plan["services"][ct]["copay_usd"] for ct in CARE_TYPES}
    assert set(plan["telehealth_partner_ids"]) <= set(PRAC_BY)


def test_original_plan_costs_are_unchanged():
    expected = {"PLAN_GOLD_PPO": (1000, [0, 25, 50, 50, 250]), "PLAN_SILVER_HMO": (3000, [15, 35, 70, 75, 400]),
                "PLAN_BRONZE_LOCAL": (7000, [30, 60, 100, 120, 750]), "PLAN_STUDENT": (500, [0, 20, 40, 40, 200])}
    for pid, (deductible, copays) in expected.items():
        p = PLAN_BY[pid]
        assert p["deductible_usd"]["individual"] == deductible == p["annual_deductible_usd"]
        assert [p["copays_usd"][ct] for ct in CARE_TYPES] == copays


def test_plan_specific_rules():
    assert PLAN_BY["PLAN_HSA_BRONZE_HMO"]["hsa_eligible"] is True
    assert all(s["deductible_applies"] for s in PLAN_BY["PLAN_HSA_BRONZE_HMO"]["services"].values())
    medicaid = PLAN_BY[MEDICAID]
    assert medicaid["premium_monthly_usd"] == 0 and medicaid["deductible_usd"]["individual"] == 0
    assert medicaid["referral_required_for_specialist"] is True
    assert max(s["copay_usd"] for s in medicaid["services"].values()) <= 10
    senior = PLAN_BY[SENIOR]
    assert "65" in senior["eligibility"] and senior["premium_monthly_usd"] == 0
    assert senior["out_of_pocket_max_usd"]["individual"] > 0
    self_pay = PLAN_BY["SELF_PAY"]
    assert set(self_pay["cash_prices_usd"]) == set(SERVICES) and self_pay["cash_prices_usd"]["TELEHEALTH"] == 59
    assert all("cash_prices_usd" not in p for p in PLANS if p["id"] != "SELF_PAY")
    assert all("in-network cost sharing" in p["emergency_rule"] for p in PLANS if p["id"] != "SELF_PAY")


# ------------------------------------------------------------------ B2 zips
def test_twelve_zips_in_three_towns():
    by_town = {}
    for z in ZIPS:
        by_town.setdefault((z["city"], z["area_type"]), []).append(z["zip"])
    assert by_town == {("Corvalle", "urban"): ["00101", "00102", "00103", "00104", "00105"],
                       ("Brightwater", "suburban"): ["00201", "00202", "00203", "00204"],
                       ("Pinecrest", "rural"): ["00301", "00302", "00303"]}


def test_town_distances():
    corvalle = ZIP_BY["00101"]
    for z, (low, high) in {"00201": (17, 25), "00301": (30, 40)}.items():
        assert low <= km(corvalle["lat"], corvalle["lng"], ZIP_BY[z]["lat"], ZIP_BY[z]["lng"]) <= high, z


# ------------------------------------------------------------------ B3 practitioners and networks
def count(city_zips, ptype):
    return sum(1 for p in PRACS if p["zip"] in city_zips and p["type"] == ptype)


def test_new_towns_have_the_required_mix():
    bw, pc = ["00201", "00202", "00203", "00204"], ["00301", "00302", "00303"]
    assert (count(bw, "ER"), count(bw, "URGENT_CARE"), count(bw, "PRIMARY_CARE"), count(bw, "SPECIALIST")) == (1, 5, 12, 4)
    assert (count(pc, "ER"), count(pc, "URGENT_CARE"), count(pc, "SPECIALIST")) == (1, 1, 0)
    for z in pc:
        assert count([z], "PRIMARY_CARE") == 1
    assert any(not p["accepting_new"] for p in PRACS if p["zip"] in pc and p["type"] == "PRIMARY_CARE")
    assert {"TH-006", "TH-007"} <= set(PRAC_BY)
    assert all(v == "24h" for v in PRAC_BY["TH-006"]["hours"].values())
    assert all(v == "24h" for v in PRAC_BY["TH-007"]["hours"].values())


def test_new_bios_are_varied():
    new = [p for p in PRACS if p["zip"] in ("00201", "00202", "00203", "00204", "00301", "00302", "00303")]
    assert len({p["bio"] for p in new}) == len(new)
    assert len({tuple(p["conditions_treated"]) for p in new}) >= len(new) * 0.8


def test_platinum_and_hsa_follow_gold_and_silver():
    for p in PRACS:
        assert ("PLAN_GOLD_PPO" in p["accepted_plans"]) == ("PLAN_PLATINUM_PPO" in p["accepted_plans"]), p["id"]
        assert ("PLAN_SILVER_HMO" in p["accepted_plans"]) == ("PLAN_HSA_BRONZE_HMO" in p["accepted_plans"]), p["id"]


def test_medicaid_network_is_a_deliberate_subset():
    for ptype, low, high in [("PRIMARY_CARE", 0.3, 0.7), ("URGENT_CARE", 0.3, 0.7)]:
        group = [p for p in PRACS if p["type"] == ptype]
        share = sum(MEDICAID in p["accepted_plans"] for p in group) / len(group)
        assert low <= share <= high, (ptype, share)
    assert 1 <= sum(MEDICAID in p["accepted_plans"] for p in PRACS if p["type"] == "SPECIALIST") <= 2


def test_senior_plan_never_at_pediatric_only_providers():
    # D-045: ERs accept every plan (B3) including ER-004; the age filter keeps adults out of it.
    for p in PRACS:
        if p["patient_ages"] == "children" and p["type"] != "ER":
            assert SENIOR not in p["accepted_plans"], p["id"]


def test_self_pay_everywhere_except_plan_owned_telehealth():
    for p in PRACS:
        assert ("SELF_PAY" in p["accepted_plans"]) == (p["id"] not in PLAN_OWNED_TELEHEALTH), p["id"]


def test_every_er_and_nightowl_accept_every_plan():
    for p in PRACS:
        if p["type"] == "ER" or p["id"] == "TH-001":
            assert set(p["accepted_plans"]) == set(PLAN_BY), p["id"]


def test_new_daytime_providers_close_by_2100_and_midnight_rule_holds():
    midnight = datetime(2026, 11, 4, 0, 15)
    days = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    open_now = set()
    for p in PRACS:
        slot = p["hours"][days[midnight.weekday()]]
        if slot == "24h" or (slot and slot.split("-")[0] <= "00:15" < slot.split("-")[1]):
            open_now.add(p["type"])
        for s in p["hours"].values():
            if s and s != "24h" and p["type"] in ("URGENT_CARE", "PRIMARY_CARE", "SPECIALIST"):
                assert s.split("-")[1] <= "21:00", p["id"]
    assert open_now == {"ER", "TELEHEALTH"}


# ------------------------------------------------------------------ B4 coverage gaps
def compute_coverage():
    rows = []
    for z in ZIPS:
        for plan in PLAN_BY:
            def within(ptype, need_new=False):
                return any(p["type"] == ptype and plan in p["accepted_plans"] and (p["accepting_new"] or not need_new)
                           and km(z["lat"], z["lng"], p["lat"], p["lng"]) <= GAP_RADIUS_KM
                           for p in PRACS if not p["virtual"])
            rows.append({"zip": z["zip"], "plan": plan, "urgent_care": within("URGENT_CARE"),
                         "primary_care": within("PRIMARY_CARE", need_new=True), "specialist": within("SPECIALIST"),
                         "urgent_care_in_zip": any(p["type"] == "URGENT_CARE" and p["zip"] == z["zip"]
                                                   and plan in p["accepted_plans"] for p in PRACS)})
    return rows


def test_coverage_gaps_file_matches_the_data():
    saved = load("coverage_gaps.json")
    assert saved["synthetic"] is True and saved["radius_km"] == GAP_RADIUS_KM
    assert saved["coverage"] == compute_coverage()
    gaps = [{"zip": r["zip"], "plan": r["plan"],
             "missing": [k for k in ("urgent_care", "primary_care", "specialist") if not r[k]]}
            for r in compute_coverage() if not (r["urgent_care"] and r["primary_care"] and r["specialist"])]
    assert saved["gaps"] == gaps


def test_gaps_only_where_planned():
    for r in compute_coverage():
        missing = [k for k in ("urgent_care", "primary_care", "specialist") if not r[k]]
        if not missing:
            continue
        rural = ZIP_BY[r["zip"]]["area_type"] == "rural"
        assert rural or (r["plan"] == MEDICAID and missing == ["specialist"]), r


def test_no_urgent_or_primary_care_gaps_for_commercial_plans_in_corvalle_and_brightwater():
    for r in compute_coverage():
        if ZIP_BY[r["zip"]]["area_type"] != "rural" and r["plan"] in COMMERCIAL:
            assert r["urgent_care"] and r["primary_care"], r


def test_gaps_actually_exist_in_pinecrest_and_for_medicaid_specialists():
    rows = compute_coverage()
    assert any(not r["specialist"] for r in rows if ZIP_BY[r["zip"]]["area_type"] == "rural")
    assert any(not r["specialist"] for r in rows if r["plan"] == MEDICAID)


def test_bronze_00105_in_zip_urgent_care_gap_is_kept():
    in_zip_gaps = [(r["zip"], r["plan"]) for r in compute_coverage()
                   if ZIP_BY[r["zip"]]["city"] == "Corvalle" and r["plan"] in COMMERCIAL and not r["urgent_care_in_zip"]]
    assert ("00105", "PLAN_BRONZE_LOCAL") in in_zip_gaps


# ------------------------------------------------------------------ B5 eval additions
def test_new_routing_cases():
    rows = {r["id"]: r for r in load_jsonl("routing_cases.jsonl")}
    texts = {(r["plan"], r["zip"], r["expected_level"]) for r in rows.values()}
    assert ("SELF_PAY", "00101", "TELEHEALTH") in texts
    assert ("PLAN_BRONZE_LOCAL", "00303", "URGENT_CARE") in texts
    assert ("PLAN_SENIOR_ADVANTAGE", "00101", "PRIMARY_CARE") in texts
    assert ("PLAN_COMMUNITY_MEDICAID", "00201", "URGENT_CARE") in texts


def test_new_retrieval_queries_cover_the_new_towns():
    new = [q for q in load_jsonl("retrieval_queries.jsonl") if q["zip"][:3] in ("002", "003")]
    assert len(new) >= 8
    assert any(q["zip"][:3] == "003" and q["expected_ids"] == [] for q in new)
    for q in new:
        assert set(q["expected_ids"]) <= set(PRAC_BY)
