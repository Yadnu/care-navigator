"""Text embeddings: offline TF-IDF by default, Voyage when VOYAGE_API_KEY is set (D-008)."""
from __future__ import annotations

import os
from abc import ABC, abstractmethod

import numpy as np
import requests
from sklearn.feature_extraction.text import TfidfVectorizer

from navigator import config


class EmbeddingError(RuntimeError):
    """Embedding provider unreachable, failed, or used before it was fitted."""


def _normalize(vectors: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vectors, axis=-1, keepdims=True)
    return np.divide(vectors, norms, out=np.zeros_like(vectors), where=norms > 0)


class Embedder(ABC):
    name: str

    @abstractmethod
    def embed_documents(self, texts: list[str]) -> np.ndarray: ...

    @abstractmethod
    def embed_query(self, text: str) -> np.ndarray: ...


class LocalTfidfEmbedder(Embedder):
    """Character n-gram TF-IDF fitted on the documents; tolerant of word forms and typos."""

    name = "tfidf-char-3-5"

    def __init__(self):
        self._vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True)
        self._fitted = False

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        matrix = self._vectorizer.fit_transform([t.lower() for t in texts])
        self._fitted = True
        return _normalize(matrix.toarray())

    def embed_query(self, text: str) -> np.ndarray:
        if not self._fitted:
            raise EmbeddingError("embed_documents must run before embed_query")
        return _normalize(self._vectorizer.transform([text.lower()]).toarray()[0])


class VoyageEmbedder(Embedder):
    def __init__(self, api_key: str, model: str | None = None, session: requests.Session | None = None,
                 batch_size: int = config.VOYAGE_BATCH_SIZE):
        self.api_key = api_key
        self.model = model or config.voyage_model()
        self.session = session or requests.Session()
        self.batch_size = batch_size
        self.name = f"voyage:{self.model}"

    def _embed(self, texts: list[str], input_type: str) -> np.ndarray:
        rows: list[list[float]] = []
        for start in range(0, len(texts), self.batch_size):
            batch = texts[start:start + self.batch_size]
            try:
                resp = self.session.post(
                    config.VOYAGE_URL,
                    json={"input": batch, "model": self.model, "input_type": input_type},
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    timeout=config.VOYAGE_TIMEOUT_S,
                )
            except requests.RequestException as e:
                raise EmbeddingError(f"Voyage request failed: {e}") from e
            if resp.status_code != 200:
                raise EmbeddingError(f"Voyage returned HTTP {resp.status_code}")
            try:
                data = sorted(resp.json()["data"], key=lambda d: d["index"])
                rows.extend(d["embedding"] for d in data)
            except (ValueError, KeyError, TypeError) as e:
                raise EmbeddingError("unexpected Voyage response") from e
        return _normalize(np.asarray(rows, dtype=float))

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        return self._embed(texts, "document")

    def embed_query(self, text: str) -> np.ndarray:
        return self._embed([text], "query")[0]


def get_embedder() -> Embedder:
    if config.voyage_enabled():
        return VoyageEmbedder(api_key=os.environ["VOYAGE_API_KEY"].strip())
    return LocalTfidfEmbedder()
