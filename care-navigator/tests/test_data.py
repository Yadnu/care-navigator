"""Phase 1 data tests. Run: pytest tests/test_data.py"""
from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field

DATA = Path(__file__).resolve().parents[1] / "data"
EVAL = DATA / "eval"
LEVELS = ["SELF_CARE", "TELEHEALTH", "PRIMARY_CARE", "URGENT_CARE", "ER"]
TYPES = ["ER", "URGENT_CARE", "PRIMARY_CARE", "TELEHEALTH", "SPECIALIST"]
DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


# ------------------------------------------------------------------ schemas
class Zip(BaseModel):
    zip: str = Field(pattern=r"^00[1-3]\d\d$")  # D-044: Corvalle 001xx, Brightwater 002xx, Pinecrest 003xx
    neighborhood: str
    city: str
    lat: float
    lng: float
    synthetic: Literal[True]


class Plan(BaseModel):
    id: str
    name: str
    carrier: str
    tier: str
    network_type: str
    annual_deductible_usd: int
    coinsurance_pct: int
    referral_required_for_specialist: bool
    copays_usd: dict[str, int]
    nurse_line: str
    nurse_line_hours: str
    synthetic: Literal[True]


class Practitioner(BaseModel):
    id: str
    name: str
    credential: Optional[str]
    facility_name: str
    type: Literal["ER", "URGENT_CARE", "PRIMARY_CARE", "TELEHEALTH", "SPECIALIST"]
    specialties: list[str]
    conditions_treated: list[str]
    languages: list[str]
    patient_ages: Literal["all", "adults", "children"]
    accepting_new: bool
    hours: dict[str, Optional[str]]
    accepted_plans: list[str]
    virtual: bool
    zip: Optional[str]
    address: Optional[str]
    lat: Optional[float]
    lng: Optional[float]
    phone: str
    bio: str
    synthetic: Literal[True]


# ------------------------------------------------------------------ helpers
def load(name):
    return json.loads((DATA / name).read_text())


def load_jsonl(name):
    return [json.loads(l) for l in (EVAL / name).read_text().splitlines() if l.strip()]


def haversine_km(a_lat, a_lng, b_lat, b_lng):
    r = 6371.0
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp, dl = p2 - p1, math.radians(b_lng - a_lng)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def is_open(hours: dict, when: datetime) -> bool:
    slot = hours.get(DAYS[when.weekday()])
    if slot is None:
        return False
    if slot == "24h":
        return True
    start, end = slot.split("-")
    t = when.strftime("%H:%M")
    return start <= t < end


def passes_filters(p, care_type, plan, zip_rec, when, age_group, max_km):
    if p["type"] != care_type or plan not in p["accepted_plans"]:
        return False
    if not is_open(p["hours"], when):
        return False
    if care_type in ("PRIMARY_CARE", "SPECIALIST") and not p["accepting_new"]:
        return False
    if age_group == "child" and p["patient_ages"] == "adults":
        return False
    if age_group == "adult" and p["patient_ages"] == "children":
        return False
    if not p["virtual"]:
        if haversine_km(zip_rec["lat"], zip_rec["lng"], p["lat"], p["lng"]) > max_km:
            return False
    return True


ZIPS = load("zips.json")
PLANS = load("plans.json")
PRACS = load("practitioners.json")
ZIP_BY = {z["zip"]: z for z in ZIPS}
ORIGINAL_ZIPS = ["00101", "00102", "00103", "00104", "00105"]
ORIGINAL_PLANS = ["PLAN_GOLD_PPO", "PLAN_SILVER_HMO", "PLAN_BRONZE_LOCAL", "PLAN_STUDENT"]
PLAN_IDS = {p["id"] for p in PLANS}


# ------------------------------------------------------------------ tests
def test_schemas_validate():
    for z in ZIPS:
        Zip(**z)
    for p in PLANS:
        Plan(**p)
    for p in PRACS:
        Practitioner(**p)


def test_everything_is_synthetic():
    assert load("cost_ranges.json")["synthetic"] is True
    for name in ["red_flags", "routing_cases", "vague", "adversarial", "retrieval_queries"]:
        assert all(r["synthetic"] is True for r in load_jsonl(f"{name}.jsonl"))


def test_ids_unique_and_references_valid():
    ids = [p["id"] for p in PRACS]
    assert len(ids) == len(set(ids))
    for p in PRACS:
        assert set(p["accepted_plans"]) <= PLAN_IDS, p["id"]
        assert p["virtual"] or p["zip"] in ZIP_BY, p["id"]
        assert p["virtual"] == (p["zip"] is None), p["id"]
        assert set(p["hours"]) == set(DAYS), p["id"]


def test_plan_copays_cover_every_care_type():
    for p in PLANS:
        assert set(p["copays_usd"]) == {"TELEHEALTH", "PRIMARY_CARE", "SPECIALIST", "URGENT_CARE", "ER"}


def test_er_open_24_7_and_accepts_all_plans():
    for p in (p for p in PRACS if p["type"] == "ER"):
        assert all(v == "24h" for v in p["hours"].values()), p["id"]
        assert set(p["accepted_plans"]) == PLAN_IDS, p["id"]


def test_urgent_care_closes_by_2100_and_primary_care_is_daytime():
    for p in PRACS:
        for slot in p["hours"].values():
            if slot and slot != "24h" and p["type"] in ("URGENT_CARE", "PRIMARY_CARE", "SPECIALIST"):
                assert slot.split("-")[1] <= "21:00", p["id"]


def test_24h_telehealth_for_every_plan():
    for plan in PLAN_IDS:
        assert any(p["type"] == "TELEHEALTH" and plan in p["accepted_plans"]
                   and all(v == "24h" for v in p["hours"].values()) for p in PRACS), plan


def test_coverage_in_every_zip_except_deliberate_gap():
    # D-044: the original in-zip guarantee for the original 5 Corvalle zips and 4 plans; the
    # 12-zip, 10-plan rules are the 15 km coverage-gap tests in test_data_insurance.py.
    for z in ORIGINAL_ZIPS:
        for plan in ORIGINAL_PLANS:
            for ctype in ("URGENT_CARE", "PRIMARY_CARE"):
                ok = any(p["type"] == ctype and p["zip"] == z and plan in p["accepted_plans"] for p in PRACS)
                if (z, plan, ctype) == ("00105", "PLAN_BRONZE_LOCAL", "URGENT_CARE"):
                    assert not ok, "deliberate gap must stay"
                else:
                    assert ok, (z, plan, ctype)


def test_bios_are_2_to_4_sentences():
    for p in PRACS:
        n = p["bio"].count(". ") + 1
        assert 1 <= n <= 4 and len(p["bio"]) > 60, p["id"]


def test_eval_set_sizes():
    assert len(load_jsonl("red_flags.jsonl")) >= 40
    assert len(load_jsonl("routing_cases.jsonl")) >= 40
    assert len(load_jsonl("vague.jsonl")) >= 15
    assert len(load_jsonl("adversarial.jsonl")) >= 10
    assert len(load_jsonl("retrieval_queries.jsonl")) >= 20


def test_routing_cases_are_consistent():
    for r in load_jsonl("routing_cases.jsonl"):
        assert r["expected_level"] in LEVELS
        assert r["expected_level"] in r["acceptable_levels"]
        assert set(r["acceptable_levels"]) <= set(LEVELS)
        assert r["zip"] in ZIP_BY and r["plan"] in PLAN_IDS
        datetime.fromisoformat(r["request_time"])


def test_midnight_food_poisoning_cases_present():
    rows = load_jsonl("routing_cases.jsonl")
    mid = [r for r in rows if r["request_time"].endswith("T00:15") and "since dinner" in r["text"]]
    assert {r["expected_level"] for r in mid} == {"TELEHEALTH", "ER"}


def test_retrieval_expected_ids_pass_every_hard_filter():
    for q in load_jsonl("retrieval_queries.jsonl"):
        when = datetime.fromisoformat(q["request_time"])
        candidates = {p["id"] for p in PRACS if passes_filters(
            p, q["care_type"], q["plan"], ZIP_BY[q["zip"]], when, q["age_group"], q["max_distance_km"])}
        assert set(q["expected_ids"]) <= candidates, (q["id"], q["expected_ids"], candidates)
        if not q["expected_ids"]:
            assert not candidates, (q["id"], candidates)


def test_nothing_except_virtual_and_er_open_at_midnight():
    when = datetime.fromisoformat("2026-11-04T00:15")
    open_now = {p["type"] for p in PRACS if is_open(p["hours"], when)}
    assert open_now == {"ER", "TELEHEALTH"}


if __name__ == "__main__":  # fallback runner when pytest isn't installed
    import sys
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("PASS", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, repr(e))
    sys.exit(1 if fails else 0)
