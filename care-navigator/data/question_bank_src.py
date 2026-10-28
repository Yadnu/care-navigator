"""Offline question bank, rebuilt from the symptom guide (CHANGE_conversational_triage.md Part 4, D-050).

One entry per `ask_about` topic in data/symptom_guide.json (template wording, quick replies, answer
patterns) plus one per `possible_cause_questions` item (the guide's own wording). generate.py writes
data/question_bank.json. Danger links only name a guide danger sign; the action always comes from the
guide, so there is one source of truth (D-048).

Answers and free text are lowercased, apostrophes removed and punctuation turned into spaces before
matching. Patterns starting with "^" only apply to a direct answer; the others may also fill a topic
from what the person already wrote (negation-aware). Options are checked in order. Synthetic and
simplified; not clinically validated.
"""

YES = [r"^(yes|yeah|yep|yup|i do|i am|it is|they are|there is)\b"]
NO = [r"^(no|nope|nah|none|not really|nothing|i dont|it isnt|its not|there isnt)\b"]


def opt(value, label, match):
    return {"value": value, "label": label, "match": match}


def link(values, cluster, sign):
    return {"values": values, "cluster": cluster, "sign": sign}


VD, AB, CH, ARM, LEG, HA, BR, FV, ST, SK, UR, DZ = (
    "vomiting_diarrhea", "abdominal_pain", "chest_pain", "arm_hand_injury", "leg_ankle_injury", "headache",
    "breathing", "fever", "sore_throat_ear", "skin_allergy", "urinary", "dizziness")

# topic -> question, options, danger links, routine (no-danger) value
TOPICS = {
    "main_symptom": dict(
        question="What is the main thing bothering you, and where on your body do you feel it?",
        options=[], danger=[], routine=None),
    "fluids_kept_down": dict(
        question="Can you keep water or other fluids down?",
        options=[opt("no", "No, nothing stays down", NO + [r"\b(cant|cannot|can not) keep\b", r"\bnothing (stays|is staying) down\b",
                                                          r"\beverything comes back up\b"]),
                 opt("some", "Some", [r"^some\b", r"\bsome (fluids? |water |of it )?(stays?|staying)\b", r"\bsmall sips?\b", r"\ba little\b"]),
                 opt("yes", "Yes", YES + [r"\bcan keep\b", r"\bkeeping \w+( \w+)? down\b", r"\bstaying down\b", r"\bstill drinking\b",
                                         r"\bdrinking (fine|ok|okay|well|normally)\b"])],
        danger=[link(["no"], VD, "unable to keep any fluids down for many hours")], routine="yes"),
    "duration_and_frequency": dict(
        question="How long has this been going on, and how often is it happening?",
        options=[opt("hours", "A few hours", [r"\bhours?\b", r"\btoday\b", r"\btonight\b", r"\bsince (dinner|lunch|breakfast|this morning)\b"]),
                 opt("day", "About a day", [r"\b(a|one|1) day\b", r"\byesterday\b"]),
                 opt("days", "Several days", [r"\b([2-9]|two|three|four|five|several|few) days\b", r"\bweeks?\b"])],
        danger=[], routine="hours"),
    "blood": dict(
        question="Have you seen any blood in your vomit, stool or urine, or vomit that looks like coffee grounds?",
        options=[opt("no", "No", NO + [r"\bno blood\b"]),
                 opt("stool", "Yes, in stool", [r"\b(stool|poop|bowel movement)\b"]),
                 opt("urine", "Yes, in urine", [r"\b(urine|pee)\b"]),
                 opt("vomit", "Yes, in vomit", YES + [r"\bvomit\w*\b", r"\bcoffee grounds\b", r"\bthrowing up blood\b"])],
        danger=[link(["vomit"], VD, "vomiting blood or material that looks like coffee grounds"),
                link(["stool"], VD, "black or bloody stool")], routine="no"),
    "dehydration_signs": dict(
        question="Do you feel dizzy when you stand up, or are you peeing much less than usual?",
        options=[opt("no", "No", NO + [r"\bnot dizzy\b", r"\bpeeing (fine|normally|ok)\b"]),
                 opt("yes", "Yes", YES + [r"\bdizz\w*", r"\blight ?headed\b", r"\b(barely|hardly|much less|not) pee\w*", r"\bhavent peed\b"])],
        danger=[link(["yes"], VD, "dizzy or faint when standing, or very little urine")], routine="no"),
    "fever": dict(
        question="Is there any fever, or have you felt hot and shivery?",
        options=[opt("no", "No", NO + [r"\bno fever\b"]),
                 opt("yes", "Yes", YES + [r"\bfever\w*", r"\b10[0-6]f?\b", r"\bchills\b", r"\bhot and\b"])],
        danger=[], routine="no"),
    "abdominal_pain": dict(
        question="Any belly pain with it, and if so, is it severe or in one spot?",
        options=[opt("no", "No", NO + [r"\bno (belly |stomach )?pain\b"]),
                 opt("severe", "Yes, severe or in one spot", [r"\bsevere\b", r"\bone (spot|side)\b", r"\bworst\b", r"\bhard belly\b"]),
                 opt("mild", "Mild cramps", YES + [r"\bmild\b", r"\ba little\b", r"\bcramp\w*", r"\bcomes and goes\b"])],
        danger=[link(["severe"], VD, "severe or worsening belly pain, or a hard belly")], routine="no"),
    "location": dict(
        question="Where is the belly pain: upper, lower right, lower left, or all over?",
        options=[opt("lower_right", "Lower right", [r"\b(lower right|right lower|bottom right)\b"]),
                 opt("upper", "Upper", [r"\bupper\b", r"\btop\b", r"\bunder (my |the )?ribs\b"]),
                 opt("lower_left", "Lower left", [r"\b(lower left|left lower|bottom left)\b"]),
                 opt("all_over", "Everywhere", [r"\ball over\b", r"\beverywhere\b", r"\b(middle|around)\b"])],
        danger=[], routine="all_over"),
    "onset_and_trend": dict(
        question="Is the pain getting better, staying about the same, or getting worse?",
        options=[opt("worse", "Getting worse", [r"\bworse\b", r"\bworsening\b"]),
                 opt("better", "Getting better", [r"\bbetter\b", r"\bimproving\b", r"\beasing\b"]),
                 opt("same", "About the same", [r"\bsame\b", r"\bsteady\b", r"\bcomes and goes\b"])],
        danger=[link(["worse"], VD, "severe or worsening belly pain, or a hard belly")], routine="same"),
    "severity": dict(
        question="On a scale of 1 to 10, how bad is the pain right now?",
        options=[opt("mild", "1 to 3", [r"^[1-3]\b", r"\bmild\b"]),
                 opt("moderate", "4 to 6", [r"^[4-6]\b", r"\bmoderate\b", r"\bmedium\b"]),
                 opt("severe", "7 to 10", [r"^([7-9]|10)\b", r"\bsevere\b", r"\bworst\b"])],
        danger=[], routine="moderate"),
    "fever_vomiting": dict(
        question="Any fever or vomiting along with the pain?",
        options=[opt("no", "No", NO), opt("yes", "Yes", YES + [r"\bfever\w*", r"\bvomit\w*", r"\bthrowing up\b"])],
        danger=[], routine="no"),
    "bowel_urine_changes": dict(
        question="Any change in your stool or urine, like diarrhea, blood, or burning when you pee?",
        options=[opt("no", "No", NO),
                 opt("blood", "Blood or black stool", [r"\bblood\w*", r"\bblack (stool|poop)\b"]),
                 opt("burning", "Burning when I pee", [r"\bburning\b", r"\bpee\w* hurts\b"]),
                 opt("diarrhea", "Diarrhea", [r"\bdiarrh\w*", r"\bloose\b"])],
        danger=[link(["blood"], VD, "black or bloody stool")], routine="no"),
    "character": dict(
        question="Does the chest discomfort feel crushing, squeezing or heavy, or sharp and sore when you press on it?",
        options=[opt("sharp", "Sharp, sore when pressed", [r"\bsharp\b", r"\bsore\b", r"\bwhen i press\b", r"\btender\b"]),
                 opt("crushing", "Crushing, squeezing or heavy", [r"\bcrush\w*", r"\bsqueez\w*", r"\bheavy\b", r"\bpressure\b", r"\btight\w*"])],
        danger=[link(["crushing"], CH, "crushing, squeezing, or heavy chest pain")], routine="sharp"),
    "associated_symptoms": dict(
        question="Any sweating, shortness of breath, nausea, or pain spreading to your arm, jaw or back?",
        options=[opt("no", "No", NO),
                 opt("yes", "Yes", YES + [r"\bsweat\w*", r"\b(short|shortness) of breath\b", r"\bnause\w*", r"\bspread\w*",
                                         r"\b(arm|jaw)\b"])],
        danger=[link(["yes"], CH, "chest pain with sweating, shortness of breath, nausea, or pain spreading to the arm, jaw, or back")],
        routine="no"),
    "trigger": dict(
        question="Did it start during activity, or after a workout, heavy lifting, lots of coughing, or something new you ate or used?",
        options=[opt("none", "Nothing I can think of", NO + [r"\bnot sure\b"]),
                 opt("activity", "During activity", [r"\bduring (activity|exercise|exertion)\b", r"\bwhen i (walk|exercise|climb)\w*",
                                                    r"\bclimbing stairs\b"]),
                 opt("after_exercise", "After a workout, lifting or coughing", [r"\bafter (a |my )?(workout|lifting|gym|exercise|coughing)\b",
                                                                               r"\blift\w*", r"\bbench\b", r"\bcough\w*"]),
                 opt("new_exposure", "Something new I ate or used", [r"\bnew (food|soap|detergent|lotion|product)\b", r"\bate\b",
                                                                     r"\bsting\b", r"\bbitten\b"])],
        danger=[link(["activity"], CH, "chest pain with exertion that goes away with rest")], routine="none"),
    "duration": dict(
        question="How long has this been going on?",
        options=[opt("hours", "A few hours", [r"\bhours?\b", r"\btoday\b", r"\btonight\b"]),
                 opt("days", "A day or two", [r"\b(a|one|two|1|2) days?\b", r"\byesterday\b"]),
                 opt("week_plus", "A week or more", [r"\bweeks?\b", r"\bmonths?\b"])],
        danger=[], routine="days"),
    "injury_mechanism": dict(
        question="Did this start after a fall, twist, lift, sport or other injury?",
        options=[opt("no", "No injury", NO + [r"\bno injury\b", r"\bout of nowhere\b"]),
                 opt("yes", "Yes, after an injury", YES + [
                     r"\b(fell|fall|twisted|lifted|lifting|tripped|bumped|played|carrying|carried)\b",
                     r"\b(volleyball|soccer|basketball|football|tennis|skating|skiing|hike|hiking|gym|workout)\b"])],
        danger=[], routine="yes"),
    "swelling_or_deformity": dict(
        question="Is the area swollen or bruised, or does it look out of its usual shape?",
        options=[opt("deformed", "It looks out of shape", [r"\bout of (its )?(usual )?shape\b", r"\bdeformed\b", r"\blooks bent\b",
                                                         r"\bbone (is )?(visible|sticking|showing)\b"]),
                 opt("no", "No", NO),
                 opt("yes", "Yes, swollen or bruised", YES + [r"\bswollen\b", r"\bswelling\b", r"\bbruis\w*"])],
        danger=[link(["deformed"], ARM, "bone visible or limb clearly deformed")], routine="no"),
    "can_use": dict(
        question="Can you use it normally, like gripping or moving your fingers and wrist?",
        options=[opt("no", "No, I can't", NO + [r"\b(cant|cannot|can not|unable to) (use|move|grip|bend)\b"]),
                 opt("yes", "Yes, mostly", YES + [r"\bcan (use|move|grip|bend)\b", r"\bmoving fine\b"])],
        danger=[], routine="yes"),
    "numbness": dict(
        question="Are your hand or fingers numb, tingling, cold or pale?",
        options=[opt("no", "No", NO),
                 opt("yes", "Yes", YES + [r"\bnumb\w*", r"\btingl\w*", r"\bcold\b", r"\bpale\b", r"\bpins and needles\b"])],
        danger=[link(["yes"], ARM, "hand or fingers cold, pale, or numb after an injury")], routine="no"),
    "cardiac_screen": dict(
        question="Along with this, is there any chest pain or pressure, shortness of breath, sweating or nausea?",
        options=[opt("no", "No", NO),
                 opt("yes", "Yes", YES + [r"\bchest\b", r"\bsweat\w*", r"\bclammy\b", r"\b(short|shortness) of breath\b", r"\bnause\w*"])],
        danger=[link(["yes"], ARM, "arm pain with chest pain, shortness of breath, sweating, or nausea")], routine="no"),
    "can_bear_weight": dict(
        question="Can you put weight on it and take a few steps?",
        options=[opt("no", "No, I can't", NO + [r"\b(cant|cannot|can not|unable to) (walk|put weight|stand|bear)\b"]),
                 opt("yes", "Yes", YES + [r"\bcan (walk|stand|put weight)\b", r"\bwalk (on it|a little)\b", r"\blimping\b"])],
        danger=[], routine="yes"),
    "calf_swelling": dict(
        question="Is one calf swollen, warm and painful without an injury?",
        options=[opt("no", "No", NO), opt("yes", "Yes", YES + [r"\bcalf\b"])],
        danger=[link(["yes"], LEG, "one calf swollen, warm, and painful without injury")], routine="no"),
    "onset": dict(
        question="Did the headache start suddenly, within seconds to a minute, or build up gradually?",
        options=[opt("sudden", "Suddenly", [r"\bsudden\w*", r"\ball at once\b", r"\bout of nowhere\b", r"\bthunderclap\b", r"\binstantly\b"]),
                 opt("gradual", "Gradually", [r"\bgradual\w*", r"\bslow\w*", r"\bbuil[dt] up\b", r"\bover (the day|hours|time)\b",
                                             r"\bafter (work|a long day|school)\b", r"\bscreens?\b", r"\blong day\b"])],
        danger=[link(["sudden"], HA, "sudden, worst headache of your life")], routine="gradual"),
    "neuro_symptoms": dict(
        question="Any weakness, confusion, trouble speaking, or changes in your vision?",
        options=[opt("no", "No", NO),
                 opt("yes", "Yes", YES + [r"\bweak\w*", r"\bconfus\w*", r"\btrouble speaking\b", r"\bslurr\w*", r"\bvision\b",
                                         r"\bblurr\w*", r"\bcant see\b"])],
        danger=[link(["yes"], HA, "headache with weakness, confusion, trouble speaking, or vision loss")], routine="no"),
    "fever_stiff_neck": dict(
        question="Is there a fever together with a stiff neck?",
        options=[opt("no", "No", NO), opt("yes", "Yes", YES + [r"\bstiff neck\b"])],
        danger=[link(["yes"], HA, "headache with fever and stiff neck")], routine="no"),
    "head_injury": dict(
        question="Did this start after a hit to the head, and since then any vomiting or unusual sleepiness?",
        options=[opt("no", "No", NO),
                 opt("with_signs", "Yes, with vomiting or sleepiness", [r"\bvomit\w*", r"\bthrowing up\b", r"\bsleepy\b", r"\bdrowsy\b"]),
                 opt("yes", "Yes, but no vomiting or sleepiness", YES + [r"\bhit (my |his |her )?head\b", r"\bbumped\b"])],
        danger=[link(["with_signs"], HA, "headache after a head injury with vomiting or sleepiness")], routine="no"),
    "at_rest": dict(
        question="Are you short of breath even while resting or sitting still?",
        options=[opt("no", "No, only with activity", NO + [
                     r"\bonly (after|when|with|on|during)\b", r"\bfine (at|when) rest\w*", r"\bnormal again\b", r"\bgoes away\b",
                     r"\bbetter (at|when) rest\w*", r"\bafter (running|stairs|climbing|exercise|exercising|a run|working out)\b"]),
                 opt("yes", "Yes, even at rest", YES + [r"\beven (sitting|resting|lying|at rest)\b", r"\bat rest\b", r"\bsitting still\b",
                                                       r"\ball the time\b"])],
        danger=[link(["yes"], BR, "short of breath while resting")], routine="no"),
    "asthma_history": dict(
        question="Have you had wheezing or breathing trouble like this before?",
        options=[opt("no", "No", NO), opt("yes", "Yes", YES + [r"\bwheez\w*", r"\bbefore\b"])],
        danger=[], routine="no"),
    "temperature_value": dict(
        question="What was the highest temperature you measured?",
        options=[opt("over_102", "Over 102F", [r"\b10[3-7]f?\b"]),
                 opt("100_4_to_102", "100.4F to 102F", [r"\b10[12]f?\b", r"\b100 [4-9]\b"]),
                 opt("under_100_4", "Under 100.4F", [r"\b9\d(f| [0-9])?\b", r"\b100f?\b", r"\b100 [0-3]\b"])],
        danger=[], routine="100_4_to_102"),
    "age": dict(
        question="How old is the person with the fever?",
        options=[opt("under_3_months", "Under 3 months", [r"\bunder (3|three) months\b", r"\bnewborn\b", r"\b[0-2] months?( old)?\b",
                                                          r"\b\d+ (days?|weeks?) old\b", r"^\d+ (days?|weeks?)\b"]),
                 opt("3_to_12_months", "3 to 12 months", [r"\b([3-9]|1[0-2]) months?( old)?\b"]),
                 opt("child", "1 to 17 years", [r"\b([1-9]|1[0-7]) (years?|yrs?)( old)?\b", r"\btoddler\b"]),
                 opt("adult", "18 or older", [r"\badult\b", r"\b(1[89]|[2-9]\d) (years?|yrs?)?\b", r"\bme\b", r"\bmyself\b"])],
        danger=[link(["under_3_months"], FV, "fever in a baby under 3 months old")], routine="adult"),
    "other_symptoms": dict(
        question="Besides the fever, are there other symptoms, like cough, sore throat, ear pain or a rash?",
        options=[opt("none", "No, just the fever", NO + [r"\bnothing else\b", r"\bjust the fever\b"]),
                 opt("some", "Yes", YES + [r"\bcough\w*", r"\bthroat\b", r"\bear\b", r"\brash\b", r"\bvomit\w*", r"\bdiarrh\w*"])],
        danger=[], routine="none"),
    "drinking_and_alertness": dict(
        question="Are they drinking normally and acting alert, or very sleepy and hard to wake?",
        options=[opt("hard_to_wake", "Very sleepy or hard to wake", [r"\bhard to wake\b", r"\bvery sleepy\b", r"\bconfus\w*", r"\blimp\b",
                                                                     r"\bnot responding\b"]),
                 opt("poor_drinking", "Not drinking much", [r"\bnot drinking\b", r"\bwont drink\b", r"\brefus\w*"]),
                 opt("alert", "Drinking and alert", YES + [r"\bdrinking (well|fine|normally|ok)\b", r"\balert\b", r"\bplaying\b",
                                                          r"\bacting normal\b"])],
        danger=[link(["hard_to_wake"], FV, "fever with confusion or very hard to wake")], routine="alert"),
    "swallowing_breathing": dict(
        question="Can you swallow your saliva, and is your breathing normal?",
        options=[opt("trouble", "No, trouble swallowing or breathing", [r"^no\b", r"\b(cant|cannot) (swallow|breathe)\b", r"\bdrool\w*",
                                                                        r"\btrouble (breathing|swallowing)\b", r"\bhard to breathe\b"]),
                 opt("ok", "Yes, both fine", YES + [r"\bfine\b", r"\bnormal\b", r"\bcan swallow\b"])],
        danger=[link(["trouble"], ST, "can't swallow saliva or trouble breathing")], routine="ok"),
    "breathing_swallowing": dict(
        question="Any swelling of your lips, tongue or throat, or trouble breathing or swallowing?",
        options=[opt("no", "No", NO),
                 opt("yes", "Yes", YES + [r"\blips?\b", r"\btongue\b", r"\bthroat\b", r"\btrouble (breathing|swallowing)\b",
                                         r"\b(short|shortness) of breath\b"])],
        danger=[link(["yes"], SK, "throat, tongue, or lip swelling, or trouble breathing")], routine="no"),
    "spread_and_fever": dict(
        question="Is the rash spreading, and is there a fever or a rash that doesn't fade when pressed?",
        options=[opt("no", "No", NO),
                 opt("not_fading", "Rash doesn't fade when pressed", [r"\b(doesnt|does not|wont|will not) fade\b", r"\bnot fad\w*"]),
                 opt("fever", "Fever", [r"\bfever\w*"]),
                 opt("spreading", "Spreading", YES + [r"\bspread\w*", r"\bgetting bigger\b"])],
        danger=[link(["not_fading"], SK, "rash with fever that doesn't fade when pressed")], routine="no"),
    "fever_back_pain": dict(
        question="Any fever, pain in your back or side, or vomiting?",
        options=[opt("no", "No", NO), opt("yes", "Yes", YES + [r"\bfever\w*", r"\bback\b", r"\bside\b", r"\bvomit\w*"])],
        danger=[link(["yes"], UR, "fever with back or side pain and vomiting")], routine="no"),
    "pregnancy": dict(
        question="Is there any chance you could be pregnant?",
        options=[opt("no", "No", NO + [r"\bnot pregnant\b"]),
                 opt("yes", "Yes or maybe", YES + [r"\bpregnant\b", r"\bmaybe\b", r"\bpossibly\b"])],
        danger=[], routine="no"),
    "fainted": dict(
        question="Did you actually pass out, and if so, did you wake up quickly?",
        options=[opt("no", "No", NO + [r"\bdidnt (pass|faint)\b"]),
                 opt("slow_wake", "Yes, and it took a while to wake", [r"\bdidnt wake (up )?quickly\b", r"\btook (a while|long) to wake\b"]),
                 opt("yes_quick", "Yes, but woke quickly", YES + [r"\bwoke (up )?quickly\b"])],
        danger=[link(["slow_wake"], DZ, "fainted and didn't wake up quickly")], routine="no"),
    "neuro_cardiac": dict(
        question="Any chest pain, racing heart, shortness of breath, weakness, confusion, or trouble speaking?",
        options=[opt("no", "No", NO),
                 opt("yes", "Yes", YES + [r"\bchest\b", r"\bracing\b", r"\bpound\w*", r"\b(short|shortness) of breath\b", r"\bweak\w*",
                                         r"\bconfus\w*", r"\btrouble speaking\b", r"\bslurr\w*"])],
        danger=[link(["yes"], DZ, "fainting with chest pain, racing heart, or shortness of breath")], routine="no"),
    "fluids_food": dict(
        question="Have you eaten and had enough to drink today?",
        options=[opt("no", "No, not much", NO + [r"\bskipped\b", r"\bhavent eaten\b", r"\bnot much\b"]),
                 opt("yes", "Yes", YES + [r"\bate\b", r"\beaten\b", r"\bdrank\b", r"\bdrinking\b"])],
        danger=[], routine="yes"),
}

CAUSE_NO = NO + [r"\b(fine|nobody|no one|none|nothing|well|okay)\b"]
CAUSE_UNSURE = [r"\bnot sure\b", r"\bmaybe\b", r"\bdont know\b", r"\bunsure\b"]

# Which possible cause an answer to a possible-cause question points to: (guide cluster, question
# index) -> (cause, the answer value that points to it). Two questions point to a cause on "no"
# ("Have you had enough water and food today?").
CAUSE_HINTS = {
    (VD, 0): ("food poisoning", "yes"), (VD, 1): ("food poisoning", "yes"),
    (VD, 2): ("a stomach bug (viral gastroenteritis)", "yes"), (VD, 3): ("a reaction to a medication or alcohol", "yes"),
    (AB, 0): ("indigestion or acid reflux", "yes"),
    (CH, 0): ("a strained chest muscle", "yes"), (CH, 1): ("a strained chest muscle", "yes"),
    (ARM, 0): ("a sprain or strain", "yes"), (ARM, 1): ("a small fracture", "yes"),
    (LEG, 0): ("an ankle or knee sprain", "yes"),
    (HA, 0): ("a tension headache", "yes"), (HA, 1): ("dehydration or a skipped meal", "no"), (HA, 2): ("a migraine", "yes"),
    (BR, 0): ("a common cold or viral infection", "yes"), (BR, 1): ("allergies or asthma flare", "yes"),
    (FV, 0): ("a viral infection like a cold or flu", "yes"),
    (ST, 0): ("strep throat", "yes"),
    (SK, 0): ("contact dermatitis", "yes"), (SK, 1): ("hives from a mild allergy", "yes"),
    (UR, 0): ("a urinary tract infection", "yes"),
    (DZ, 0): ("dehydration or low blood sugar", "no"), (DZ, 1): ("standing up too quickly", "yes"),
}


def build_bank(guide: dict) -> list[dict]:
    """The question bank entries, in a stable order: main symptom, guide topics, cause questions."""
    clusters_for: dict[str, list[str]] = {"main_symptom": ["any"]}
    for cluster in guide["clusters"]:
        for item in cluster["ask_about"]:
            clusters_for.setdefault(item["topic"], []).append(cluster["id"])
    missing = set(clusters_for) - set(TOPICS)
    if missing:
        raise ValueError(f"question_bank_src.py has no template for guide topics {sorted(missing)}")

    bank = []
    for topic, clusters in clusters_for.items():
        t = TOPICS[topic]
        kind = "safety" if t["danger"] else "detail"
        bank.append({"topic": topic, "kind": kind, "clusters": clusters, "question": t["question"],
                     "quick_replies": [o["label"] for o in t["options"]], "options": t["options"],
                     "danger": t["danger"], "routine_value": t["routine"], "cause": None, "cause_on": None})
    for cluster in guide["clusters"]:
        for i, question in enumerate(cluster["possible_cause_questions"]):
            hint = CAUSE_HINTS.get((cluster["id"], i))
            bank.append({"topic": f"{cluster['id']}.cause{i + 1}", "kind": "cause", "clusters": [cluster["id"]],
                         "question": question, "quick_replies": ["Yes", "No", "Not sure"],
                         "options": [opt("no", "No", CAUSE_NO), opt("unsure", "Not sure", CAUSE_UNSURE),
                                     opt("yes", "Yes", [r"\w"])],
                         "danger": [], "routine_value": "no", "cause": hint[0] if hint else None,
                         "cause_on": hint[1] if hint else None})
    return bank
