"""Phase 5: RAG over practitioners - filters first, then hybrid search, RRF and rerank (D-005, D-006)."""
from __future__ import annotations

import itertools
import json
import math
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest
import requests

from navigator import config
from navigator.data import is_open, load_practitioners, load_plans, load_zips
from navigator.jev_client import JevError, OfflineJev
from navigator.models import Match, SymptomReport
from navigator.retrieval.bm25 import BM25Index, tokenize
from navigator.retrieval.embeddings import (
    EmbeddingError,
    LocalTfidfEmbedder,
    VoyageEmbedder,
    get_embedder,
)
from navigator.retrieval.fusion import reciprocal_rank_fusion
from navigator.retrieval.retriever import Retriever, build_query, practitioner_text
from navigator.retrieval.vector_store import InMemoryVectorStore

EVAL = Path(__file__).resolve().parents[1] / "data" / "eval"
QUERIES = [json.loads(l) for l in (EVAL / "retrieval_queries.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
ZIP_BY = {z["zip"]: z for z in load_zips()}
TUE_DAY = datetime(2026, 11, 3, 14, 0)
retriever = Retriever()


# ------------------------------------------------------------------ independent filter check
def haversine_km(a_lat, a_lng, b_lat, b_lng):
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp, dl = p2 - p1, math.radians(b_lng - a_lng)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(h))


def violations(match: Match, care_type, plan, zip_code, when, age_group, max_km):
    p = match.practitioner
    found = []
    if p.type != care_type:
        found.append("type")
    if plan not in p.accepted_plans:
        found.append("plan")
    if not is_open(p.hours, when):
        found.append("closed")
    if care_type in ("PRIMARY_CARE", "SPECIALIST") and not p.accepting_new:
        found.append("not accepting")
    if (age_group == "child" and p.patient_ages == "adults") or (age_group == "adult" and p.patient_ages == "children"):
        found.append("age")
    if not p.virtual:
        z = ZIP_BY.get(zip_code)
        if z is None or haversine_km(z["lat"], z["lng"], p.lat, p.lng) > max_km:
            found.append("distance")
    return found


def run(q, **kw):
    return retriever.search_text(q["query"], care_type=q["care_type"], plan=q["plan"], zip_code=q["zip"],
                                 when=datetime.fromisoformat(q["request_time"]), age_group=q["age_group"],
                                 max_km=q["max_distance_km"], **kw)


# ------------------------------------------------------------------ fusion
def test_rrf_scores_use_k_60_by_default():
    fused = dict(reciprocal_rank_fusion([["a", "b"], ["b", "c"]]))
    assert fused["b"] == pytest.approx(1 / 62 + 1 / 61)
    assert fused["a"] == pytest.approx(1 / 61)
    assert fused["c"] == pytest.approx(1 / 62)


def test_rrf_orders_by_fused_score():
    fused = reciprocal_rank_fusion([["a", "b", "c"], ["c", "b", "a"], ["b"]])
    assert [i for i, _ in fused][0] == "b"


def test_rrf_custom_k_and_empty():
    assert reciprocal_rank_fusion([]) == []
    assert dict(reciprocal_rank_fusion([["x"]], k=0))["x"] == 1.0


# ------------------------------------------------------------------ BM25
def test_tokenize_lowercases_and_drops_stopwords():
    assert tokenize("Treats the Stomach-bugs and Vomiting!") == ["treats", "stomach", "bugs", "vomiting"]


def test_bm25_ranks_matching_doc_first_and_only_scores_given_ids():
    index = BM25Index({"a": "sports injuries sprains knee pain", "b": "stomach bugs vomiting food poisoning",
                       "c": "skin rashes acne eczema"})
    ranked = index.rank("vomiting after food", ids=["a", "b"])
    assert [i for i, _ in ranked] == ["b", "a"]


# ------------------------------------------------------------------ embeddings
DOCS = ["sports injuries sprains and knee pain", "stomach bugs vomiting and food poisoning", "skin rashes and acne"]


def test_tfidf_embeddings_are_normalized_and_semantic():
    emb = LocalTfidfEmbedder()
    docs = emb.embed_documents(DOCS)
    assert docs.shape[0] == 3
    assert np.allclose(np.linalg.norm(docs, axis=1), 1.0)
    q = emb.embed_query("vomiting food poisoning")
    assert int(np.argmax(docs @ q)) == 1


def test_tfidf_query_before_fit_raises():
    with pytest.raises(EmbeddingError):
        LocalTfidfEmbedder().embed_query("x")


def voyage_session(vectors=None, status=200, exc=None):
    session = MagicMock(spec=requests.Session)
    if exc:
        session.post.side_effect = exc
        return session

    def reply(url, json, headers, timeout):
        resp = MagicMock()
        resp.status_code = status
        n = len(json["input"])
        data = [{"object": "embedding", "embedding": (vectors or [[1.0, 0.0]] * n)[i], "index": i}
                for i in reversed(range(n))]  # out of order on purpose
        resp.json.return_value = {"object": "list", "data": data, "model": json["model"],
                                  "usage": {"total_tokens": 7}}
        return resp

    session.post.side_effect = reply
    return session


def test_voyage_request_shape_and_ordering():
    session = voyage_session(vectors=[[3.0, 4.0], [0.0, 2.0]])
    emb = VoyageEmbedder(api_key="vk", session=session)
    out = emb.embed_documents(["a", "b"])
    assert np.allclose(out, [[0.6, 0.8], [0.0, 1.0]])  # reordered by index and normalized
    args, kwargs = session.post.call_args
    assert args[0] == "https://api.voyageai.com/v1/embeddings"
    assert kwargs["headers"]["Authorization"] == "Bearer vk"
    assert kwargs["json"]["model"] == config.voyage_model()
    assert kwargs["json"]["input_type"] == "document"
    emb.embed_query("q")
    assert session.post.call_args.kwargs["json"]["input_type"] == "query"


def test_voyage_batches_large_inputs():
    session = voyage_session()
    VoyageEmbedder(api_key="vk", session=session, batch_size=2).embed_documents(["a", "b", "c"])
    assert session.post.call_count == 2


@pytest.mark.parametrize("kwargs", [dict(status=429), dict(exc=requests.Timeout("slow"))])
def test_voyage_errors_raise_embedding_error(kwargs):
    with pytest.raises(EmbeddingError):
        VoyageEmbedder(api_key="vk", session=voyage_session(**kwargs)).embed_documents(["a"])


def test_get_embedder(monkeypatch):
    assert isinstance(get_embedder(), LocalTfidfEmbedder)
    monkeypatch.setenv("VOYAGE_API_KEY", "vk")
    assert isinstance(get_embedder(), VoyageEmbedder)


# ------------------------------------------------------------------ vector store
def test_vector_store_cosine_search_with_filter_and_k():
    store = InMemoryVectorStore()
    store.add(["a", "b", "c"], np.array([[1.0, 0.0], [0.8, 0.6], [0.0, 1.0]]),
              [{"type": "UC"}, {"type": "PC"}, {"type": "UC"}])
    assert [i for i, _ in store.search(np.array([1.0, 0.0]), k=3)] == ["a", "b", "c"]
    assert [i for i, _ in store.search(np.array([1.0, 0.0]), k=1)] == ["a"]
    assert [i for i, _ in store.search(np.array([1.0, 0.0]), k=3, where=lambda m: m["type"] == "UC")] == ["a", "c"]


def test_vector_store_validates_and_handles_empty():
    store = InMemoryVectorStore()
    assert store.search(np.array([1.0, 0.0]), k=3) == []
    with pytest.raises(ValueError):
        store.add(["a"], np.array([[1.0, 0.0], [0.0, 1.0]]), [{}])


# ------------------------------------------------------------------ retriever: hard filters
@pytest.mark.parametrize("q", QUERIES, ids=[q["id"] for q in QUERIES])
def test_eval_query_results_pass_every_filter(q):
    result = run(q)
    for m in result.matches:
        assert violations(m, q["care_type"], q["plan"], q["zip"], datetime.fromisoformat(q["request_time"]),
                          q["age_group"], q["max_distance_km"]) == [], (q["id"], m.practitioner.id)


def test_zero_filter_violations_across_the_whole_grid():
    times = [TUE_DAY, datetime(2026, 11, 3, 22, 30), datetime(2026, 11, 4, 0, 15), datetime(2026, 11, 7, 10, 0)]
    types = ["ER", "URGENT_CARE", "PRIMARY_CARE", "TELEHEALTH", "SPECIALIST"]
    count = 0
    for care_type, plan, zip_code, when, age, km in itertools.product(
            types, [p["id"] for p in load_plans()], ZIP_BY, times, ["adult", "child"], [3, 10]):
        for m in retriever.search_text("fever cough", care_type=care_type, plan=plan, zip_code=zip_code,
                                       when=when, age_group=age, max_km=km).matches:
            count += 1
            assert violations(m, care_type, plan, zip_code, when, age, km) == [], (care_type, plan, zip_code, when, age, km, m.practitioner.id)
    assert count > 0


# ------------------------------------------------------------------ retriever: quality
def test_recall_at_3_meets_bar():
    scored = [q for q in QUERIES if q["expected_ids"]]
    recalls = []
    for q in scored:
        top = {m.practitioner.id for m in run(q).matches}
        recalls.append(len(top & set(q["expected_ids"])) / len(q["expected_ids"]))
    assert sum(recalls) / len(recalls) >= 0.9, recalls


def test_coverage_gap_returns_empty_cleanly():
    q = next(q for q in QUERIES if q["id"] == "RQ-019")
    result = run(q)
    assert result.matches == [] and result.candidates == 0


def test_results_have_matched_text_distance_and_at_most_three():
    for q in QUERIES:
        matches = run(q).matches
        assert len(matches) <= 3
        for m in matches:
            assert m.matched_text
            assert (m.distance_km is None) == m.practitioner.virtual


def test_self_care_has_no_practitioners():
    result = retriever.search_text("sneezing", care_type="SELF_CARE", plan="PLAN_GOLD_PPO", zip_code="00101",
                                   when=TUE_DAY)
    assert result.matches == []


def test_unknown_zip_keeps_only_virtual_options():
    result = retriever.search_text("cough", care_type="URGENT_CARE", plan="PLAN_GOLD_PPO", zip_code="99999",
                                   when=TUE_DAY)
    assert result.matches == []
    virtual = retriever.search_text("cough", care_type="TELEHEALTH", plan="PLAN_GOLD_PPO", zip_code="99999",
                                    when=TUE_DAY)
    assert virtual.matches and all(m.practitioner.virtual for m in virtual.matches)


def test_results_are_deterministic():
    q = QUERIES[0]
    assert [m.practitioner.id for m in run(q).matches] == [m.practitioner.id for m in run(q).matches]


# ------------------------------------------------------------------ retriever: query building and rerank
def test_query_is_built_from_parsed_fields_not_raw_text():
    report = SymptomReport(main_symptom="vomiting, cramps", body_area="stomach", duration_hours=5, severity=5,
                           confidence="high")
    query = build_query(report)
    assert "vomiting" in query and "stomach" in query
    assert "ignore" not in query


def test_search_uses_the_report():
    report = SymptomReport(main_symptom="vomiting, cramps", body_area="stomach", duration_hours=5, severity=5,
                           confidence="high")
    result = retriever.search(report, level="URGENT_CARE", plan="PLAN_SILVER_HMO", zip_code="00101", when=TUE_DAY)
    assert result.matches[0].practitioner.id == "UC-002"


def test_matched_text_never_claims_an_unrelated_condition():
    from navigator.retrieval.retriever import matched_text
    p = next(p for p in load_practitioners() if p.id == "UC-002")  # GI-focused urgent care
    assert matched_text(p, "vomiting") != "" and "vomiting" in matched_text(p, "vomiting").lower()
    fallback = matched_text(p, "sore throat fever")
    assert fallback == ", ".join(p.specialties)  # no overlap: say what the place does, not "food poisoning"


def test_practitioner_text_includes_bio_specialties_conditions_and_languages():
    p = next(p for p in load_practitioners() if p.id == "UC-005")
    text = practitioner_text(p)
    assert p.bio in text and "urinary tract infections" in text and "Spanish" in text


def test_rerank_changes_order():
    class Reverse(OfflineJev):
        def rerank(self, query, docs):
            return [float(i) for i in range(len(docs))]  # last fused doc wins

    q = next(q for q in QUERIES if q["id"] == "RQ-004")
    default = [m.practitioner.id for m in run(q).matches]
    reversed_ = [m.practitioner.id for m in Retriever(jev=Reverse()).search_text(
        q["query"], care_type=q["care_type"], plan=q["plan"], zip_code=q["zip"],
        when=datetime.fromisoformat(q["request_time"]), age_group=q["age_group"],
        max_km=q["max_distance_km"]).matches]
    assert default != reversed_


def test_rerank_failure_falls_back_to_fused_order():
    class Down(OfflineJev):
        def rerank(self, query, docs):
            raise JevError("down")

    q = QUERIES[0]
    result = Retriever(jev=Down()).search_text(q["query"], care_type=q["care_type"], plan=q["plan"],
                                               zip_code=q["zip"], when=datetime.fromisoformat(q["request_time"]))
    assert result.matches and result.reranked is False
    assert run(q).reranked is True
