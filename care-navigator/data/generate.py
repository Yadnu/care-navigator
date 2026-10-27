"""Deterministic synthetic data generator for Care Navigator.

Every record is fictional and labeled "synthetic": true.
Town "Corvalle", zip codes 00101-00105 and all names, phones and
addresses are invented. Coordinates sit in rural Kansas so they map to
no real clinic. Run: python data/generate.py
"""
from __future__ import annotations

import json
import random
from pathlib import Path

SEED = 20261027
DATA_DIR = Path(__file__).parent
EVAL_DIR = DATA_DIR / "eval"

G, S, B, T = "PLAN_GOLD_PPO", "PLAN_SILVER_HMO", "PLAN_BRONZE_LOCAL", "PLAN_STUDENT"
ALL_PLANS = [G, S, B, T]
DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def hours(weekday: str | None, sat: str | None = None, sun: str | None = None) -> dict:
    h = {d: weekday for d in DAYS[:5]}
    h["sat"], h["sun"] = sat, sun
    return h


H24 = {d: "24h" for d in DAYS}
UC_A = hours("08:00-20:00", "08:00-20:00", "08:00-20:00")
UC_B = hours("09:00-21:00", "09:00-17:00", "09:00-17:00")
UC_C = hours("10:00-19:00", "10:00-19:00", None)
PC = hours("08:00-17:00")
PC_SAT = hours("08:00-17:00", "09:00-12:00")
SPEC = hours("09:00-16:30")
TH_DAY = {d: "07:00-22:00" for d in DAYS}

ZIPS = [
    {"zip": "00101", "neighborhood": "Downtown", "city": "Corvalle", "lat": 39.5000, "lng": -98.3500},
    {"zip": "00102", "neighborhood": "Northside", "city": "Corvalle", "lat": 39.5400, "lng": -98.3450},
    {"zip": "00103", "neighborhood": "Eastgate", "city": "Corvalle", "lat": 39.5050, "lng": -98.3000},
    {"zip": "00104", "neighborhood": "Southpoint", "city": "Corvalle", "lat": 39.4600, "lng": -98.3550},
    {"zip": "00105", "neighborhood": "Westfield", "city": "Corvalle", "lat": 39.4980, "lng": -98.4100},
]

PLANS = [
    {
        "id": G, "name": "Evergreen Health Gold PPO", "carrier": "Evergreen Health (fictional)",
        "tier": "gold", "network_type": "PPO", "annual_deductible_usd": 1000,
        "coinsurance_pct": 10, "referral_required_for_specialist": False,
        "copays_usd": {"TELEHEALTH": 0, "PRIMARY_CARE": 25, "SPECIALIST": 50, "URGENT_CARE": 50, "ER": 250},
        "nurse_line": "1-800-555-0101", "nurse_line_hours": "24/7",
    },
    {
        "id": S, "name": "Summit Care Silver HMO", "carrier": "Summit Care (fictional)",
        "tier": "silver", "network_type": "HMO", "annual_deductible_usd": 3000,
        "coinsurance_pct": 20, "referral_required_for_specialist": True,
        "copays_usd": {"TELEHEALTH": 15, "PRIMARY_CARE": 35, "SPECIALIST": 70, "URGENT_CARE": 75, "ER": 400},
        "nurse_line": "1-800-555-0102", "nurse_line_hours": "24/7",
    },
    {
        "id": B, "name": "Harbor Bronze Local", "carrier": "Harbor Mutual (fictional)",
        "tier": "bronze", "network_type": "EPO (narrow network)", "annual_deductible_usd": 7000,
        "coinsurance_pct": 40, "referral_required_for_specialist": False,
        "copays_usd": {"TELEHEALTH": 30, "PRIMARY_CARE": 60, "SPECIALIST": 100, "URGENT_CARE": 120, "ER": 750},
        "nurse_line": "1-800-555-0103", "nurse_line_hours": "08:00-20:00",
    },
    {
        "id": T, "name": "Campus Student Health Plan", "carrier": "Corvalle University (fictional)",
        "tier": "student", "network_type": "PPO", "annual_deductible_usd": 500,
        "coinsurance_pct": 20, "referral_required_for_specialist": False,
        "copays_usd": {"TELEHEALTH": 0, "PRIMARY_CARE": 20, "SPECIALIST": 40, "URGENT_CARE": 40, "ER": 200},
        "nurse_line": "1-800-555-0104", "nurse_line_hours": "24/7",
    },
]

# Typical total billed cost before insurance, by care type. Synthetic estimates.
COST_RANGES = {
    "note": "Synthetic typical total cost before insurance, USD. Not real prices.",
    "synthetic": True,
    "ranges_usd": {
        "SELF_CARE": [0, 20],
        "TELEHEALTH": [40, 90],
        "PRIMARY_CARE": [120, 250],
        "URGENT_CARE": [150, 300],
        "SPECIALIST": [200, 450],
        "ER": [1200, 3500],
    },
}

# (id, name, credential, facility, type, zip, hours, plans, accepting_new,
#  specialties, conditions, languages, patient_ages, bio)
P = [
    # Emergency departments: open 24/7, accept every plan.
    ("ER-001", "Corvalle General Hospital Emergency Department", None, "Corvalle General Hospital", "ER", "00101", H24, ALL_PLANS, True,
     ["emergency medicine", "trauma"], ["chest pain", "stroke", "severe bleeding", "severe dehydration", "broken bones", "head injury"], ["English", "Spanish"], "all",
     "Level II trauma center with a 24-hour emergency department. Board-certified emergency physicians handle heart attacks, strokes, serious injuries and severe dehydration needing IV fluids."),
    ("ER-002", "Northside Regional Medical Center Emergency", None, "Northside Regional Medical Center", "ER", "00102", H24, ALL_PLANS, True,
     ["emergency medicine", "cardiac care"], ["chest pain", "shortness of breath", "severe abdominal pain", "allergic reactions"], ["English"], "all",
     "Full-service emergency department open around the clock, with an on-site cardiac catheterization lab and CT imaging for chest pain and severe abdominal pain."),
    ("ER-003", "Southpoint Community Hospital Emergency", None, "Southpoint Community Hospital", "ER", "00104", H24, ALL_PLANS, True,
     ["emergency medicine"], ["injuries", "severe vomiting", "high fever", "breathing problems"], ["English", "Spanish"], "all",
     "Community hospital emergency room serving the south side 24 hours a day. Treats serious injuries, breathing problems, high fevers and vomiting that won't stop."),
    ("ER-004", "St. Aldric Children's Pediatric Emergency", None, "St. Aldric Children's Hospital", "ER", "00103", H24, ALL_PLANS, True,
     ["pediatric emergency medicine"], ["high fever in infants", "breathing problems in children", "dehydration in children", "seizures"], ["English", "Spanish"], "children",
     "Emergency department staffed by pediatric emergency specialists, for children and teens only. Open 24/7 for infant fevers, breathing trouble, seizures and dehydration."),

    # Urgent care: none open past 21:00, so midnight requests need telehealth or the ER.
    ("UC-001", "Downtown QuickCare", None, "Downtown QuickCare", "URGENT_CARE", "00101", UC_A, ALL_PLANS, True,
     ["urgent care", "family medicine"], ["colds", "flu", "sore throat", "strep test", "minor cuts", "pink eye"], ["English"], "all",
     "Walk-in urgent care for everyday illness. Rapid strep and flu testing on site, plus care for minor cuts and pink eye. Open every day until 8 pm."),
    ("UC-002", "Riverwalk Urgent Care", None, "Riverwalk Urgent Care", "URGENT_CARE", "00101", UC_B, [G, S, T], True,
     ["urgent care", "hydration therapy"], ["food poisoning", "stomach bugs", "vomiting", "diarrhea", "dehydration", "IV fluids"], ["English", "Spanish"], "all",
     "Urgent care with a focus on stomach illness. Treats food poisoning, stomach bugs, vomiting and diarrhea, and gives IV fluids for mild to moderate dehydration. Spanish spoken."),
    ("UC-003", "Northside Express Care", None, "Northside Express Care", "URGENT_CARE", "00102", UC_A, ALL_PLANS, True,
     ["urgent care", "minor orthopedics"], ["sprains", "minor fractures", "x-ray", "back strain", "sports injuries"], ["English"], "all",
     "Urgent care with on-site X-ray for sprains, simple fractures and sports injuries. Splinting and crutches available. Open daily 8 am to 8 pm."),
    ("UC-004", "Little Sprouts Pediatric Urgent Care", None, "Little Sprouts Pediatric Urgent Care", "URGENT_CARE", "00102", UC_B, ALL_PLANS, True,
     ["pediatric urgent care"], ["ear infections in children", "fever in children", "croup", "rashes in children", "minor injuries in children"], ["English", "Spanish"], "children",
     "Urgent care just for kids, staffed by pediatric providers. Handles ear infections, fevers, croup and small injuries in a child-friendly setting."),
    ("UC-005", "Eastgate Walk-In Clinic", None, "Eastgate Walk-In Clinic", "URGENT_CARE", "00103", UC_C, ALL_PLANS, True,
     ["urgent care"], ["urinary tract infections", "coughs", "bronchitis", "sinus infections", "sore throat"], ["English", "Spanish"], "all",
     "Neighborhood walk-in clinic with bilingual English and Spanish staff. Common visits include urinary tract infections, coughs, bronchitis and sinus infections."),
    ("UC-006", "Eastgate Sports & Injury Urgent Care", None, "Eastgate Sports & Injury", "URGENT_CARE", "00103", UC_A, [G, S, T], True,
     ["urgent care", "sports medicine"], ["ankle sprains", "knee injuries", "wrist injuries", "minor fractures", "running injuries"], ["English"], "all",
     "Injury-focused urgent care run by sports medicine providers. Same-day X-ray and bracing for ankle sprains, knee and wrist injuries from sports or falls."),
    ("UC-007", "Southpoint Urgent Care", None, "Southpoint Urgent Care", "URGENT_CARE", "00104", UC_A, ALL_PLANS, True,
     ["urgent care", "wound care"], ["cuts needing stitches", "minor burns", "animal bites", "splinters", "tetanus shots"], ["English", "Spanish"], "all",
     "Urgent care experienced in wound care: stitches, minor burns, animal bites and tetanus shots. Open daily until 8 pm."),
    ("UC-008", "Southpoint Same-Day Care", None, "Southpoint Same-Day Care", "URGENT_CARE", "00104", UC_C, [G, T], True,
     ["urgent care", "dermatology triage"], ["skin rashes", "hives", "mild allergic reactions", "poison ivy", "insect bites"], ["English"], "all",
     "Same-day care for skin problems such as rashes, hives, poison ivy and insect bites, plus mild allergic reactions that don't affect breathing."),
    ("UC-009", "Westfield Urgent Care", None, "Westfield Urgent Care", "URGENT_CARE", "00105", UC_A, [G, S, T], True,
     ["urgent care"], ["flu", "fever", "sore throat", "ear pain", "minor injuries"], ["English"], "all",
     "General urgent care on the west side for flu, fevers, sore throats, ear pain and minor injuries. Not in the Harbor Bronze Local network."),
    ("UC-010", "Westfield Family Urgent Care", None, "Westfield Family Urgent Care", "URGENT_CARE", "00105", UC_B, [G, S, T], True,
     ["urgent care", "family medicine"], ["ear infections", "pink eye", "colds", "stomach bugs", "urinary tract infections"], ["English", "Spanish"], "all",
     "Family urgent care seeing kids and adults for ear infections, pink eye, colds and stomach bugs. Bilingual staff."),

    # Primary care: weekday daytime only.
    ("PC-001", "Dr. Elena Marsh", "MD", "Corvalle Family Health", "PRIMARY_CARE", "00101", PC, ALL_PLANS, True,
     ["family medicine"], ["annual checkups", "colds", "minor infections", "vaccines", "follow-up visits"], ["English", "Spanish"], "all",
     "Family physician caring for patients of all ages, from checkups and vaccines to follow-up after an urgent care or ER visit."),
    ("PC-002", "Dr. Samuel Okafor", "DO", "Downtown Internal Medicine", "PRIMARY_CARE", "00101", PC, [G, S], True,
     ["internal medicine"], ["high blood pressure", "diabetes", "cholesterol", "fatigue"], ["English"], "adults",
     "Internist focused on long-term adult health: blood pressure, diabetes and cholesterol management, and workups for ongoing fatigue."),
    ("PC-003", "Priya Natarajan", "NP", "Corvalle Family Health", "PRIMARY_CARE", "00101", PC, ALL_PLANS, False,
     ["family medicine", "women's health"], ["women's health", "contraception", "annual checkups"], ["English", "Tamil"], "adults",
     "Nurse practitioner offering women's health visits, contraception counseling and annual checkups. Not accepting new patients."),
    ("PC-004", "Dr. Marcus Hale", "MD", "Northside Primary Care", "PRIMARY_CARE", "00102", PC, ALL_PLANS, True,
     ["family medicine"], ["checkups", "back pain", "sinus problems", "mild asthma"], ["English"], "all",
     "Family doctor treating back pain, sinus problems and mild asthma, with same-week appointments for new patients."),
    ("PC-005", "Dr. Lina Haddad", "MD", "Northside Pediatrics", "PRIMARY_CARE", "00102", PC, [G, S, T], True,
     ["pediatrics"], ["well-child visits", "childhood vaccines", "ear infections in children", "asthma in children"], ["English", "Arabic"], "children",
     "Pediatrician for newborns through teens: well-child visits, vaccines, ear infections and childhood asthma."),
    ("PC-006", "Dr. Tomás Reyes", "MD", "Clínica Northside", "PRIMARY_CARE", "00102", PC, [S, B], True,
     ["internal medicine"], ["diabetes", "high blood pressure", "stomach problems", "checkups"], ["Spanish", "English"], "adults",
     "Bilingual internist serving the Spanish-speaking community, with a focus on diabetes, blood pressure and ongoing stomach problems."),
    ("PC-007", "Dr. Grace Liu", "MD", "Eastgate Family Medicine", "PRIMARY_CARE", "00103", PC, ALL_PLANS, True,
     ["family medicine"], ["checkups", "skin concerns", "headaches", "minor injuries"], ["English", "Mandarin"], "all",
     "Family physician who sees adults and children for checkups, recurring headaches, skin concerns and minor injuries."),
    ("PC-008", "Jordan Ellis", "PA", "Eastgate Family Medicine", "PRIMARY_CARE", "00103", PC, [G, T], True,
     ["family medicine"], ["sports physicals", "colds", "minor infections"], ["English"], "all",
     "Physician assistant offering sports physicals and visits for colds and minor infections."),
    ("PC-009", "Dr. Amara Bello", "MD", "Eastgate Senior Health", "PRIMARY_CARE", "00103", PC, [G, S], False,
     ["internal medicine", "geriatrics"], ["older adult care", "memory concerns", "falls prevention"], ["English", "Yoruba"], "adults",
     "Internist specializing in older adults: memory concerns, fall prevention and managing several medications. Not accepting new patients."),
    ("PC-010", "Dr. Henrik Lund", "MD", "Southpoint Family Practice", "PRIMARY_CARE", "00104", PC_SAT, ALL_PLANS, True,
     ["family medicine"], ["checkups", "colds", "stomach upset", "minor injuries"], ["English"], "all",
     "Family practice with Saturday morning hours for colds, stomach upset and minor injuries."),
    ("PC-011", "Dr. Rosa Delgado", "MD", "Southpoint Pediatrics", "PRIMARY_CARE", "00104", PC, [G, S, B], True,
     ["pediatrics"], ["well-child visits", "fever in children", "rashes in children", "vaccines"], ["Spanish", "English"], "children",
     "Bilingual pediatrician seeing children for fevers, rashes, vaccines and well-child visits."),
    ("PC-012", "Dr. Kwame Asante", "DO", "Southpoint Internal Medicine", "PRIMARY_CARE", "00104", PC, [S, T], True,
     ["internal medicine"], ["high blood pressure", "thyroid problems", "fatigue"], ["English", "Twi"], "adults",
     "Internist managing blood pressure, thyroid problems and persistent fatigue in adults."),
    ("PC-013", "Dr. Nadia Petrov", "MD", "Westfield Family Clinic", "PRIMARY_CARE", "00105", PC, ALL_PLANS, True,
     ["family medicine"], ["checkups", "colds", "minor infections", "vaccines"], ["English", "Russian"], "all",
     "Family physician on the west side accepting new patients of all ages for checkups, vaccines and common illnesses."),
    ("PC-014", "Dr. Ethan Brooks", "MD", "Westfield Family Clinic", "PRIMARY_CARE", "00105", PC, [G, S], True,
     ["family medicine", "sports medicine"], ["running injuries", "knee pain", "sports physicals"], ["English"], "all",
     "Primary care doctor with sports medicine training who treats knee pain and running injuries alongside routine care."),
    ("PC-015", "Mei Tanaka", "NP", "Corvalle University Student Health", "PRIMARY_CARE", "00105", PC, [T, B], True,
     ["family medicine", "young adult health"], ["colds", "stress", "sleep problems", "sexual health"], ["English", "Japanese"], "adults",
     "Nurse practitioner at the student health center caring for young adults: colds, stress, sleep problems and sexual health."),

    # Telehealth: virtual, serve every zip.
    ("TH-001", "NightOwl Virtual Care", None, "NightOwl Virtual Care", "TELEHEALTH", None, H24, ALL_PLANS, True,
     ["virtual urgent care"], ["nausea", "vomiting", "food poisoning", "diarrhea", "colds", "rashes by photo", "pink eye"], ["English", "Spanish"], "all",
     "Video visits with a licensed clinician 24 hours a day, usually within 15 minutes. Common late-night visits include food poisoning, vomiting, colds and rashes reviewed by photo."),
    ("TH-002", "Evergreen Health Virtual Visits", None, "Evergreen Health (fictional)", "TELEHEALTH", None, H24, [G], True,
     ["virtual urgent care", "virtual primary care"], ["colds", "flu", "allergies", "urinary tract infections", "stomach bugs"], ["English"], "all",
     "Evergreen Health members' own 24/7 video visit service with no copay, for colds, flu, allergies, UTIs and stomach bugs."),
    ("TH-003", "Summit Care Telehealth", None, "Summit Care (fictional)", "TELEHEALTH", None, TH_DAY, [S], True,
     ["virtual urgent care"], ["colds", "sinus infections", "pink eye", "minor rashes"], ["English", "Spanish"], "all",
     "Summit Care members' video visits from 7 am to 10 pm for colds, sinus infections, pink eye and minor rashes."),
    ("TH-004", "KidsLine Pediatric Telehealth", None, "KidsLine", "TELEHEALTH", None, TH_DAY, [G, S, T], True,
     ["pediatric telehealth"], ["fever in children", "rashes in children", "ear pain in children", "vomiting in children"], ["English", "Spanish"], "children",
     "Video visits with pediatric clinicians from 7 am to 10 pm for children's fevers, rashes, ear pain and vomiting."),
    ("TH-005", "Campus Connect Telehealth", None, "Corvalle University (fictional)", "TELEHEALTH", None, H24, [T, B], True,
     ["virtual urgent care", "young adult health"], ["colds", "food poisoning", "hangover-like symptoms", "stress", "minor injuries"], ["English", "Spanish"], "adults",
     "24/7 video visits for students and young adults, covering colds, food poisoning, stress and minor injury questions."),

    # Specialists: weekday daytime, mostly for follow-up care.
    ("SP-001", "Dr. Victor Chen", "MD", "Corvalle ENT Associates", "SPECIALIST", "00101", SPEC, [G, S], True,
     ["otolaryngology (ENT)"], ["chronic sinus problems", "ear infections that keep coming back", "tonsil problems", "hearing loss"], ["English", "Cantonese"], "all",
     "Ear, nose and throat specialist for chronic sinus problems, repeated ear infections, tonsil issues and hearing loss."),
    ("SP-002", "Dr. Hannah Weiss", "MD", "Eastgate Sports Medicine", "SPECIALIST", "00103", SPEC, [G, S, T], True,
     ["sports medicine"], ["knee pain from running", "ACL injuries", "tendonitis", "shin splints"], ["English", "German"], "all",
     "Sports medicine physician who treats runners and athletes: knee pain from running, ACL injuries, tendonitis and shin splints."),
    ("SP-003", "Dr. Luis Romero", "MD", "Southpoint Orthopedics", "SPECIALIST", "00104", SPEC, [G, B], True,
     ["orthopedic surgery"], ["fractures", "back pain", "shoulder injuries", "joint replacement"], ["Spanish", "English"], "adults",
     "Orthopedic surgeon handling fracture follow-up, back pain, shoulder injuries and joint problems."),
    ("SP-004", "Dr. Fatima Siddiqui", "MD", "Northside Digestive Health", "SPECIALIST", "00102", SPEC, [G, S], True,
     ["gastroenterology"], ["acid reflux", "irritable bowel syndrome", "chronic diarrhea", "stomach pain that keeps coming back"], ["English", "Urdu"], "adults",
     "Gastroenterologist for ongoing digestive problems such as acid reflux, irritable bowel syndrome and long-lasting diarrhea or stomach pain."),
    ("SP-005", "Dr. Owen Gallagher", "MD", "Downtown Dermatology", "SPECIALIST", "00101", SPEC, [G, S, T], True,
     ["dermatology"], ["eczema", "acne", "rashes that won't go away", "skin checks"], ["English"], "all",
     "Dermatologist treating eczema, acne, stubborn rashes and doing skin checks for moles."),
    ("SP-006", "Dr. Ana Moreira", "MD", "Westfield Allergy & Asthma", "SPECIALIST", "00105", SPEC, [G, S, B], True,
     ["allergy and immunology"], ["seasonal allergies", "asthma", "hives", "food allergies"], ["Portuguese", "Spanish", "English"], "all",
     "Allergist for seasonal allergies, asthma, recurring hives and food allergy testing."),
    ("SP-007", "Dr. Daniel Kim", "MD", "Northside Heart Clinic", "SPECIALIST", "00102", SPEC, [G, S], True,
     ["cardiology"], ["heart palpitations follow-up", "high blood pressure", "heart rhythm problems"], ["English", "Korean"], "adults",
     "Cardiologist for non-emergency follow-up of palpitations, heart rhythm problems and hard-to-control blood pressure."),
    ("SP-008", "Dr. Leila Farah", "MD", "Eastgate Women's Health", "SPECIALIST", "00103", SPEC, ALL_PLANS, True,
     ["obstetrics and gynecology"], ["pregnancy care", "pelvic pain", "menstrual problems"], ["English", "Arabic", "French"], "adults",
     "OB/GYN providing pregnancy care and treatment for pelvic pain and menstrual problems."),
    ("SP-009", "Dr. Benjamin Ortiz", "DPM", "Southpoint Foot & Ankle", "SPECIALIST", "00104", SPEC, [G, T], True,
     ["podiatry"], ["ankle pain", "foot pain", "plantar fasciitis", "ingrown toenails"], ["English", "Spanish"], "all",
     "Podiatrist treating foot and ankle pain, plantar fasciitis and ingrown toenails."),
    ("SP-010", "Dr. Chloe Martin", "MD", "Westfield Sports & Spine", "SPECIALIST", "00105", SPEC, [S, B], True,
     ["sports medicine", "physical medicine"], ["running injuries", "shin splints", "lower back pain", "hamstring strains"], ["English", "French"], "all",
     "Sports and spine physician for running injuries, shin splints, lower back pain and muscle strains, with on-site physical therapy."),
]


def build_practitioners(rng: random.Random) -> list[dict]:
    zip_by_code = {z["zip"]: z for z in ZIPS}
    out = []
    for i, (pid, name, cred, facility, ptype, zip_code, hrs, plans, accepting, specs, conds, langs, ages, bio) in enumerate(P):
        rec = {
            "id": pid,
            "name": name,
            "credential": cred,
            "facility_name": facility,
            "type": ptype,
            "specialties": specs,
            "conditions_treated": conds,
            "languages": langs,
            "patient_ages": ages,
            "accepting_new": accepting,
            "hours": hrs,
            "accepted_plans": plans,
            "virtual": ptype == "TELEHEALTH",
            "zip": zip_code,
            "address": None,
            "lat": None,
            "lng": None,
            "phone": f"555-01{i:02d}",
            "bio": bio,
            "synthetic": True,
        }
        if zip_code:
            z = zip_by_code[zip_code]
            rec["lat"] = round(z["lat"] + rng.uniform(-0.008, 0.008), 5)
            rec["lng"] = round(z["lng"] + rng.uniform(-0.008, 0.008), 5)
            rec["address"] = f"{rng.randint(100, 2400)} {rng.choice(['Elm', 'Cedar', 'Main', 'Harbor', 'Mill', 'Oak', 'Ridge', 'Lake'])} {rng.choice(['St', 'Ave', 'Rd', 'Blvd'])}, {z['city']} {zip_code}"
        out.append(rec)
    return out


def write_json(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def main() -> None:
    from eval_sets import EVAL_SETS  # local module next to this file

    rng = random.Random(SEED)
    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    write_json(DATA_DIR / "zips.json", [{**z, "synthetic": True} for z in ZIPS])
    write_json(DATA_DIR / "plans.json", [{**p, "synthetic": True} for p in PLANS])
    write_json(DATA_DIR / "cost_ranges.json", COST_RANGES)
    write_json(DATA_DIR / "practitioners.json", build_practitioners(rng))
    for name, rows in EVAL_SETS.items():
        write_jsonl(EVAL_DIR / f"{name}.jsonl", [{**r, "synthetic": True} for r in rows])
    print("Wrote synthetic data to", DATA_DIR)


if __name__ == "__main__":
    import sys

    sys.path.insert(0, str(DATA_DIR))
    main()
