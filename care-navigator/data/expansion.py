"""Prompt1 Part B data: 10 plans, 12 zips in 3 towns, new practitioners, network rules, coverage gaps.

Imported by generate.py. Everything is fictional and synthetic. Deterministic: the only randomness
comes from the generator's seeded random.Random, used after the original 44 records so their
coordinates and addresses don't change. Simplified; not real insurance rules (D-044).
"""
from __future__ import annotations

import math
import random

G, S, B, T = "PLAN_GOLD_PPO", "PLAN_SILVER_HMO", "PLAN_BRONZE_LOCAL", "PLAN_STUDENT"
PLAT, HSA, MCD = "PLAN_PLATINUM_PPO", "PLAN_HSA_BRONZE_HMO", "PLAN_COMMUNITY_MEDICAID"
SEN, MKT, CASH = "PLAN_SENIOR_ADVANTAGE", "PLAN_MARKETPLACE_EPO", "SELF_PAY"
PLAN_ORDER = [G, S, B, T, PLAT, HSA, MCD, SEN, MKT, CASH]
SERVICES = ["TELEHEALTH", "PRIMARY_CARE", "SPECIALIST", "URGENT_CARE", "ER", "AMBULANCE", "LAB", "XRAY",
            "ADVANCED_IMAGING"]
CARE_TYPES = SERVICES[:5]
DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
EMERGENCY_RULE = "ER covered at in-network cost sharing anywhere, simplified"
PLAN_OWNED_TELEHEALTH = {"TH-002", "TH-003", "TH-007"}
GAP_RADIUS_KM = 15

# ------------------------------------------------------------------ plans (B1)


def _svc(copay, deductible=False, coinsurance=False, note=""):
    return {"copay_usd": copay, "deductible_applies": deductible, "coinsurance_applies": coinsurance, "note": note}


def _services(copays: list[int], deductible_for=(), coinsurance_for=(), notes=None) -> dict:
    notes = notes or {}
    return {s: _svc(c, s in deductible_for, s in coinsurance_for, notes.get(s, ""))
            for s, c in zip(SERVICES, copays)}


def _plan(pid, name, carrier, plan_type, metal, network, eligibility, premium, deductible, oop, coinsurance,
          services, waived, out_of_network, referral, prior_auth, hsa, partners, nurse, nurse_hours, member,
          legacy_tier, legacy_network, cash=None):
    plan = {
        "id": pid, "name": name, "carrier": carrier, "plan_type": plan_type, "metal_tier": metal,
        "network_name": network, "plan_year": 2026, "eligibility": eligibility, "premium_monthly_usd": premium,
        "deductible_usd": {"individual": deductible[0], "family": deductible[1]},
        "out_of_pocket_max_usd": {"individual": oop[0], "family": oop[1]},
        "coinsurance_pct": coinsurance, "services": services, "er_copay_waived_if_admitted": waived,
        "out_of_network": out_of_network, "emergency_rule": EMERGENCY_RULE if pid != CASH else
        "No insurance: the ER bills its cash price; financial assistance may apply (simplified)",
        "referral_required_for_specialist": referral, "prior_auth_required_for": prior_auth, "hsa_eligible": hsa,
        "telehealth_partner_ids": partners, "nurse_line": nurse, "nurse_line_hours": nurse_hours,
        "member_services": member,
        # Legacy fields kept so older code and tests keep working (D-044).
        "tier": legacy_tier, "network_type": legacy_network, "annual_deductible_usd": deductible[0],
        "copays_usd": {ct: services[ct]["copay_usd"] for ct in CARE_TYPES},
    }
    if cash is not None:
        plan["cash_prices_usd"] = cash
    return plan


def _oon(covered, coinsurance, note):
    return {"covered": covered, "coinsurance_pct": coinsurance, "note": note}


ER_NOTE = {"ER": "Waived if you are admitted"}
HDHP = "No copay; you pay the full allowed cost until the deductible is met, then coinsurance"
CASH_PRICES = {"TELEHEALTH": 59, "PRIMARY_CARE": 140, "SPECIALIST": 220, "URGENT_CARE": 175, "ER": 1400,
               "AMBULANCE": 900, "LAB": 45, "XRAY": 110, "ADVANCED_IMAGING": 650}

PLANS = [
    _plan(G, "Evergreen Health Gold PPO", "Evergreen Health (fictional)", "PPO", "gold", "Evergreen Network",
          "Employer group and individual", 520, (1000, 2000), (5000, 10000), 10,
          _services([0, 25, 50, 50, 250, 150, 0, 40, 200], deductible_for=("ADVANCED_IMAGING",),
                    coinsurance_for=("ADVANCED_IMAGING",), notes=ER_NOTE),
          True, _oon(True, 40, "Covered at higher cost sharing"), False, ["ADVANCED_IMAGING"], False, ["TH-002"],
          "1-800-555-0101", "24/7", "1-800-555-0201", "gold", "PPO"),
    _plan(S, "Summit Care Silver HMO", "Summit Care (fictional)", "HMO", "silver", "Summit HMO Network",
          "Employer group and individual", 410, (3000, 6000), (8000, 16000), 20,
          _services([15, 35, 70, 75, 400, 250, 10, 50, 300], deductible_for=("ER", "AMBULANCE", "ADVANCED_IMAGING"),
                    coinsurance_for=("ADVANCED_IMAGING",), notes=ER_NOTE),
          True, _oon(False, None, "Not covered except emergencies"), True, ["SPECIALIST", "ADVANCED_IMAGING"], False,
          ["TH-003"], "1-800-555-0102", "24/7", "1-800-555-0202", "silver", "HMO"),
    _plan(B, "Harbor Bronze Local", "Harbor Mutual (fictional)", "EPO", "bronze", "Harbor Local Network",
          "Individual", 290, (7000, 14000), (9200, 18400), 40,
          _services([30, 60, 100, 120, 750, 400, 25, 75, 500],
                    deductible_for=("SPECIALIST", "ER", "AMBULANCE", "XRAY", "ADVANCED_IMAGING"),
                    coinsurance_for=("ER", "AMBULANCE", "ADVANCED_IMAGING")),
          False, _oon(False, None, "Narrow network: not covered except emergencies"), False, ["ADVANCED_IMAGING"],
          False, ["TH-005"], "1-800-555-0103", "08:00-20:00", "1-800-555-0203", "bronze", "EPO (narrow network)"),
    _plan(T, "Campus Student Health Plan", "Corvalle University (fictional)", "PPO", "gold", "Campus Network",
          "Enrolled students", 180, (500, 1000), (3000, 6000), 20,
          _services([0, 20, 40, 40, 200, 150, 0, 30, 150], notes=ER_NOTE),
          True, _oon(True, 40, "Covered at higher cost sharing"), False, [], False, ["TH-005"],
          "1-800-555-0104", "24/7", "1-800-555-0204", "student", "PPO"),
    _plan(PLAT, "Evergreen Health Platinum PPO", "Evergreen Health (fictional)", "PPO", "platinum",
          "Evergreen Network", "Employer group and individual", 720, (250, 500), (3000, 6000), 10,
          _services([0, 15, 30, 30, 150, 100, 0, 25, 100], notes=ER_NOTE),
          True, _oon(True, 30, "Covered at higher cost sharing"), False, [], False, ["TH-002"],
          "1-800-555-0101", "24/7", "1-800-555-0205", "platinum", "PPO"),
    _plan(HSA, "Summit Care HSA Bronze HMO", "Summit Care (fictional)", "HMO", "bronze", "Summit HMO Network",
          "Individual, HSA eligible", 260, (4000, 8000), (7500, 15000), 30,
          _services([0, 0, 0, 0, 0, 0, 0, 0, 0], deductible_for=SERVICES, coinsurance_for=SERVICES,
                    notes={s: HDHP for s in SERVICES}),
          False, _oon(False, None, "Not covered except emergencies"), True, ["SPECIALIST", "ADVANCED_IMAGING"], True,
          ["TH-003"], "1-800-555-0102", "24/7", "1-800-555-0206", "bronze", "HMO"),
    _plan(MCD, "Community Care Medicaid Plan", "Community Care (fictional)", "Medicaid-style", None,
          "Community Care Network", "Low-income adults and children (fictional Medicaid-style)", 0, (0, 0),
          (100, 200), 0, _services([0, 2, 3, 3, 8, 0, 0, 0, 3]),
          True, _oon(False, None, "Not covered except emergencies"), True, ["SPECIALIST", "ADVANCED_IMAGING"], False,
          ["TH-007"], "1-800-555-0107", "24/7", "1-800-555-0207", "medicaid", "Medicaid-style (narrow network)"),
    _plan(SEN, "Golden Years Senior Advantage HMO", "Golden Years Health (fictional)", "Medicare Advantage-style HMO",
          None, "Golden Years Network", "Age 65+ (fictional Medicare Advantage-style)", 0, (0, 0), (4500, 4500), 20,
          _services([0, 0, 40, 45, 95, 250, 0, 15, 150], coinsurance_for=("ADVANCED_IMAGING",), notes=ER_NOTE),
          True, _oon(False, None, "Not covered except emergencies"), True, ["ADVANCED_IMAGING"], False, ["TH-006"],
          "1-800-555-0108", "24/7", "1-800-555-0208", "senior", "HMO"),
    _plan(MKT, "Prairie Marketplace Silver EPO", "Prairie Mutual (fictional)", "EPO", "silver",
          "Prairie Select Network", "Individual marketplace", 410, (4500, 9000), (8700, 17400), 30,
          _services([10, 40, 80, 75, 500, 300, 20, 50, 300], deductible_for=("ER", "AMBULANCE", "ADVANCED_IMAGING"),
                    coinsurance_for=("ER", "AMBULANCE", "ADVANCED_IMAGING")),
          False, _oon(False, None, "Not covered except emergencies"), False, ["ADVANCED_IMAGING"], False, [],
          "1-800-555-0109", "24/7", "1-800-555-0209", "silver", "EPO"),
    _plan(CASH, "Self-pay (no insurance)", "None (self-pay)", "SELF_PAY", None, None, "Anyone without insurance",
          0, (0, 0), (None, None), 0,
          _services([CASH_PRICES[s] for s in SERVICES], notes={s: "Cash price" for s in SERVICES}),
          False, _oon(False, None, "No network; cash prices apply"), False, [], False, [],
          "1-800-555-0110", "08:00-20:00", "1-800-555-0210", "self_pay", "none", cash=CASH_PRICES),
]

# ------------------------------------------------------------------ zips (B2)
ZIPS = [
    {"zip": "00101", "neighborhood": "Downtown", "city": "Corvalle", "area_type": "urban", "lat": 39.5000, "lng": -98.3500},
    {"zip": "00102", "neighborhood": "Northside", "city": "Corvalle", "area_type": "urban", "lat": 39.5400, "lng": -98.3450},
    {"zip": "00103", "neighborhood": "Eastgate", "city": "Corvalle", "area_type": "urban", "lat": 39.5050, "lng": -98.3000},
    {"zip": "00104", "neighborhood": "Southpoint", "city": "Corvalle", "area_type": "urban", "lat": 39.4600, "lng": -98.3550},
    {"zip": "00105", "neighborhood": "Westfield", "city": "Corvalle", "area_type": "urban", "lat": 39.4980, "lng": -98.4100},
    {"zip": "00201", "neighborhood": "Brightwater Center", "city": "Brightwater", "area_type": "suburban", "lat": 39.6800, "lng": -98.3500},
    {"zip": "00202", "neighborhood": "Lakeview", "city": "Brightwater", "area_type": "suburban", "lat": 39.7150, "lng": -98.3350},
    {"zip": "00203", "neighborhood": "Orchard Hill", "city": "Brightwater", "area_type": "suburban", "lat": 39.6900, "lng": -98.3000},
    {"zip": "00204", "neighborhood": "Millbrook", "city": "Brightwater", "area_type": "suburban", "lat": 39.6550, "lng": -98.3850},
    {"zip": "00301", "neighborhood": "Pinecrest Town", "city": "Pinecrest", "area_type": "rural", "lat": 39.1850, "lng": -98.3500},
    {"zip": "00302", "neighborhood": "Cedar Hollow", "city": "Pinecrest", "area_type": "rural", "lat": 39.1500, "lng": -98.4200},
    {"zip": "00303", "neighborhood": "Ridge Creek", "city": "Pinecrest", "area_type": "rural", "lat": 39.2050, "lng": -98.4700},
]

# ------------------------------------------------------------------ practitioners (B3)


def _hours(weekday, sat=None, sun=None):
    h = {d: weekday for d in DAYS[:5]}
    h["sat"], h["sun"] = sat, sun
    return h


H24 = {d: "24h" for d in DAYS}
UC_LONG = _hours("08:00-20:00", "08:00-20:00", "09:00-17:00")
UC_MID = _hours("09:00-21:00", "09:00-17:00", None)
UC_SHORT = _hours("10:00-16:00", "10:00-14:00", None)
PC_DAY = _hours("08:00-17:00")
PC_EARLY = _hours("07:30-16:30", "09:00-12:00")
SPEC_DAY = _hours("09:00-16:30")

FIRST = ["Avery", "Jonah", "Mariela", "Theo", "Ingrid", "Rafael", "Selin", "Owen", "Keiko", "Darius", "Lucia",
         "Malik", "Hanna", "Ezra", "Noor", "Callum", "Ximena", "Bram", "Ruth", "Tarek", "Linnea", "Joaquin"]
LAST = ["Halvorsen", "Abernathy", "Quintero", "Okonkwo", "Lindqvist", "Ferreira", "Yilmaz", "Pemberton",
        "Nakamura", "Rostami", "Castellanos", "Achterberg", "Mbeki", "Sorensen", "Varga", "Whitcombe",
        "Delacroix", "Fairbanks", "Ibarra", "Kowalczyk", "Moreau", "Thorne"]
STREETS = ["Birch", "Willow", "Aspen", "Prairie", "Meadow", "Juniper", "Harvest", "Granite"]

# id, type, zip, facility, hours, base plans, medicaid, accepting, ages, specialties, conditions, languages, bio
NEW = [
    # Brightwater (suburban)
    ("ER-005", "ER", "00201", "Brightwater Medical Center", H24, [], True, True, "all",
     ["emergency medicine"], ["chest pain", "stroke", "serious injuries", "severe allergic reactions"], ["English", "Spanish"],
     "Brightwater's only emergency department, open around the clock. It handles chest pain, strokes, serious injuries and severe allergic reactions."),
    ("UC-011", "URGENT_CARE", "00201", "Brightwater Injury & X-ray Care", UC_LONG, [G, S, B, T], True, True, "all",
     ["urgent care", "minor orthopedics"], ["ankle sprains", "wrist fractures", "back strain", "sports injuries", "x-ray"], ["English"],
     "Injury-focused urgent care with digital X-ray on site. Splints, braces and crutches for sprains, wrist fractures and sports injuries."),
    ("UC-012", "URGENT_CARE", "00202", "Lakeview Stomach & Hydration Clinic", UC_MID, [G, S, B, T], False, True, "all",
     ["urgent care", "hydration therapy"], ["food poisoning", "vomiting", "diarrhea", "dehydration", "IV fluids"], ["English", "Vietnamese"],
     "Walk-in clinic for stomach illness by the lake. Treats food poisoning, vomiting and diarrhea, with IV fluids for mild dehydration."),
    ("UC-013", "URGENT_CARE", "00203", "Orchard Hill Kids Urgent Care", UC_MID, [G, S, B, T], True, True, "children",
     ["pediatric urgent care"], ["ear infections in children", "fever in children", "croup", "sprains in children"], ["English", "Spanish"],
     "Urgent care only for babies, kids and teens, with pediatric nurses. Common visits are ear infections, fevers, croup and playground sprains."),
    ("UC-014", "URGENT_CARE", "00204", "Millbrook Skin & Allergy Walk-In", UC_LONG, [G, S, B, T], False, True, "all",
     ["urgent care", "dermatology triage"], ["rashes", "hives", "poison ivy", "insect bites", "mild allergic reactions"], ["English"],
     "Same-day walk-in care for skin trouble in Millbrook. Rashes, hives, poison ivy and insect bites, plus mild allergic reactions without breathing problems."),
    ("UC-015", "URGENT_CARE", "00201", "Brightwater Family Walk-In", UC_MID, [G, S, B, T], True, True, "all",
     ["urgent care", "family medicine"], ["ear infections", "colds", "flu", "sore throat", "urinary tract infections"], ["English", "Spanish", "Tagalog"],
     "Family walk-in clinic for kids and adults in central Brightwater. Ear infections, colds, flu, sore throats and urinary tract infections, with bilingual staff."),
    ("PC-016", "PRIMARY_CARE", "00201", "Brightwater Family Health", PC_DAY, [G, S, B, T], True, True, "all",
     ["family medicine"], ["checkups", "vaccines", "diabetes", "colds"], ["English", "Spanish"],
     "Family physician for all ages in central Brightwater: checkups, vaccines, colds and long-term diabetes care."),
    ("PC-017", "PRIMARY_CARE", "00201", "Brightwater Internal Medicine", PC_DAY, [G, S, B, T], False, True, "adults",
     ["internal medicine"], ["high blood pressure", "cholesterol", "fatigue", "preventive care"], ["English"],
     "Internist for adults focused on blood pressure, cholesterol, preventive screening and unexplained tiredness."),
    ("PC-018", "PRIMARY_CARE", "00201", "Little Oaks Pediatrics", PC_EARLY, [G, S, B, T], True, True, "children",
     ["pediatrics"], ["well-child visits", "fever in children", "asthma in children", "childhood vaccines"], ["English", "Spanish"],
     "Pediatric practice for newborns through teens with early weekday and Saturday morning hours. Well-child visits, fevers, asthma and vaccines."),
    ("PC-019", "PRIMARY_CARE", "00202", "Lakeview Community Clinic", PC_DAY, [G, S, B, T], True, True, "all",
     ["family medicine"], ["women's health", "checkups", "vaccines", "minor infections"], ["Spanish", "English"],
     "Bilingual community clinic by the lake offering women's health visits, checkups, vaccines and care for minor infections."),
    ("PC-020", "PRIMARY_CARE", "00202", "Lakeview Senior Care", PC_DAY, [G, S, B, T], False, True, "adults",
     ["geriatrics", "internal medicine"], ["older adult care", "memory concerns", "falls prevention", "medication reviews"], ["English"],
     "Primary care for older adults: memory concerns, preventing falls and reviewing long lists of medicines with families."),
    ("PC-021", "PRIMARY_CARE", "00202", "Lakeview Sports & Family Medicine", PC_DAY, [G, S, B, T], True, True, "all",
     ["family medicine", "sports medicine"], ["knee pain", "running injuries", "sports physicals", "tendonitis"], ["English"],
     "Family doctor with sports medicine training who sees runners and weekend athletes for knee pain, tendonitis and sports physicals."),
    ("PC-022", "PRIMARY_CARE", "00203", "Orchard Hill Family Practice", PC_DAY, [G, S, B, T], True, True, "all",
     ["family medicine"], ["colds", "stomach upset", "minor injuries", "checkups"], ["English", "Polish"],
     "Neighborhood family practice in Orchard Hill for colds, stomach upset, minor injuries and yearly checkups."),
    ("PC-023", "PRIMARY_CARE", "00203", "Orchard Hill Internal Medicine", PC_DAY, [G, S, B, T], False, False, "adults",
     ["internal medicine"], ["thyroid problems", "high blood pressure", "kidney health"], ["English"],
     "Internist managing thyroid problems, blood pressure and kidney health. The panel is full, so no new patients right now."),
    ("PC-024", "PRIMARY_CARE", "00203", "Orchard Hill Young Adult Health", PC_DAY, [G, S, B, T], False, True, "adults",
     ["family medicine", "young adult health"], ["stress", "sleep problems", "sexual health", "acne"], ["English", "Korean"],
     "Nurse practitioner clinic for people in their late teens and twenties: stress, sleep trouble, sexual health and acne."),
    ("PC-025", "PRIMARY_CARE", "00204", "Millbrook Family Doctors", PC_DAY, [G, S, B, T], True, True, "all",
     ["family medicine"], ["checkups", "colds", "skin concerns", "back pain"], ["English", "Vietnamese"],
     "Family doctors in Millbrook seeing all ages for checkups, colds, skin concerns and everyday back pain."),
    ("PC-026", "PRIMARY_CARE", "00204", "Millbrook Women's Primary Care", PC_DAY, [G, S, B, T], False, True, "adults",
     ["family medicine", "women's health"], ["contraception", "menstrual problems", "menopause care", "checkups"], ["English", "French"],
     "Primary care for women covering contraception, period problems, menopause care and routine checkups."),
    ("PC-027", "PRIMARY_CARE", "00204", "Millbrook Internal Medicine", PC_DAY, [G, S, B, T], False, True, "adults",
     ["internal medicine"], ["diabetes", "high blood pressure", "heart health follow-up"], ["English", "Hindi"],
     "Internist helping adults manage diabetes and blood pressure, and following up after heart tests."),
    ("SP-011", "SPECIALIST", "00201", "Brightwater Dermatology", SPEC_DAY, [G, S, B, T], False, True, "all",
     ["dermatology"], ["eczema", "psoriasis", "acne", "mole checks"], ["English"],
     "Dermatologist treating eczema, psoriasis and stubborn acne, and checking moles."),
    ("SP-012", "SPECIALIST", "00202", "Lakeview Orthopedics", SPEC_DAY, [G, S, B, T], False, True, "adults",
     ["orthopedic surgery"], ["fracture follow-up", "shoulder injuries", "knee injuries", "joint pain"], ["English", "Spanish"],
     "Orthopedic surgeon for fracture follow-up, shoulder and knee injuries, and joint pain that isn't getting better."),
    ("SP-013", "SPECIALIST", "00203", "Orchard Hill Digestive Care", SPEC_DAY, [G, S, B, T], False, True, "adults",
     ["gastroenterology"], ["acid reflux", "chronic constipation", "stomach pain that keeps coming back"], ["English"],
     "Gastroenterologist for long-running digestive problems: reflux, constipation and stomach pain that keeps returning."),
    ("SP-014", "SPECIALIST", "00204", "Millbrook Heart & Vascular", SPEC_DAY, [G, S, B, T], False, True, "adults",
     ["cardiology"], ["palpitations follow-up", "high blood pressure", "cholesterol"], ["English"],
     "Cardiologist for planned follow-up of palpitations, hard-to-control blood pressure and high cholesterol."),
    # Pinecrest (rural)
    ("ER-006", "ER", "00301", "Pinecrest Critical Access Hospital", H24, [], True, True, "all",
     ["emergency medicine", "critical access"], ["injuries", "breathing problems", "chest pain", "stabilize and transfer"], ["English"],
     "Small rural hospital emergency room open 24 hours. It treats injuries, breathing problems and chest pain, and stabilizes patients for transfer."),
    ("UC-016", "URGENT_CARE", "00302", "Cedar Hollow Rural Urgent Care", UC_SHORT, [G, S, B], False, True, "all",
     ["urgent care"], ["farm injuries", "cuts", "sprains", "colds"], ["English"],
     "The only urgent care in the Pinecrest area, with short hours. It treats farm and ranch injuries, cuts, sprains and colds."),
    ("PC-028", "PRIMARY_CARE", "00301", "Pinecrest Family Clinic", PC_DAY, [G, S, B, T], True, True, "all",
     ["family medicine"], ["checkups", "vaccines", "chronic conditions", "minor injuries"], ["English", "Spanish"],
     "Family clinic in Pinecrest town for all ages: checkups, vaccines, long-term conditions and minor injuries."),
    ("PC-029", "PRIMARY_CARE", "00302", "Cedar Hollow Country Doctor", PC_DAY, [G, S, B, T], False, False, "all",
     ["family medicine"], ["checkups", "blood pressure", "farm health"], ["English"],
     "A long-time country doctor caring for Cedar Hollow families. The practice is full and not taking new patients."),
    ("PC-030", "PRIMARY_CARE", "00303", "Ridge Creek Health Center", PC_DAY, [G, S, B, T], False, True, "all",
     ["family medicine"], ["checkups", "back pain", "colds", "diabetes"], ["English"],
     "Small health center in Ridge Creek offering checkups, care for back pain and colds, and diabetes follow-up."),
    # Telehealth
    ("TH-006", "TELEHEALTH", None, "SilverLine Senior Telehealth", H24, [G, S], False, True, "adults",
     ["virtual primary care", "geriatrics"], ["medication questions", "colds", "dizziness follow-up", "chronic condition check-ins"], ["English", "Spanish"],
     "Around-the-clock video visits designed for older adults, with large-text screens and family call-in. Medication questions, colds and check-ins."),
    ("TH-007", "TELEHEALTH", None, "Community Care Virtual Clinic", H24, [], True, True, "all",
     ["virtual urgent care"], ["colds", "rashes by photo", "stomach bugs", "prescription refill questions"], ["English", "Spanish"],
     "Community Care members' own 24/7 video clinic for colds, rashes by photo, stomach bugs and refill questions. No cost to members."),
]

# Existing records in the Medicaid-style network: about half of urgent and primary care, one specialist.
EXISTING_MEDICAID = {"UC-001", "UC-003", "UC-005", "UC-007", "UC-010",
                     "PC-001", "PC-004", "PC-006", "PC-007", "PC-010", "PC-011", "PC-013", "SP-008"}


def apply_network_rules(record: dict, medicaid: bool) -> list[str]:
    """B3 network rules on one record's original (Gold/Silver/Bronze/Student) plan list."""
    plans = set(record["accepted_plans"])
    if record["type"] == "ER" or record["id"] == "TH-001":
        return list(PLAN_ORDER)  # every ER and NightOwl accept every plan, including self-pay
    if G in plans:
        plans.add(PLAT)                                  # Platinum wherever Gold
    if S in plans:
        plans |= {HSA, MKT}                              # HSA Bronze (same network) and marketplace wherever Silver
    if medicaid:
        plans.add(MCD)
    if record["patient_ages"] != "children" and plans & {G, S}:
        plans.add(SEN)                                   # senior plan: never pediatric-only providers
    if record["id"] not in PLAN_OWNED_TELEHEALTH:
        plans.add(CASH)
    return [p for p in PLAN_ORDER if p in plans]


def build_new(rng: random.Random, start_index: int) -> list[dict]:
    zip_by = {z["zip"]: z for z in ZIPS}
    out = []
    for n, (pid, ptype, zip_code, facility, hrs, base, medicaid, accepting, ages, specs, conds, langs, bio) in \
            enumerate(NEW):
        doctor = ptype in ("PRIMARY_CARE", "SPECIALIST")
        name = f"Dr. {rng.choice(FIRST)} {rng.choice(LAST)}" if doctor else facility
        rec = {
            "id": pid, "name": name, "credential": rng.choice(["MD", "DO"]) if doctor else None,
            "facility_name": facility, "type": ptype, "specialties": specs, "conditions_treated": conds,
            "languages": langs, "patient_ages": ages, "accepting_new": accepting, "hours": hrs,
            "accepted_plans": base, "virtual": ptype == "TELEHEALTH", "zip": zip_code, "address": None,
            "lat": None, "lng": None, "phone": f"555-01{start_index + n:02d}", "bio": bio, "synthetic": True,
        }
        if pid == "TH-007":
            rec["accepted_plans"] = [MCD]                # plan-owned: the Medicaid-style plan only
        else:
            rec["accepted_plans"] = apply_network_rules(rec, medicaid)
        if zip_code:
            z = zip_by[zip_code]
            jitter = 0.01 if z["area_type"] == "rural" else 0.008
            rec["lat"] = round(z["lat"] + rng.uniform(-jitter, jitter), 5)
            rec["lng"] = round(z["lng"] + rng.uniform(-jitter, jitter), 5)
            rec["address"] = (f"{rng.randint(100, 2400)} {rng.choice(STREETS)} "
                              f"{rng.choice(['St', 'Ave', 'Rd', 'Way'])}, {z['city']} {zip_code}")
        out.append(rec)
    return out


# ------------------------------------------------------------------ coverage gaps (B4)


def _km(a_lat, a_lng, b_lat, b_lng):
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp, dl = p2 - p1, math.radians(b_lng - a_lng)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(h))


def coverage_gaps(practitioners: list[dict]) -> dict:
    """For each zip and plan: in-network urgent care, primary care (accepting new) and a specialist
    within GAP_RADIUS_KM, plus whether urgent care exists in the zip itself."""
    rows = []
    in_person = [p for p in practitioners if not p["virtual"]]
    for z in ZIPS:
        for plan in PLAN_ORDER:
            def within(ptype, need_new=False):
                return any(p["type"] == ptype and plan in p["accepted_plans"] and (p["accepting_new"] or not need_new)
                           and _km(z["lat"], z["lng"], p["lat"], p["lng"]) <= GAP_RADIUS_KM for p in in_person)
            rows.append({"zip": z["zip"], "plan": plan, "urgent_care": within("URGENT_CARE"),
                         "primary_care": within("PRIMARY_CARE", need_new=True), "specialist": within("SPECIALIST"),
                         "urgent_care_in_zip": any(p["type"] == "URGENT_CARE" and p["zip"] == z["zip"]
                                                   and plan in p["accepted_plans"] for p in practitioners)})
    gaps = [{"zip": r["zip"], "plan": r["plan"],
             "missing": [k for k in ("urgent_care", "primary_care", "specialist") if not r[k]]}
            for r in rows if not (r["urgent_care"] and r["primary_care"] and r["specialist"])]
    return {"note": "Synthetic in-network coverage within the radius; computed by data/generate.py.",
            "synthetic": True, "radius_km": GAP_RADIUS_KM, "coverage": rows, "gaps": gaps}
