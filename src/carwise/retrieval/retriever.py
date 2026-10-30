"""Three retrieval modes, one per question shape (CLAUDE.md section 3.2).

Why three and not one top-k: a comparison retrieved with a single top-k lets
the car with the wordier review take every slot, and a ranking question
("which is the fastest") needs every car represented. Plain code, no LLM.
"""

from __future__ import annotations

from collections import Counter

from carwise.config import RetrievalConfig
from carwise.retrieval.embedder import Embedder
from carwise.retrieval.store import ChunkStore
from carwise.schemas import RetrievedChunk


class Retriever:
    def __init__(self, store: ChunkStore, embedder: Embedder, config: RetrievalConfig) -> None:
        self._store = store
        self._embedder = embedder
        self._config = config

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
