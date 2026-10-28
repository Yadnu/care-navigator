"""The curated symptom guide, data/symptom_guide.json (D-047, D-048).

Matches the conversation to clusters (negation-aware `match_terms`, plus the Jev category) and
scores the possible causes. Possible causes are hedged common possibilities, never a diagnosis.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Optional

from navigator.data import DATA_DIR
from navigator.redflags import TextView

# Jev / lexicon category -> the guide cluster it supports when no match term matched.
CATEGORY_CLUSTER = {
    "gastrointestinal": "vomiting_diarrhea",
    "neuro": "headache",
    "respiratory": "breathing",
    "ent": "sore_throat_ear",
    "fever": "fever",
    "skin": "skin_allergy",
    "allergy": "skin_allergy",
    "urinary": "urinary",
}
STOPWORDS = {"with", "from", "that", "this", "often", "like", "your", "when", "after", "sometimes", "usually",
             "common", "about", "have", "more", "than", "into", "there", "comes", "goes", "pain", "some", "yes",
             "fine", "well", "none", "sure", "same", "feel", "feels"}


@lru_cache(maxsize=1)
def load_guide() -> dict:
    return json.loads((DATA_DIR / "symptom_guide.json").read_text(encoding="utf-8"))


def clusters() -> dict[str, dict]:
    return {c["id"]: c for c in load_guide()["clusters"]}


def sign_by_text(cluster: str, sign: str) -> dict:
    """A guide danger sign with its cluster id added."""
    for d in clusters()[cluster]["danger_signs"]:
        if d["sign"] == sign:
            return {**d, "cluster": cluster}
    raise KeyError(f"no danger sign {sign!r} in cluster {cluster!r}")


def _term_pattern(term: str) -> str:
    """A match term is a word prefix: "vomit" matches "vomiting", "urinat" matches "urinating"."""
    words = re.sub(r"[^a-z0-9 ]+", " ", term.lower().replace("'", "")).split()
    return r"\b" + r" ".join(re.escape(w) for w in words) + r"\w*"


def match_clusters(text: str, category: Optional[str] = None, limit: int = 2) -> list[str]:
    """Clusters whose match terms appear (not negated) in the text, most hits first, then guide
    order; the Jev category's cluster is added when no term matched. At most `limit`."""
    view = TextView(text)
    scored = []
    for i, c in enumerate(load_guide()["clusters"]):
        hits = sum(1 for t in c["match_terms"] if view.find(_term_pattern(t)))
        if hits:
            scored.append((-hits, i, c["id"]))
    found = [cid for _, _, cid in sorted(scored)]
    if not found and category in CATEGORY_CLUSTER:
        found = [CATEGORY_CLUSTER[category]]
    return found[:limit]


def _words(text: str) -> set[str]:
    return {w[:6] for w in re.findall(r"[a-z]{4,}", text.lower()) if w not in STOPWORDS}


def ranked_causes(cluster_ids: list[str], text: str, hinted: dict[str, int], limit: int = 2) -> list[dict]:
    """Possible causes of the matched clusters, best first: +3 per possible-cause answer that points
    to it (`hinted`), +1 per word shared with the conversation; ties go to guide order (the guide
    lists the most common cause first). At most `limit`."""
    words = _words(text)
    scored = []
    order = 0  # guide order breaks ties
    for cid in cluster_ids:
        for cause in clusters()[cid]["possible_causes"]:
            score = 3 * hinted.get(cause["cause"], 0) + len(_words(cause["cause"] + " " + cause["description"]) & words)
            scored.append((-score, order, {**cause, "cluster": cid, "score": score}))
            order += 1
    return [c for _, _, c in sorted(scored, key=lambda s: (s[0], s[1]))][:limit]


def best_cause(cluster_ids: list[str], text: str, hinted: dict[str, int]) -> Optional[dict]:
    """The best-matching possible cause, or None when no matched cluster lists causes."""
    ranked = ranked_causes(cluster_ids, text, hinted, limit=1)
    return ranked[0] if ranked else None
