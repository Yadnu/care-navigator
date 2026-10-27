"""In-memory vector store with cosine similarity and metadata filtering (D-029).

44 records need no index; ChromaDB (or similar) is the production path.
"""
from __future__ import annotations

from typing import Any, Callable, Optional

import numpy as np

Where = Callable[[dict[str, Any]], bool]


class InMemoryVectorStore:
    def __init__(self):
        self._ids: list[str] = []
        self._vectors = np.zeros((0, 0))
        self._metadata: list[dict[str, Any]] = []

    def add(self, ids: list[str], vectors: np.ndarray, metadatas: list[dict[str, Any]]) -> None:
        vectors = np.asarray(vectors, dtype=float)
        if not (len(ids) == vectors.shape[0] == len(metadatas)):
            raise ValueError("ids, vectors and metadatas must have the same length")
        self._vectors = vectors if not self._ids else np.vstack([self._vectors, vectors])
        self._ids.extend(ids)
        self._metadata.extend(metadatas)

    def search(self, vector: np.ndarray, k: int, where: Optional[Where] = None) -> list[tuple[str, float]]:
        """Top-k (id, cosine similarity) among records passing `where`; ties keep insertion order."""
        if not self._ids:
            return []
        norms = np.linalg.norm(self._vectors, axis=1) * (np.linalg.norm(vector) or 1.0)
        sims = np.divide(self._vectors @ vector, norms, out=np.zeros(len(self._ids)), where=norms > 0)
        hits = [(self._ids[i], float(sims[i])) for i in range(len(self._ids))
                if where is None or where(self._metadata[i])]
        return sorted(hits, key=lambda item: -item[1])[:k]
