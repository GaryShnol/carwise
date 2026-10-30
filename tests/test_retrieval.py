from datetime import date
from pathlib import Path

import pytest

from carwise.config import (
    ChunkingConfig,
    EmbeddingsConfig,
    LexicalConfig,
    RetrievalConfig,
    load_settings,
)
from carwise.retrieval.embedder import FakeEmbedder, SentenceTransformerEmbedder, make_embedder
from carwise.retrieval.retriever import Retriever
from carwise.retrieval.store import (
    ChunkStore,
    IndexNotReadyError,
    build_index,
    fingerprint,
    stored_fingerprint,
)
from carwise.schemas import Chunk

# Synthetic chunks only; the repository is public.
LIMITS = ChunkingConfig(min_chars=10, max_chars=500, embed_section_chars=60, spec_header=False)
LEXICAL_OFF = LexicalConfig(enabled=False, rrf_k=60, bm25_k1=1.5, bm25_b=0.75)
CONFIG = RetrievalConfig(
    top_k=3,
    per_car_cap=2,
    cross_car_top_k=6,
    cross_car_per_car_cap=2,
    relevance_threshold=0.0,
    lexical=LEXICAL_OFF,
    force_spec_box=False,
)
TOPICS = ["מנוע טורבו כוח סוס", "טווח סוללה טעינה", "מחיר אבזור גרסה", "נוחות מושבים שקט"]


def _chunk(car: str, index: int, text: str, published: date | None = date(2026, 1, 1)) -> Chunk:
    name = f"רכב {car}"
    return Chunk(
        chunk_id=f"{car}:{index:03d}",
        car=car,
        car_name=name,
        section=f"פרק {index}",
        source_url=f"https://example.test/{car}/",
        published=published,
        text=text,
        embed_text=f"{name} — פרק {index}\n{text}",
    )


def _corpus() -> list[Chunk]:
    chunks = [
        _chunk(car, i, f"{topic} {car}")
        for car in ("aaa", "bbb", "ccc")
        for i, topic in enumerate(TOPICS)
    ]
    return [*chunks, _chunk("ddd", 0, "טקסט ללא תאריך", published=None)]


@pytest.fixture
def retriever(tmp_path: Path) -> Retriever:
    embedder = FakeEmbedder()
    build_index(_corpus(), embedder, LIMITS, tmp_path)
    return Retriever(ChunkStore(tmp_path), embedder, CONFIG)


def test_car_filter_returns_only_that_car(retriever: Retriever) -> None:
    hits = retriever.search("מנוע טורבו", car_ids=["bbb"], top_k=10)
    assert len(hits) == len(TOPICS)
    assert {hit.chunk.car for hit in hits} == {"bbb"}
    assert hits[0].chunk.chunk_id == "bbb:000"  # the engine chunk ranks first


def test_filter_by_several_cars(retriever: Retriever) -> None:
    hits = retriever.search("טווח", car_ids=["aaa", "ccc"], top_k=20)
    assert {hit.chunk.car for hit in hits} == {"aaa", "ccc"}


def test_unknown_car_returns_nothing(retriever: Retriever) -> None:
    assert retriever.search("מנוע", car_ids=["zzz"]) == []


def test_empty_car_list_is_an_error(retriever: Retriever) -> None:
    with pytest.raises(ValueError, match="car_ids"):
        retriever.search("מנוע", car_ids=[])


def test_top_k_respected_and_defaults_from_config(retriever: Retriever) -> None:
    assert len(retriever.search("מנוע", top_k=5)) == 5
    assert len(retriever.search("מנוע")) == CONFIG.top_k


def test_scores_in_range_and_sorted(retriever: Retriever) -> None:
    hits = retriever.search("מחיר אבזור", top_k=20)
    scores = [hit.score for hit in hits]
    assert all(-1.0 <= score <= 1.0 for score in scores)
    assert scores == sorted(scores, reverse=True)


def test_ties_break_by_chunk_id_and_order_is_stable(retriever: Retriever) -> None:
    # The three cars share each topic sentence word for word except the car id,
    # so a query without car words scores them alike; ids decide.
    first = retriever.search("נוחות מושבים שקט", top_k=20)
    second = retriever.search("נוחות מושבים שקט", top_k=20)
    assert first == second
    assert first == sorted(first, key=lambda hit: (-hit.score, hit.chunk.chunk_id))


def test_exact_ties_are_ordered_by_chunk_id(tmp_path: Path) -> None:
    embedder = FakeEmbedder()
    twins = [_chunk("bbb", 1, "אותו טקסט"), _chunk("aaa", 1, "אותו טקסט")]
    twins = [c.model_copy(update={"embed_text": "אותו טקסט"}) for c in twins]
    build_index(twins, embedder, LIMITS, tmp_path)
    hits = Retriever(ChunkStore(tmp_path), embedder, CONFIG).search("אותו טקסט", top_k=2)
    assert hits[0].score == hits[1].score
    assert [hit.chunk.chunk_id for hit in hits] == ["aaa:001", "bbb:001"]


def test_search_per_car_covers_every_requested_car(retriever: Retriever) -> None:
    hits = retriever.search_per_car("מנוע", ["aaa", "ccc"], top_k_per_car=2)
    per_car = {car: sum(1 for hit in hits if hit.chunk.car == car) for car in ("aaa", "ccc")}
    assert per_car == {"aaa": 2, "ccc": 2}
    assert len(hits) == 4


def test_search_all_respects_cap_and_top_k(retriever: Retriever) -> None:
    hits = retriever.search_all("מנוע טורבו כוח סוס", top_k=5, per_car_cap=1)
    cars = [hit.chunk.car for hit in hits]
    assert len(cars) == len(set(cars)) == 4  # only four cars exist, one each
    capped = retriever.search_all("מנוע", top_k=5, per_car_cap=2)
    assert len(capped) == 5
    assert max(sum(1 for h in capped if h.chunk.car == c) for c in {"aaa", "bbb", "ccc"}) <= 2


def test_chunk_round_trips_through_the_store(retriever: Retriever) -> None:
    by_id = {hit.chunk.chunk_id: hit.chunk for hit in retriever.search("x", top_k=50)}
    assert by_id == {chunk.chunk_id: chunk for chunk in _corpus()}  # incl. a missing date


def test_store_lists_every_chunk_in_id_order(retriever: Retriever, tmp_path: Path) -> None:
    chunks = ChunkStore(tmp_path).chunks()
    assert chunks == sorted(_corpus(), key=lambda chunk: chunk.chunk_id)


def test_build_is_skipped_when_nothing_changed(tmp_path: Path) -> None:
    embedder, chunks = FakeEmbedder(), _corpus()
    assert build_index(chunks, embedder, LIMITS, tmp_path).rebuilt
    again = build_index(chunks, embedder, LIMITS, tmp_path)
    assert not again.rebuilt and again.chunks == len(chunks)


@pytest.mark.parametrize("change", ["limits", "text", "ids", "embedder"])
def test_build_reruns_when_the_fingerprint_changes(tmp_path: Path, change: str) -> None:
    embedder, chunks, limits = FakeEmbedder(), _corpus(), LIMITS
    build_index(chunks, embedder, limits, tmp_path)
    if change == "limits":
        limits = ChunkingConfig(
            min_chars=20, max_chars=500, embed_section_chars=60, spec_header=False
        )
    elif change == "text":
        chunks = [chunks[0].model_copy(update={"embed_text": "שונה"}), *chunks[1:]]
    elif change == "ids":
        chunks = chunks[:-1]
    else:
        embedder = FakeEmbedder(dimension=128)
    assert build_index(chunks, embedder, limits, tmp_path).rebuilt
    assert stored_fingerprint(tmp_path) == fingerprint(chunks, embedder, limits)
    assert ChunkStore(tmp_path).count() == len(chunks)


def test_store_refuses_a_missing_or_stale_index(tmp_path: Path) -> None:
    with pytest.raises(IndexNotReadyError, match="ingest"):
        ChunkStore(tmp_path / "nothing")
    build_index(_corpus(), FakeEmbedder(), LIMITS, tmp_path)
    ChunkStore(tmp_path, FakeEmbedder())  # same embedder: fine
    with pytest.raises(IndexNotReadyError, match="other embedding settings"):
        ChunkStore(tmp_path, FakeEmbedder(dimension=128))


def test_fake_embedder_prefers_shared_words() -> None:
    embedder = FakeEmbedder()
    query = embedder.embed_query("טווח סוללה")
    near, far = embedder.embed_documents(["טווח סוללה ארוך", "מושבים נוחים"])

    def dot(a: list[float], b: list[float]) -> float:
        return sum(x * y for x, y in zip(a, b, strict=True))

    assert dot(query, near) > dot(query, far)
    assert embedder.embed_query("") == embedder.embed_query("")  # no zero vector, no NaN


def test_provider_comes_from_config() -> None:
    config = load_settings().embeddings
    assert isinstance(make_embedder(config), SentenceTransformerEmbedder)
    fake = EmbeddingsConfig(**{**config.model_dump(), "provider": "fake"})
    assert isinstance(make_embedder(fake), FakeEmbedder)


def test_real_embedder_identity_names_pinned_revision_and_prefixes() -> None:
    config = load_settings().embeddings
    identity = SentenceTransformerEmbedder(config).identity
    assert identity["revision"] and len(str(identity["revision"])) == 40  # a commit hash
    assert identity["query_prefix"] == "query: " and identity["passage_prefix"] == "passage: "
