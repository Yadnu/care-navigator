"""Question bank for multi-turn clarification (written to data/question_bank.json by generate.py).

Every question the system asks comes from here. Claude may only rephrase the text.
Answers and free text are lowercased, apostrophes removed and punctuation turned into
spaces before matching. Patterns starting with "^" only apply to a direct answer;
the others are also used to fill the slot from anything the person already wrote
(negation-aware, so "no swelling" doesn't count as swelling).

kind: "safety" questions check for danger signs; "detail" questions fill a slot the
care rules need. danger_values: option values that route straight to EMERGENCY.
routine_value: the no-danger answer used by the eval runner for scripted runs.
Synthetic and simplified; not clinically validated.
"""

YES = [r"^(yes|yeah|yep|yup|i do|i am|it is|they are)\b"]
NO = [r"^(no|nope|nah|none|not really|nothing|i dont|it isnt|its not)\b"]

QUESTION_BANK = [
    {
        "slot": "main_symptom", "kind": "detail", "categories": ["any"],
        "question": "What is the main thing bothering you, and where on your body do you feel it?",
        "options": [], "danger_values": [], "routine_value": None,
    },
    {
        "slot": "duration", "kind": "detail", "categories": ["any"],
        "question": "How long has this been going on?",
        "options": [
            {"value": "hours", "label": "A few hours", "match": [r"\bhours?\b", r"\btoday\b", r"\btonight\b"]},
            {"value": "days", "label": "A day or two", "match": [r"\b(a|one|two|1|2) days?\b", r"\byesterday\b"]},
            {"value": "week_plus", "label": "A week or more", "match": [r"\bweeks?\b", r"\bmonths?\b"]},
        ],
        "danger_values": [], "routine_value": "days",
    },
    {
        "slot": "severity_now", "kind": "detail", "categories": ["any"],
        "question": "Right now, how bad is it on a scale of 1 to 10?",
        "options": [
            {"value": "mild", "label": "1 to 3, mild", "match": [r"^[1-3]\b", r"\bmild\b"]},
            {"value": "moderate", "label": "4 to 6, moderate", "match": [r"^[4-6]\b", r"\bmoderate\b"]},
            {"value": "severe", "label": "7 to 10, severe", "match": [r"^([7-9]|10)\b", r"\bsevere\b"]},
        ],
        "danger_values": [], "routine_value": "moderate",
    },
    {
        "slot": "location_detail", "kind": "detail", "categories": ["any"],
        "question": "Where exactly do you feel it?",
        "options": [], "danger_values": [], "routine_value": None,
    },
    {
        "slot": "injury_mechanism", "kind": "detail", "categories": ["musculoskeletal"],
        "question": "Did this start after a fall, twist, lift, sport or other injury?",
        "options": [
            {"value": "no", "label": "No injury", "match": NO + [r"\bno injury\b", r"\bout of nowhere\b"]},
            {"value": "yes", "label": "Yes, after an injury", "match": YES + [
                r"\b(fell|fall|twisted|lifted|lifting|tripped|bumped|played|carrying|carried)\b",
                r"\b(volleyball|soccer|basketball|football|tennis|skating|skiing|hike|hiking|gym|workout)\b"]},
        ],
        "danger_values": [], "routine_value": "yes",
    },
    {
        "slot": "swelling_or_deformity", "kind": "detail", "categories": ["musculoskeletal"],
        "question": "Is the area swollen, bruised or out of its usual shape?",
        "options": [
            {"value": "no", "label": "No", "match": NO},
            {"value": "yes", "label": "Yes", "match": YES + [r"\bswollen\b", r"\bswelling\b", r"\bbruis\w*",
                                                           r"\bout of shape\b", r"\bdeformed\b", r"\blooks bent\b"]},
        ],
        "danger_values": [], "routine_value": "no",
    },
    {
        "slot": "can_use_or_bear_weight", "kind": "detail", "categories": ["musculoskeletal"],
        "question": "Can you use it normally or put weight on it?",
        "options": [
            {"value": "no", "label": "No, I can't", "match": NO + [
                r"\b(cant|cannot|can not|unable to) (use|move|walk|put weight|bear|grip|bend|stand)\b"]},
            {"value": "yes", "label": "Yes, mostly", "match": YES + [
                r"\bcan (use|move|walk|bend|grip|stand)\b", r"\bwalk (on it|a little)\b", r"\bmoving fine\b"]},
        ],
        "danger_values": [], "routine_value": "yes",
    },
    {
        "slot": "associated_cardiac_symptoms", "kind": "safety", "categories": ["any"],
        "question": "Along with this, is there any chest pain or pressure, shortness of breath, sweating or nausea?",
        "options": [
            {"value": "no", "label": "No", "match": NO},
            {"value": "yes", "label": "Yes", "match": YES + [r"\bchest\b", r"\bsweat\w*", r"\bclammy\b",
                                                           r"\b(short|shortness) of breath\b", r"\bnause\w*"]},
        ],
        "danger_values": ["yes"], "routine_value": "no",
    },
    {
        "slot": "headache_onset", "kind": "safety", "categories": ["neuro"],
        "question": "Did the headache start suddenly, within seconds to a minute, or build up gradually?",
        "options": [
            {"value": "sudden", "label": "Suddenly", "match": [r"\bsudden\w*", r"\ball at once\b", r"\bout of nowhere\b",
                                                              r"\bthunderclap\b", r"\binstantly\b"]},
            {"value": "gradual", "label": "Gradually", "match": [r"\bgradual\w*", r"\bslow\w*", r"\bbuil[dt] up\b",
                                                                r"\bover (the day|hours|time)\b",
                                                                r"\bafter (work|a long day|school)\b",
                                                                r"\blong day\b"]},
        ],
        "danger_values": ["sudden"], "routine_value": "gradual",
    },
    {
        "slot": "breathing_at_rest", "kind": "safety", "categories": ["respiratory"],
        "question": "Are you short of breath even while resting or sitting still?",
        "options": [
            {"value": "no", "label": "No, only with activity", "match": NO + [
                r"\bonly (after|when|with|on|during)\b", r"\bfine (at|when) rest\w*", r"\bnormal again\b",
                r"\bgoes away\b", r"\bbetter (at|when) rest\w*",
                r"\bafter (running|stairs|climbing|exercise|exercising|a run|working out)\b"]},
            {"value": "yes", "label": "Yes, even at rest", "match": YES + [
                r"\beven (sitting|resting|lying|at rest)\b", r"\bat rest\b", r"\bsitting still\b", r"\ball the time\b"]},
        ],
        "danger_values": ["yes"], "routine_value": "no",
    },
    {
        "slot": "fluids_kept_down", "kind": "safety", "categories": ["gastrointestinal"],
        "question": "Can you keep water or other fluids down?",
        "options": [
            {"value": "no", "label": "No, it comes back up", "match": NO + [
                r"\b(cant|cannot|can not) keep\b", r"\bnothing (stays|is staying) down\b",
                r"\beverything comes back up\b"]},
            {"value": "yes", "label": "Yes", "match": YES + [
                r"\bcan keep\b", r"\bkeeping \w+( \w+)? down\b", r"\bstaying down\b", r"\bstill drinking\b",
                r"\bdrinking (fine|ok|okay|well|normally)\b"]},
        ],
        "danger_values": ["no"], "routine_value": "yes",
    },
    {
        "slot": "urine_output", "kind": "detail", "categories": ["gastrointestinal"],
        "question": "Have you been peeing much less than usual today?",
        "options": [
            {"value": "no", "label": "No, about normal", "match": NO + [r"\bpeeing (fine|normally|ok)\b"]},
            {"value": "yes", "label": "Yes, much less", "match": YES + [r"\bhavent peed\b", r"\bbarely peed\b"]},
        ],
        "danger_values": [], "routine_value": "no",
    },
    {
        "slot": "fever_value", "kind": "detail", "categories": ["fever"],
        "question": "If there is a fever, what was the highest temperature?",
        "options": [
            {"value": "under_100_4", "label": "Under 100.4", "match": [r"\b(9[5-9]|100)( [0-3])?\b"]},
            {"value": "100_4_to_102", "label": "100.4 to 102", "match": [r"\b(10[01])( [4-9])?\b", r"\b102\b"]},
            {"value": "over_102", "label": "Over 102", "match": [r"\b10[3-7]\b"]},
        ],
        "danger_values": [], "routine_value": "100_4_to_102",
    },
    {
        "slot": "child_age", "kind": "safety", "categories": ["fever"],
        "question": "How old is your child?",
        "options": [
            {"value": "under_3_months", "label": "Under 3 months", "match": [
                r"\bunder (3|three) months\b", r"\bnewborn\b", r"\b[0-2] months? old\b", r"\b\d+ (days?|weeks?) old\b",
                r"^[0-2] months?\b", r"^\d+ (days?|weeks?)\b"]},
            {"value": "3_to_12_months", "label": "3 to 12 months", "match": [
                r"\b([3-9]|1[0-2]) months?( old)?\b"]},
            {"value": "1_to_5_years", "label": "1 to 5 years", "match": [r"\b[1-5] (years?|yrs?)( old)?\b", r"\btoddler\b"]},
            {"value": "6_years_plus", "label": "6 years or older", "match": [r"\b([6-9]|1[0-7]) (years?|yrs?)( old)?\b"]},
        ],
        "danger_values": ["under_3_months"], "routine_value": "1_to_5_years",
    },
    {
        "slot": "abdominal_location_and_trend", "kind": "safety", "categories": ["gastrointestinal"],
        "question": "Where is the belly pain, and is it getting better or worse?",
        "options": [
            {"value": "lower_right_worse", "label": "Lower right, getting worse", "match": [
                r"\blower right\b.{0,40}\b(worse|worsening|fever)\b",
                r"\b(worse|worsening)\b.{0,40}\blower right\b"]},
            {"value": "upper", "label": "Upper belly or burning", "match": [
                r"\bupper\b", r"\bburning\b", r"\bheartburn\b", r"\bafter (food|eating|a meal|spicy)\b"]},
            {"value": "mild_or_better", "label": "All over, mild or getting better", "match": [
                r"\ball over\b", r"\bmild\b", r"\bgetting better\b", r"\bcomes and goes\b"]},
        ],
        "danger_values": ["lower_right_worse"], "routine_value": "mild_or_better",
    },
]
