"""One query embedding per turn (CW-614): a comparison or a recommendation used to embed
the question twice, once for its search and once more for the spec boxes."""

from __future__ import annotations

from typing import Any

import pytest

from carwise.config import load_settings
from carwise.llm.fake import FakeLLMClient
from carwise.pipeline import Pipeline
from carwise.registry import load_registry
from carwise.retrieval.embedder import FakeEmbedder, Vector
from carwise.retrieval.retriever import Retriever, SerializedRetriever
from carwise.schemas import Intent, RetrievedChunk
from tests.test_pipeline import InMemoryStore, _chunks, generation, understanding

REGISTRY = load_registry()


class CountingEmbedder(FakeEmbedder):
    def __init__(self) -> None:
        super().__init__()
        self.queries: list[str] = []

    def embed_query(self, text: str) -> Vector:
        self.queries.append(text)
        return super().embed_query(text)


def _retriever(settings: Any) -> tuple[Retriever, CountingEmbedder]:
    embedder = CountingEmbedder()
    return Retriever(InMemoryStore(_chunks()), embedder, settings.retrieval), embedder


def _settings(force_spec_box: bool = True) -> Any:
    settings = load_settings()
    retrieval = settings.retrieval.model_copy(
        update={"relevance_threshold": 0.0, "force_spec_box": force_spec_box}
    )
    return settings.model_copy(update={"retrieval": retrieval})


@pytest.mark.parametrize(
    ("intent", "cars"),
    [
        (Intent.COMPARE, ["mg_s6", "aion_ht"]),  # search_per_car, then spec_boxes
        (Intent.RECOMMEND, ["mg_s6"]),  # search_all, then spec_boxes
        (Intent.RECOMMEND, []),  # search_all only
        (Intent.FACT, ["mg_s6"]),  # search only
    ],
)
def test_each_turn_embeds_the_question_once(intent: Intent, cars: list[str]) -> None:
    settings = _settings()
    retriever, embedder = _retriever(settings)
    reply = understanding(intent=intent, cars=cars, question="מה הטווח והמחיר?")
    llm = FakeLLMClient([reply, generation()])
    pipeline = Pipeline(settings, REGISTRY, SerializedRetriever(retriever), llm)
    pipeline.ask("מה הטווח והמחיר?", [])
    assert embedder.queries == ["מה הטווח והמחיר?"]


def _key(hits: list[RetrievedChunk]) -> list[tuple[str, float]]:
    return [(hit.chunk.chunk_id, hit.score) for hit in hits]


@pytest.mark.parametrize("question", ["מה הטווח בפועל?", "כמה עולה?", "צריכת החשמל"])
def test_an_embedded_query_gives_the_same_results_as_its_text(question: str) -> None:
    retriever, _ = _retriever(_settings())
    query = retriever.embed(question)
    cars = ["mg_s6", "aion_ht"]
    assert _key(retriever.search(query, cars, 3)) == _key(retriever.search(question, cars, 3))
    assert _key(retriever.search_per_car(query, cars, 2)) == _key(
        retriever.search_per_car(question, cars, 2)
    )
    assert _key(retriever.search_all(query, 5, 1)) == _key(retriever.search_all(question, 5, 1))
    assert _key(retriever.spec_boxes(query, cars)) == _key(retriever.spec_boxes(question, cars))
