"""CW-303 step 2: table labels, option A (spec header) and option B (forced spec box).

Synthetic chunks only (the repository is public); real car ids come from the registry
because the pipeline resolves names through it.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from carwise.config import ChunkingConfig, load_settings
from carwise.ingest.chunk import SPEC_HEADER, chunk_document, table_labels
from carwise.ingest.clean import Block, BlockKind, Document
from carwise.llm.fake import FakeLLMClient
from carwise.pipeline import Pipeline
from carwise.registry import load_registry
from carwise.retrieval.embedder import FakeEmbedder, Vector
from carwise.retrieval.retriever import Retriever
from carwise.retrieval.store import ChunkStore, build_index
from carwise.schemas import Chunk, Generation, Intent, Understanding

REGISTRY = load_registry()
SETTINGS = load_settings()


def test_table_labels_take_the_label_part_once_in_order() -> None:
    rows = ["מחיר: 100", '0 ל-100 קמ"ש (שניות): 7.3', "מחיר: 120", "שורה בלי נקודתיים"]
    assert table_labels(rows) == ["מחיר", '0 ל-100 קמ"ש (שניות)']


def _doc(spec_rows: list[str]) -> Document:
    car = REGISTRY.get("mg_s6")
    blocks = [
        Block(kind=BlockKind.HEADING, text="נהיגה", level=2),
        Block(kind=BlockKind.PARAGRAPH, text="פסקה על הנהיגה " * 30),
        Block(kind=BlockKind.HEADING, text="הרכב הנבחן", level=2),
        *[Block(kind=BlockKind.TABLE_ROW, text=row) for row in spec_rows],
    ]
    return Document(car_id=car.id, source_url=car.url, title="כותרת", published=None, blocks=blocks)


def _limits(spec_header: bool) -> ChunkingConfig:
    return SETTINGS.chunking.model_copy(update={"spec_header": spec_header, "min_chars": 50})


def test_option_a_adds_the_table_labels_to_the_embedded_header_only() -> None:
    rows = ["מחיר: 168,888", '0 ל-100 קמ"ש (שניות): 7.3']
    car = REGISTRY.get("mg_s6")
    plain = chunk_document(_doc(rows), car, _limits(False))
    enriched = chunk_document(_doc(rows), car, _limits(True))
    spec = next(c for c in enriched if c.table_labels)
    assert spec.table_labels == ["מחיר", '0 ל-100 קמ"ש (שניות)']
    assert SPEC_HEADER + 'מחיר, 0 ל-100 קמ"ש (שניות)' in spec.embed_text
    # The text the model reads and cites is unchanged; prose chunks get no header.
    assert [c.text for c in plain] == [c.text for c in enriched]
    assert all(SPEC_HEADER not in c.embed_text for c in enriched if not c.table_labels)
    assert all(SPEC_HEADER not in c.embed_text for c in plain)


def _chunk(car_id: str, index: int, text: str, labels: list[str] | None = None) -> Chunk:
    car = REGISTRY.get(car_id)
    return Chunk(
        chunk_id=f"{car_id}:{index:03d}",
        car=car_id,
        car_name=car.display_name,
        section="פרק",
        source_url=car.url,
        published=date(2026, 1, 1),
        text=text,
        embed_text=text,
        table_labels=labels or [],
    )


CHUNKS = [
    _chunk("mg_s6", 0, "המכונית זולה יותר והנסיעה נעימה"),
    _chunk("mg_s6", 1, "מחיר: 168,888", ["מחיר"]),
    _chunk("aion_ht", 0, "המכונית זולה יותר ומרווחת"),
    _chunk("aion_ht", 1, "מחיר: 179,990", ["מחיר"]),
    _chunk("kia_ev9", 0, "המכונית גדולה"),  # no table: no spec box
]


def test_table_labels_survive_the_store(tmp_path: Path) -> None:
    build_index(CHUNKS, FakeEmbedder(), SETTINGS.chunking, tmp_path)
    assert ChunkStore(tmp_path).chunks() == sorted(CHUNKS, key=lambda c: c.chunk_id)


class InMemoryStore:
    def __init__(self) -> None:
        self.embedder = FakeEmbedder()
        vectors = self.embedder.embed_documents([c.embed_text for c in CHUNKS])
        self.rows = list(zip(CHUNKS, vectors, strict=True))

    def candidates(self, vector: Vector, car_ids: list[str] | None) -> list[tuple[Chunk, float]]:
        return [
            (chunk, round(sum(a * b for a, b in zip(vector, row, strict=True)), 6))
            for chunk, row in self.rows
            if car_ids is None or chunk.car in car_ids
        ]


def _retriever(force: bool, cap: int = 1) -> tuple[Retriever, Pipeline, FakeLLMClient]:
    retrieval = SETTINGS.retrieval.model_copy(update={"force_spec_box": force, "per_car_cap": cap})
    settings = SETTINGS.model_copy(update={"retrieval": retrieval})
    store = InMemoryStore()
    retriever = Retriever(store, store.embedder, retrieval)
    llm = FakeLLMClient([])
    return retriever, Pipeline(settings, REGISTRY, retriever, llm), llm


def test_spec_boxes_pick_each_cars_table_chunk_with_its_real_score() -> None:
    retriever, _, _ = _retriever(False)
    boxes = retriever.spec_boxes("מה זול יותר", ["mg_s6", "aion_ht", "kia_ev9"])
    assert [b.chunk.chunk_id for b in boxes] == ["mg_s6:001", "aion_ht:001"]
    ranked = {h.chunk.chunk_id: h.score for h in retriever.search("מה זול יותר", top_k=10)}
    assert all(b.score == ranked[b.chunk.chunk_id] for b in boxes)


def _ask(force: bool, intent: Intent, cars: list[str]) -> list[str]:
    _, pipeline, llm = _retriever(force)
    llm.add(
        Understanding(
            intent=intent,
            cars=cars,
            unrecognized_cars=[],
            standalone_question="מה זול יותר",
            preference_updates=[],
        ),
        Generation(answer="תשובה קצרה", used_chunk_ids=[]),
    )
    return [hit.chunk.chunk_id for hit in pipeline.ask("מה זול יותר?", []).retrieved]


def test_option_b_adds_missing_spec_boxes_for_comparisons_only() -> None:
    plain = _ask(False, Intent.COMPARE, ["mg_s6", "aion_ht"])
    forced = _ask(True, Intent.COMPARE, ["mg_s6", "aion_ht"])
    assert "mg_s6:001" not in plain and "aion_ht:001" not in plain  # the cap of 1 kept prose
    assert forced[: len(plain)] == plain  # the normal result is kept, in order
    assert set(forced) - set(plain) == {"mg_s6:001", "aion_ht:001"}
    assert _ask(True, Intent.FACT, ["mg_s6"]) == _ask(False, Intent.FACT, ["mg_s6"])
