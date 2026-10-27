"""Reciprocal rank fusion (D-006)."""
from __future__ import annotations

from navigator import config


def reciprocal_rank_fusion(rankings: list[list[str]], k: int = config.RRF_K) -> list[tuple[str, float]]:
    """Merge ranked id lists: score(id) = sum of 1 / (k + rank), rank starting at 1.

    Ties keep first-seen order, so results are deterministic.
    """
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, doc_id in enumerate(ranking, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda item: -item[1])
