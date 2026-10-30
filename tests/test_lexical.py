"""BM25 and reciprocal rank fusion (CW-305). Synthetic chunks only; the repository is public."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from carwise.config import ChunkingConfig, LexicalConfig, load_settings
from carwise.retrieval.embedder import FakeEmbedder
from carwise.retrieval.lexical import LexicalIndex, fuse, terms
from carwise.retrieval.retriever import Retriever, open_retriever
from carwise.retrieval.store import ChunkStore, build_index
from carwise.schemas import Chunk, RetrievedChunk

LEXICAL = LexicalConfig(enabled=True, rrf_k=60, bm25_k1=1.5, bm25_b=0.75)


def _chunk(chunk_id: str, text: str) -> Chunk:
    car = chunk_id.split(":")[0]
    return Chunk(
        chunk_id=chunk_id,
        car=car,
        car_name=car,
        section="פרק",
        source_url=f"https://example.test/{car}/",
        published=date(2026, 1, 1),
        text=text,
        embed_text=text,
    )


CHUNKS = [
    _chunk("a:000", "המחיר 199,900 שקלים ותאוצה 0 ל-100 ב-7.7 שניות"),
    _chunk("a:001", "נוחות הנסיעה טובה והמושבים רכים"),
    _chunk("b:000", "תא המטען גדול והבידוד שקט"),
]


def test_terms_keep_the_word_and_add_prefix_stripped_forms() -> None:
    found = terms("במחיר ובתאוצה ל-100")
    assert "במחיר" in found and "מחיר" in found
    assert "ובתאוצה" in found and "בתאוצה" in found and "תאוצה" in found
    assert "100" in found
    assert "ל" not in found  # a lone prefix letter is not a word


def test_terms_never_strip_below_three_letters_or_touch_latin() -> None:
    assert terms("מה") == ["מה"]
    assert terms("GV80 Bose") == ["gv80", "bose"]


def test_bm25_prefers_the_chunk_that_shares_rare_words() -> None:
    index = LexicalIndex(CHUNKS, LEXICAL)
    assert index.score("מה המחיר?", "a:000") > 0
    assert index.score("מה המחיר?", "b:000") == 0
    assert index.score("anything", "missing:000") == 0


def _hits(order: list[str], score: float = 0.8) -> list[RetrievedChunk]:
    by_id = {c.chunk_id: c for c in CHUNKS}
    return [RetrievedChunk(chunk=by_id[cid], score=score - i * 0.01) for i, cid in enumerate(order)]


def test_fusion_lifts_a_lexical_match_and_keeps_cosine_scores() -> None:
    dense = _hits(["a:001", "b:000", "a:000"])
    fused = fuse("כמה עולה, מה המחיר?", dense, LexicalIndex(CHUNKS, LEXICAL), 1)
    assert fused[0].chunk.chunk_id == "a:000"
    assert {h.chunk.chunk_id: h.score for h in fused} == {h.chunk.chunk_id: h.score for h in dense}


def test_fusion_without_any_lexical_match_keeps_the_dense_order() -> None:
    dense = _hits(["b:000", "a:001", "a:000"])
    fused = fuse("zzz", dense, LexicalIndex(CHUNKS, LEXICAL), 60)
    assert [h.chunk.chunk_id for h in fused] == ["b:000", "a:001", "a:000"]


def test_fusion_ties_fall_back_to_cosine_then_chunk_id() -> None:
    dense = [RetrievedChunk(chunk=c, score=0.5) for c in reversed(CHUNKS)]
    fused = fuse(
        "zzz", sorted(dense, key=lambda h: h.chunk.chunk_id), LexicalIndex(CHUNKS, LEXICAL), 60
    )
    assert [h.chunk.chunk_id for h in fused] == ["a:000", "a:001", "b:000"]


def test_open_retriever_builds_the_lexical_index_only_when_enabled(tmp_path: Path) -> None:
    settings = load_settings()
    fake = settings.embeddings.model_copy(update={"provider": "fake"})
    build_index(
        CHUNKS,
        FakeEmbedder(),
        ChunkingConfig(min_chars=1, max_chars=500, embed_section_chars=60, spec_header=False),
        tmp_path,
    )

    def opened(enabled: bool) -> Retriever:
        retrieval = settings.retrieval.model_copy(
            update={"lexical": LEXICAL.model_copy(update={"enabled": enabled})}
        )
        paths = settings.paths.model_copy(update={"index_dir": str(tmp_path)})
        return open_retriever(
            settings.model_copy(update={"embeddings": fake, "retrieval": retrieval, "paths": paths})
        )

    plain, hybrid = opened(False), opened(True)
    assert plain._lexical is None
    assert hybrid._lexical is not None
    # Both search the same store; only the order may differ, never the set or the scores.
    a = plain.search("המחיר", top_k=3)
    b = hybrid.search("המחיר", top_k=3)
    assert sorted((h.chunk.chunk_id, h.score) for h in a) == sorted(
        (h.chunk.chunk_id, h.score) for h in b
    )
    assert b[0].chunk.chunk_id == "a:000"
    assert ChunkStore(tmp_path).count() == 3
