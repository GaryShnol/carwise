"""Three retrieval modes, one per question shape (CLAUDE.md section 3.2).

Why three and not one top-k: a comparison retrieved with a single top-k lets
the car with the wordier review take every slot, and a ranking question
("which is the fastest") needs every car represented. Plain code, no LLM.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Protocol

from carwise.config import RetrievalConfig, Settings
from carwise.retrieval.embedder import Embedder, Vector, make_embedder
from carwise.retrieval.store import ChunkStore
from carwise.schemas import Chunk, RetrievedChunk


class CandidateSource(Protocol):
    """What the retriever needs from a store: every candidate with its cosine score."""

    def candidates(
        self, vector: Vector, car_ids: list[str] | None
    ) -> list[tuple[Chunk, float]]: ...


class ChunkRetriever(Protocol):
    """What the pipeline needs; the Retriever below is the only production implementation."""

    def search(
        self, query: str, car_ids: list[str] | None = None, top_k: int | None = None
    ) -> list[RetrievedChunk]: ...

    def search_per_car(
        self, query: str, car_ids: list[str], top_k_per_car: int | None = None
    ) -> list[RetrievedChunk]: ...

    def search_all(
        self, query: str, top_k: int | None = None, per_car_cap: int | None = None
    ) -> list[RetrievedChunk]: ...


class Retriever:
    def __init__(self, store: CandidateSource, embedder: Embedder, config: RetrievalConfig) -> None:
        self._store = store
        self._embedder = embedder
        self._config = config

    def warm_up(self) -> None:
        """Load the embedding model now (about a minute on a cold CPU start, not mid-chat)."""
        self._embedder.warm_up()

    def _ranked(self, query: str, car_ids: list[str] | None) -> list[RetrievedChunk]:
        if car_ids is not None and not car_ids:
            raise ValueError("car_ids must be None (all cars) or name at least one car")
        vector = self._embedder.embed_query(query)
        hits = [
            RetrievedChunk(chunk=chunk, score=score)
            for chunk, score in self._store.candidates(vector, car_ids)
        ]
        # Score first, chunk id breaks ties: same index and query, same order, always.
        return sorted(hits, key=lambda hit: (-hit.score, hit.chunk.chunk_id))

    def search(
        self, query: str, car_ids: list[str] | None = None, top_k: int | None = None
    ) -> list[RetrievedChunk]:
        """Best chunks overall, or among the given cars (single-car fact questions)."""
        return self._ranked(query, car_ids)[: _default(top_k, self._config.top_k)]

    def search_per_car(
        self, query: str, car_ids: list[str], top_k_per_car: int | None = None
    ) -> list[RetrievedChunk]:
        """The best chunks of each car separately, so no car crowds out another."""
        cap = _default(top_k_per_car, self._config.per_car_cap)
        return _capped(self._ranked(query, car_ids), cap, limit=None)

    def search_all(
        self, query: str, top_k: int | None = None, per_car_cap: int | None = None
    ) -> list[RetrievedChunk]:
        """Across all cars with a cap per car, for ranking and recommendation questions."""
        cap = _default(per_car_cap, self._config.per_car_cap)
        return _capped(self._ranked(query, None), cap, _default(top_k, self._config.top_k))


def open_retriever(settings: Settings) -> Retriever:
    """Retriever over the index in paths.index_dir, using the configured embedder.

    Raises IndexNotReadyError when the index is missing or was built with
    other embedding settings, because mixing models silently ruins scores.
    """
    embedder = make_embedder(settings.embeddings)
    store = ChunkStore(Path(settings.paths.index_dir), embedder)
    return Retriever(store, embedder, settings.retrieval)


def _default(value: int | None, fallback: int) -> int:
    chosen = fallback if value is None else value
    if chosen < 1:
        raise ValueError("result limits must be at least 1")
    return chosen


def _capped(ranked: list[RetrievedChunk], cap: int, limit: int | None) -> list[RetrievedChunk]:
    """Keep ranked order, at most `cap` chunks per car, at most `limit` in total."""
    taken: Counter[str] = Counter()
    kept: list[RetrievedChunk] = []
    for hit in ranked:
        if limit is not None and len(kept) == limit:
            break
        if taken[hit.chunk.car] < cap:
            taken[hit.chunk.car] += 1
            kept.append(hit)
    return kept
