"""Practitioner retrieval: hard filters -> hybrid search (embeddings + BM25) -> RRF -> Jev rerank (D-005, D-006).

The query is built from the parsed SymptomReport, never the raw text. Every returned
practitioner passes every hard filter; an empty result is a valid answer.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Iterable, Optional

from pydantic import BaseModel

from navigator import config
from navigator.data import haversine_km, is_open, load_practitioners, load_zips
from navigator.jev_client import JevClient, JevError, OfflineJev
from navigator.models import Match, Practitioner, SymptomReport
from navigator.retrieval.bm25 import BM25Index, analyze
from navigator.retrieval.embeddings import Embedder, LocalTfidfEmbedder
from navigator.retrieval.fusion import reciprocal_rank_fusion
from navigator.retrieval.vector_store import InMemoryVectorStore

NEEDS_NEW_PATIENTS = {"PRIMARY_CARE", "SPECIALIST"}


class RetrievalResult(BaseModel):
    matches: list[Match]
    candidates: int   # practitioners left after the hard filters
    reranked: bool    # False when Jev rerank failed and fused order was used


def practitioner_text(p: Practitioner) -> str:
    return (f"{p.facility_name}. Specialties: {', '.join(p.specialties)}. "
            f"Treats: {', '.join(p.conditions_treated)}. {p.bio} Languages: {', '.join(p.languages)}.")


def _segments(p: Practitioner) -> list[str]:
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", p.bio) if s.strip()]
    return [*p.conditions_treated, *p.specialties, *sentences]


def matched_text(p: Practitioner, query: str) -> str:
    """The record segment sharing the most terms with the query (first condition if none)."""
    terms = set(analyze(query))
    best = max(_segments(p), key=lambda s: len(terms & set(analyze(s))))
    return best if terms & set(analyze(best)) else p.conditions_treated[0]


def build_query(report: SymptomReport) -> str:
    return " ".join(x.replace(",", " ") for x in (report.main_symptom, report.body_area) if x)


class Retriever:
    def __init__(self, practitioners: Optional[Iterable[Practitioner]] = None,
                 embedder: Optional[Embedder] = None, jev: Optional[JevClient] = None):
        self.practitioners = tuple(load_practitioners() if practitioners is None else practitioners)
        self.by_id = {p.id: p for p in self.practitioners}
        self.texts = {p.id: practitioner_text(p) for p in self.practitioners}
        self.embedder = embedder or LocalTfidfEmbedder()
        self.jev = jev or OfflineJev()
        self.zips = {z["zip"]: z for z in load_zips()}

        ids = list(self.texts)
        self.store = InMemoryVectorStore()
        self.store.add(ids, self.embedder.embed_documents([self.texts[i] for i in ids]), [{"id": i} for i in ids])
        self.bm25 = BM25Index(self.texts)

    def _candidates(self, care_type: str, plan: str, zip_code: str, when: datetime, age_group: str,
                    max_km: float) -> dict[str, Optional[float]]:
        """Hard filters (D-006). Returns id -> distance (None if virtual)."""
        zip_rec = self.zips.get(zip_code)
        excluded_ages = "adults" if age_group == "child" else "children"
        out: dict[str, Optional[float]] = {}
        for p in self.practitioners:
            if p.type != care_type or plan not in p.accepted_plans or not is_open(p.hours, when):
                continue
            if care_type in NEEDS_NEW_PATIENTS and not p.accepting_new:
                continue
            if p.patient_ages == excluded_ages:
                continue
            if p.virtual:
                out[p.id] = None
                continue
            if zip_rec is None:
                continue  # can't check distance for an unknown zip, so in-person options are out
            distance = haversine_km(zip_rec["lat"], zip_rec["lng"], p.lat, p.lng)
            if distance <= max_km:
                out[p.id] = round(distance, 2)
        return out

    def search_text(self, query: str, care_type: str, plan: str, zip_code: str, when: datetime,
                    age_group: str = "adult", max_km: float = config.MAX_DISTANCE_KM,
                    k: int = config.TOP_K) -> RetrievalResult:
        candidates = self._candidates(care_type, plan, zip_code, when, age_group, max_km)
        if not candidates:
            return RetrievalResult(matches=[], candidates=0, reranked=False)

        semantic = [i for i, _ in self.store.search(self.embedder.embed_query(query), k=len(candidates),
                                                     where=lambda m: m["id"] in candidates)]
        lexical = [i for i, _ in self.bm25.rank(query, ids=list(candidates))]
        fused = reciprocal_rank_fusion([semantic, lexical])[:config.RERANK_TOP_N]

        try:
            rerank = self.jev.rerank(query, [self.texts[i] for i, _ in fused])
            reranked = True
        except JevError:
            rerank, reranked = [score for _, score in fused], False

        order = sorted(range(len(fused)),
                       key=lambda n: (-rerank[n], candidates[fused[n][0]] or 0.0, -fused[n][1]))
        matches = [
            Match(practitioner=self.by_id[fused[n][0]], distance_km=candidates[fused[n][0]],
                  score=round(float(rerank[n]), 4), matched_text=matched_text(self.by_id[fused[n][0]], query))
            for n in order[:k]
        ]
        return RetrievalResult(matches=matches, candidates=len(candidates), reranked=reranked)

    def search(self, report: SymptomReport, level: str, plan: str, zip_code: str, when: datetime,
               age_group: str = "adult", max_km: float = config.MAX_DISTANCE_KM,
               k: int = config.TOP_K) -> RetrievalResult:
        return self.search_text(build_query(report), level, plan, zip_code, when, age_group, max_km, k)
