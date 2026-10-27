"""BM25 keyword search over practitioner text (bio + specialties + conditions + languages)."""
from __future__ import annotations

import re

from rank_bm25 import BM25Okapi

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has", "have", "i", "in", "is", "it",
    "my", "of", "on", "or", "since", "that", "the", "their", "to", "with", "who", "we", "our",
}
SUFFIXES = ("ing", "ed", "es", "s")


def tokenize(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in STOPWORDS]


def stem(token: str) -> str:
    """Light suffix stripping so "sprains"/"sprain" and "vomiting"/"vomit" meet."""
    for suffix in SUFFIXES:
        if token.endswith(suffix) and len(token) - len(suffix) >= 4:
            return token[: -len(suffix)]
    return token


def analyze(text: str) -> list[str]:
    return [stem(t) for t in tokenize(text)]


class BM25Index:
    def __init__(self, docs: dict[str, str]):
        self.ids = list(docs)
        self._bm25 = BM25Okapi([analyze(docs[i]) or ["_"] for i in self.ids])

    def rank(self, query: str, ids: list[str] | None = None) -> list[tuple[str, float]]:
        """Score the given ids (all if None), best first; ties keep index order."""
        scores = dict(zip(self.ids, self._bm25.get_scores(analyze(query))))
        wanted = self.ids if ids is None else [i for i in self.ids if i in set(ids)]
        return sorted(((i, float(scores[i])) for i in wanted), key=lambda item: -item[1])
