"""Pass-3 embedding fallback for concept resolution.

Design note (defended in the README):

The default embedder is a **deterministic local character n-gram TF-IDF vector**,
not a neural model. That is a deliberate trade-off for a one-day assessment:

* it needs no model download, no API key, and no network, so `make dev` and the
  test suite work anywhere;
* it is fully reproducible, which means the embedding pass can be *unit tested*
  with exact expected scores rather than being a black box;
* it still exercises the real architecture - a vector index, cosine similarity,
  and an acceptance threshold.

`EmbeddingBackend` is a Protocol, so swapping in sentence-transformers or a
provider embeddings API is a one-class change. What must never change is the
invariant that **embeddings only canonicalize language; they never decide
safety.** A concept resolved by embedding still has to survive the deterministic
graph traversal before it can affect a workout.
"""

from __future__ import annotations

import math
from collections import Counter
from typing import Protocol, runtime_checkable


@runtime_checkable
class EmbeddingBackend(Protocol):
    def embed(self, text: str) -> dict[str, float]:
        """Return a sparse unit-normalized vector."""
        ...


class CharNgramEmbedder:
    """Deterministic sparse embedder over character n-grams plus word tokens.

    Character n-grams give useful similarity for morphological variants
    ("lumbar" / "lumbar region"), which is exactly the failure mode the
    embedding pass exists to catch after exact and fuzzy matching miss.
    """

    def __init__(self, ngram_sizes: tuple[int, ...] = (3, 4)) -> None:
        self._sizes = ngram_sizes

    def embed(self, text: str) -> dict[str, float]:
        if not text:
            return {}
        padded = f" {text.strip().lower()} "
        counts: Counter[str] = Counter()

        for size in self._sizes:
            for i in range(len(padded) - size + 1):
                counts[f"{size}:{padded[i : i + size]}"] += 1

        # Word tokens carry more signal than any single n-gram, so weight them up.
        for token in text.lower().split():
            counts[f"w:{token}"] += 3

        norm = math.sqrt(sum(v * v for v in counts.values()))
        if norm == 0:
            return {}
        return {k: v / norm for k, v in counts.items()}


def cosine_similarity(a: dict[str, float], b: dict[str, float]) -> float:
    if not a or not b:
        return 0.0
    # Iterate the smaller vector for speed.
    if len(a) > len(b):
        a, b = b, a
    return max(0.0, min(1.0, sum(value * b.get(key, 0.0) for key, value in a.items())))


class EmbeddingIndex:
    """A tiny vector index over canonical concept labels and aliases."""

    def __init__(self, backend: EmbeddingBackend | None = None) -> None:
        self._backend = backend or CharNgramEmbedder()
        self._entries: list[tuple[str, str, dict[str, float]]] = []

    def add(self, concept_id: str, text: str) -> None:
        vector = self._backend.embed(text)
        if vector:
            self._entries.append((concept_id, text, vector))

    def search(self, query: str, top_k: int = 3) -> list[tuple[str, str, float]]:
        query_vector = self._backend.embed(query)
        if not query_vector:
            return []
        scored = [
            (concept_id, text, cosine_similarity(query_vector, vector))
            for concept_id, text, vector in self._entries
        ]
        scored.sort(key=lambda row: row[2], reverse=True)
        return scored[:top_k]

    def __len__(self) -> int:
        return len(self._entries)
