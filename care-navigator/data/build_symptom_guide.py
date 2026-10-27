"""Builds data/symptom_guide.json: a curated, simplified guide the
conversation and explainer are allowed to draw from.

NOT clinically validated. Plain-language, common possibilities only.
The app may mention a possible cause ONLY if it appears here, always
hedged ("could be", "a clinician needs to confirm"), never as a diagnosis.
Run: python data/build_symptom_guide.py
"""
import json
from pathlib import Path

CALL, ER = "CALL_911", "GO_TO_ER"


def danger(sign, action, why):
    return {"sign": sign, "action": action, "why": why}


def cause(name, description, typical_level):
    return {"cause": name, "description": description, "typical_level": typical_level}


CLUSTERS = [
    {
        "id": "vomiting_diarrhea",
        "name": "Vomiting or diarrhea",
        "match_terms": ["vomit", "throwing up", "threw up", "nausea", "diarrhea", "loose stools", "stomach bug", "food poisoning"],
        "ask_about": [
            {"topic": "fluids_kept_down", "why": "Whether fluids stay down is the main sign of dehydration risk"},
            {"topic": "duration_and_frequency", "why": "How long and how often changes urgency"},
            {"topic": "blood", "why": "Blood in vomit or stool is a danger sign"},
            {"topic": "dehydration_signs", "why": "Dizziness on standing or peeing much less suggests dehydration"},
            {"topic": "fever", "why": "Fever suggests infection"},
            {"topic": "abdominal_pain", "why": "Severe or one-sided belly pain needs urgent evaluation"},
        ],
        "possible_cause_questions": [
            "Did you eat anything unusual, undercooked, or from somewhere new in the last day or two?",
            "Has anyone you ate with or live with had the same symptoms?",
            "Have you traveled recently?",
            "Did you start any new medication recently?",
            "Is there any chance of pregnancy?",
        ],
        "danger_signs": [
            danger("vomiting blood or material that looks like coffee grounds", CALL, "Blood in vomit can mean bleeding in the stomach or esophagus."),
            danger("vomiting after a head injury", CALL, "Vomiting after a head injury can be a sign of injury to the brain."),
            danger("confusion, extreme sleepiness, or fainting", CALL, "Confusion or fainting can mean severe dehydration or another serious problem."),
            danger("unable to keep any fluids down for many hours", ER, "Not keeping fluids down can lead to dehydration that needs IV fluids."),
            danger("dizzy or faint when standing, or very little urine", ER, "These are signs of dehydration that may need IV fluids."),
            danger("severe or worsening belly pain, or a hard belly", ER, "Severe belly pain can mean a problem like appendicitis that needs imaging."),
            danger("black or bloody stool", ER, "Blood in the stool needs urgent evaluation."),
        ],
        "possible_causes": [
            cause("a stomach bug (viral gastroenteritis)", "A common viral infection that usually improves in 1 to 3 days.", "TELEHEALTH"),
            cause("food poisoning", "Illness from contaminated food, often starting hours after a meal and often affecting others who ate the same food.", "TELEHEALTH"),
            cause("a reaction to a medication or alcohol", "Some medicines and alcohol can upset the stomach.", "PRIMARY_CARE"),
        ],
        "watch_for": [
            "you can't keep small sips of water down for several hours",
            "you feel dizzy when standing or pee much less than usual",
            "you see blood in vomit or stool",
            "belly pain becomes severe or stays in one spot",
        ],
    },
    {
        "id": "abdominal_pain",
        "name": "Belly pain",
        "match_terms": ["stomach pain", "belly pain", "abdominal pain", "stomach ache", "cramps", "stomach hurts"],
        "ask_about": [
            {"topic": "location", "why": "Where the pain is changes what it could be"},
            {"topic": "onset_and_trend", "why": "Sudden or worsening pain is more concerning"},
            {"topic": "severity", "why": "Severe pain needs faster care"},
            {"topic": "fever_vomiting", "why": "Fever or vomiting with belly pain raises concern"},
            {"topic": "bowel_urine_changes", "why": "Changes in stool or urine point to different causes"},
        ],
        "possible_cause_questions": [
            "Did the pain start after a meal, especially spicy, fatty, or unusual food?",
            "Is there any chance of pregnancy?",
            "Have you had this kind of pain before?",
        ],
        "danger_signs": [
            danger("sudden, severe belly pain with fainting", CALL, "Sudden severe pain with fainting can mean internal bleeding."),
            danger("pain in the lower right belly that is getting worse, especially with fever", ER, "Worsening lower right pain can be appendicitis."),
            danger("a hard, rigid belly", ER, "A rigid belly can mean a serious problem inside the abdomen."),
            danger("belly pain during pregnancy with bleeding", ER, "This needs urgent evaluation."),
        ],
        "possible_causes": [
            cause("indigestion or acid reflux", "Burning upper belly pain, often after meals.", "TELEHEALTH"),
            cause("gas or constipation", "Crampy pain that comes and goes.", "SELF_CARE"),
            cause("a stomach bug", "Cramps with diarrhea or vomiting.", "TELEHEALTH"),
            cause("a urinary tract infection", "Lower belly pain with burning when peeing.", "URGENT_CARE"),
        ],
        "watch_for": ["pain becomes severe or constant", "pain moves to the lower right side", "fever, vomiting, or blood in stool appears"],
    },
    {
        "id": "chest_pain",
        "name": "Chest pain or pressure",
        "match_terms": ["chest pain", "chest pressure", "chest tight", "chest hurts", "chest discomfort"],
        "ask_about": [
            {"topic": "character", "why": "Crushing or squeezing pain is more concerning than sharp pain on touch"},
            {"topic": "associated_symptoms", "why": "Sweating, shortness of breath, nausea or arm/jaw pain raise concern"},
            {"topic": "trigger", "why": "Pain with exertion vs. after a workout or cough matters"},
            {"topic": "duration", "why": "Ongoing pain needs immediate care"},
        ],
        "possible_cause_questions": [
            "Did it start during activity, or after a workout, heavy lifting, or a lot of coughing?",
            "Does it hurt more when you press on the spot or move your arm?",
        ],
        "danger_signs": [
            danger("crushing, squeezing, or heavy chest pain", CALL, "This can be a heart attack."),
            danger("chest pain with sweating, shortness of breath, nausea, or pain spreading to the arm, jaw, or back", CALL, "These together can be a heart attack."),
            danger("chest pain with fainting", CALL, "This can be a serious heart or lung problem."),
            danger("chest pain with exertion that goes away with rest", CALL, "This can be reduced blood flow to the heart."),
        ],
        "possible_causes": [
            cause("a strained chest muscle", "Sore, sharp pain that is worse when pressing on the spot or moving, often after exercise or coughing.", "PRIMARY_CARE"),
            cause("acid reflux", "Burning behind the breastbone after meals or lying down.", "TELEHEALTH"),
        ],
        "watch_for": ["pain becomes crushing or spreads to the arm, jaw, or back", "you feel short of breath, sweaty, or faint"],
    },
    {
        "id": "arm_hand_injury",
        "name": "Arm, hand, wrist, or shoulder pain",
        "match_terms": ["arm", "hand", "wrist", "shoulder", "elbow", "finger"],
        "ask_about": [
            {"topic": "injury_mechanism", "why": "A fall, twist, or impact points to an injury"},
            {"topic": "swelling_or_deformity", "why": "Swelling or an odd shape can mean a fracture"},
            {"topic": "can_use", "why": "Not being able to use it suggests a more serious injury"},
            {"topic": "numbness", "why": "Numbness or tingling can mean nerve involvement"},
            {"topic": "cardiac_screen", "why": "Arm pain with chest symptoms must be ruled out"},
        ],
        "possible_cause_questions": [
            "Did it start after a sport, a fall, or lifting something?",
            "Did you hear a pop or snap?",
        ],
        "danger_signs": [
            danger("arm pain with chest pain, shortness of breath, sweating, or nausea", CALL, "Arm pain with these symptoms can be a heart attack."),
            danger("bone visible or limb clearly deformed", ER, "This needs emergency treatment."),
            danger("hand or fingers cold, pale, or numb after an injury", ER, "This can mean blood flow or nerve damage."),
        ],
        "possible_causes": [
            cause("a sprain or strain", "Stretched or torn ligaments or muscles, common after sports.", "URGENT_CARE"),
            cause("a small fracture", "A broken bone often needs an X-ray to confirm.", "URGENT_CARE"),
            cause("overuse or tendonitis", "Pain from repeated motion, building up over days.", "PRIMARY_CARE"),
        ],
        "watch_for": ["swelling or pain gets worse", "you can't move your fingers or wrist", "numbness or color change"],
    },
    {
        "id": "leg_ankle_injury",
        "name": "Leg, knee, ankle, or foot pain",
        "match_terms": ["ankle", "knee", "leg", "foot", "toe", "shin", "calf"],
        "ask_about": [
            {"topic": "injury_mechanism", "why": "A twist or impact points to an injury"},
            {"topic": "can_bear_weight", "why": "Not being able to walk suggests a fracture"},
            {"topic": "swelling_or_deformity", "why": "Swelling or deformity raises concern"},
            {"topic": "calf_swelling", "why": "A swollen, warm calf without injury can be a blood clot"},
        ],
        "possible_cause_questions": ["Did it start after running, a sport, or a fall?", "Have you been on a long flight or drive recently?"],
        "danger_signs": [
            danger("swollen, warm, painful calf with shortness of breath", CALL, "This can be a blood clot that has moved to the lungs."),
            danger("bone visible or leg clearly deformed", ER, "This needs emergency treatment."),
            danger("one calf swollen, warm, and painful without injury", ER, "This can be a blood clot."),
        ],
        "possible_causes": [
            cause("an ankle or knee sprain", "Twisting injury with swelling, common in sports.", "URGENT_CARE"),
            cause("a running overuse injury", "Pain that builds over weeks, like shin splints.", "PRIMARY_CARE"),
        ],
        "watch_for": ["you can't put weight on it", "numbness or color change", "calf swelling without injury"],
    },
    {
        "id": "headache",
        "name": "Headache",
        "match_terms": ["headache", "head hurts", "migraine", "head pain"],
        "ask_about": [
            {"topic": "onset", "why": "A sudden, worst-ever headache is a danger sign"},
            {"topic": "neuro_symptoms", "why": "Weakness, confusion, or vision changes are danger signs"},
            {"topic": "fever_stiff_neck", "why": "Fever with stiff neck is a danger sign"},
            {"topic": "head_injury", "why": "A recent head injury changes urgency"},
        ],
        "possible_cause_questions": ["Did it build up slowly after screen time, stress, or poor sleep?", "Have you had enough water and food today?", "Do you get headaches like this often?"],
        "danger_signs": [
            danger("sudden, worst headache of your life", CALL, "A sudden severe headache can be bleeding in the brain."),
            danger("headache with weakness, confusion, trouble speaking, or vision loss", CALL, "These can be signs of a stroke."),
            danger("headache with fever and stiff neck", ER, "This can be meningitis."),
            danger("headache after a head injury with vomiting or sleepiness", CALL, "This can be a brain injury."),
        ],
        "possible_causes": [
            cause("a tension headache", "Pressure-like pain often linked to stress, screens, or poor sleep.", "SELF_CARE"),
            cause("a migraine", "Throbbing pain, sometimes with nausea or light sensitivity.", "TELEHEALTH"),
            cause("dehydration or a skipped meal", "Headache that improves with fluids and food.", "SELF_CARE"),
        ],
        "watch_for": ["it becomes sudden and severe", "weakness, confusion, or vision changes", "fever with stiff neck"],
    },
    {
        "id": "breathing",
        "name": "Cough or breathing trouble",
        "match_terms": ["cough", "short of breath", "shortness of breath", "wheez", "breath", "breathing"],
        "ask_about": [
            {"topic": "at_rest", "why": "Trouble breathing at rest is a danger sign"},
            {"topic": "duration", "why": "How long it has lasted"},
            {"topic": "fever", "why": "Fever suggests infection"},
            {"topic": "asthma_history", "why": "Known asthma changes what to do"},
        ],
        "possible_cause_questions": ["Has anyone around you been sick?", "Did it start after exercise, smoke, or allergies?"],
        "danger_signs": [
            danger("can't breathe or speak in full sentences", CALL, "This is a breathing emergency."),
            danger("lips or face turning blue or gray", CALL, "This means low oxygen."),
            danger("short of breath while resting", CALL, "Breathing trouble at rest needs urgent evaluation."),
        ],
        "possible_causes": [
            cause("a common cold or viral infection", "Cough and congestion that improve over a week or two.", "TELEHEALTH"),
            cause("bronchitis", "A lingering cough after a cold.", "URGENT_CARE"),
            cause("allergies or asthma flare", "Wheezing or cough triggered by allergens or exercise.", "URGENT_CARE"),
        ],
        "watch_for": ["breathing gets harder at rest", "lips turn blue", "high fever that won't come down"],
    },
    {
        "id": "fever",
        "name": "Fever",
        "match_terms": ["fever", "temperature", "chills", "feverish"],
        "ask_about": [
            {"topic": "temperature_value", "why": "How high the fever is"},
            {"topic": "age", "why": "Fever in a young infant is an emergency"},
            {"topic": "other_symptoms", "why": "Where the infection might be"},
            {"topic": "drinking_and_alertness", "why": "Poor drinking or unusual sleepiness raises concern"},
        ],
        "possible_cause_questions": ["Has anyone around you been sick?", "Any recent travel?"],
        "danger_signs": [
            danger("fever in a baby under 3 months old", ER, "Young infants with fever need same-day emergency evaluation."),
            danger("fever with stiff neck and a rash that doesn't fade when pressed", CALL, "This can be a serious infection."),
            danger("fever with confusion or very hard to wake", CALL, "This can be a serious infection."),
        ],
        "possible_causes": [
            cause("a viral infection like a cold or flu", "Fever with body aches, cough, or sore throat.", "TELEHEALTH"),
            cause("an ear, throat, or urinary infection", "Fever with pain in one area.", "URGENT_CARE"),
        ],
        "watch_for": ["fever over 104F (40C)", "fever lasting more than 3 days", "trouble breathing, confusion, or a spreading rash"],
    },
    {
        "id": "sore_throat_ear",
        "name": "Sore throat or ear pain",
        "match_terms": ["sore throat", "throat", "ear pain", "earache", "ear hurts"],
        "ask_about": [
            {"topic": "fever", "why": "Fever with sore throat can mean strep"},
            {"topic": "swallowing_breathing", "why": "Trouble swallowing saliva or breathing is a danger sign"},
            {"topic": "duration", "why": "How long it has lasted"},
        ],
        "possible_cause_questions": ["Has anyone around you had strep throat or a cold?"],
        "danger_signs": [
            danger("can't swallow saliva or trouble breathing", CALL, "Severe throat swelling needs urgent care."),
        ],
        "possible_causes": [
            cause("a viral sore throat", "Often with a cold; improves in about a week.", "TELEHEALTH"),
            cause("strep throat", "Sore throat with fever and no cough; needs a test.", "URGENT_CARE"),
            cause("an ear infection", "Ear pain, sometimes with fever.", "URGENT_CARE"),
        ],
        "watch_for": ["trouble swallowing or breathing", "high fever", "symptoms lasting more than a week"],
    },
    {
        "id": "skin_allergy",
        "name": "Rash, hives, or allergic reaction",
        "match_terms": ["rash", "hives", "itch", "swelling", "allergic", "bite", "sting"],
        "ask_about": [
            {"topic": "breathing_swallowing", "why": "Breathing or swallowing trouble means a severe reaction"},
            {"topic": "trigger", "why": "A new food, medicine, product, or sting"},
            {"topic": "spread_and_fever", "why": "A spreading rash with fever raises concern"},
        ],
        "possible_cause_questions": ["Did you try a new food, medicine, soap, or detergent?", "Were you stung or bitten?"],
        "danger_signs": [
            danger("throat, tongue, or lip swelling, or trouble breathing", CALL, "This can be a severe allergic reaction (anaphylaxis)."),
            danger("rash with fever that doesn't fade when pressed", CALL, "This can be a serious infection."),
        ],
        "possible_causes": [
            cause("contact dermatitis", "An itchy rash from something that touched the skin, like a new detergent.", "TELEHEALTH"),
            cause("hives from a mild allergy", "Raised itchy welts that come and go.", "URGENT_CARE"),
        ],
        "watch_for": ["any swelling of lips, tongue, or throat", "trouble breathing", "fever with a spreading rash"],
    },
    {
        "id": "urinary",
        "name": "Urinary symptoms",
        "match_terms": ["pee", "urinat", "burning when", "uti", "bladder"],
        "ask_about": [
            {"topic": "fever_back_pain", "why": "Fever or back pain can mean a kidney infection"},
            {"topic": "blood", "why": "Blood in urine needs evaluation"},
            {"topic": "pregnancy", "why": "Changes treatment and urgency"},
        ],
        "possible_cause_questions": ["Have you had a urinary infection before?"],
        "danger_signs": [
            danger("fever with back or side pain and vomiting", ER, "This can be a kidney infection."),
        ],
        "possible_causes": [cause("a urinary tract infection", "Burning and frequent urination.", "URGENT_CARE")],
        "watch_for": ["fever, back pain, or vomiting", "blood in urine"],
    },
    {
        "id": "dizziness",
        "name": "Dizziness or fainting",
        "match_terms": ["dizzy", "lightheaded", "faint", "passed out", "vertigo"],
        "ask_about": [
            {"topic": "fainted", "why": "Actually passing out is more serious"},
            {"topic": "neuro_cardiac", "why": "Chest pain, palpitations, or weakness are danger signs"},
            {"topic": "fluids_food", "why": "Dehydration or not eating are common causes"},
        ],
        "possible_cause_questions": ["Have you eaten and had enough to drink today?", "Did it happen when you stood up quickly?"],
        "danger_signs": [
            danger("fainting with chest pain, racing heart, or shortness of breath", CALL, "This can be a heart problem."),
            danger("dizziness with weakness, confusion, or trouble speaking", CALL, "These can be signs of a stroke."),
            danger("fainted and didn't wake up quickly", CALL, "This needs emergency evaluation."),
        ],
        "possible_causes": [
            cause("dehydration or low blood sugar", "Lightheadedness that improves with fluids and food.", "SELF_CARE"),
            cause("standing up too quickly", "Brief dizziness when rising.", "SELF_CARE"),
            cause("an inner ear problem", "Spinning feeling that changes with head movement.", "PRIMARY_CARE"),
        ],
        "watch_for": ["you faint", "chest pain or racing heart", "weakness or trouble speaking"],
    },
    {
        "id": "mental_health",
        "name": "Mental health crisis",
        "match_terms": ["suicid", "kill myself", "end my life", "hurt myself", "self-harm"],
        "ask_about": [],
        "possible_cause_questions": [],
        "danger_signs": [
            danger("thoughts of suicide or harming yourself", CALL, "You deserve support right now. Call or text 988, or call 911 if you are in immediate danger."),
        ],
        "possible_causes": [],
        "watch_for": [],
        "note": "Never ask diagnostic follow-ups here. Show 988 and 911 immediately.",
    },
]

GUIDE = {
    "synthetic": True,
    "version": "2026-10-27",
    "disclaimer": "Simplified, not clinically validated. Possible causes are common possibilities only, never a diagnosis.",
    "hedging_rules": [
        "Say 'could be', 'one common possibility is', or 'a clinician needs to confirm'.",
        "Never say 'you have' or name a cause that is not listed for the matched cluster.",
        "Never name a medication or dose.",
    ],
    "clusters": CLUSTERS,
}

if __name__ == "__main__":
    out = Path(__file__).parent / "symptom_guide.json"
    out.write_text(json.dumps(GUIDE, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print("Wrote", out, len(CLUSTERS), "clusters")
