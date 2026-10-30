"""CW-306: a recommendation searches all cars; the cars its plan names are only a hint.

The follow-up case mirrors the recorded family scenario: after earlier answers, the plan
of the last turn names Kia EV9, Link & Co 01 and Genesis GV80, while the electric family
cars the user is after (MG S6, Aion HT) must still be reachable. Synthetic chunk text
only (the repository is public); car ids come from the registry.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from carwise.config import load_settings
from carwise.llm.fake import FakeLLMClient
from carwise.pipeline import Pipeline
from carwise.preferences import Session
from carwise.registry import load_registry
from carwise.retrieval.embedder import FakeEmbedder, Vector
from carwise.retrieval.retriever import Retriever
from carwise.schemas import Chunk, Generation, Intent, RetrievedChunk, Understanding

REGISTRY = load_registry()
LOADED = load_settings()
# The hashing test embedder scores on another scale than e5: no threshold here.
SETTINGS = LOADED.model_copy(
    update={"retrieval": LOADED.retrieval.model_copy(update={"relevance_threshold": 0.0})}
)
FAMILY = "רכב חשמלי מרווח למשפחה עם ילדים"


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
    _chunk("mg_s6", 0, f"{FAMILY} ונוח מאוד"),
    _chunk("aion_ht", 0, f"{FAMILY} עם מושב אחורי גדול"),
    _chunk("kia_ev9", 0, "דוח צריכה חודשי"),
    _chunk("kia_ev9", 1, "טווח ממוצע חודשי: 432", ["טווח ממוצע חודשי"]),
    _chunk("link_and_co_01", 0, "פלאג-אין עם בידוד טוב"),
    _chunk("link_and_co_01", 1, "מחיר: 198,900", ["מחיר"]),
    _chunk("genesis_gv80", 0, "מנוע בנזין גדול"),
    _chunk("genesis_gv80", 1, "מחיר: 575,990", ["מחיר"]),
]


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


class SpyRetriever(Retriever):
    def __init__(self) -> None:
        store = InMemoryStore()
        super().__init__(store, store.embedder, SETTINGS.retrieval)
        self.calls: list[str] = []

    def search(self, query: str, car_ids: Any = None, top_k: Any = None) -> list[RetrievedChunk]:
        self.calls.append("search")
        return super().search(query, car_ids, top_k)

    def search_per_car(
        self, query: str, car_ids: Any, top_k_per_car: Any = None
    ) -> list[RetrievedChunk]:
        self.calls.append("search_per_car")
        return super().search_per_car(query, car_ids, top_k_per_car)

    def search_all(
        self, query: str, top_k: Any = None, per_car_cap: Any = None
    ) -> list[RetrievedChunk]:
        self.calls.append("search_all")
        return super().search_all(query, top_k, per_car_cap)


def plan(intent: Intent, cars: list[str], question: str = FAMILY) -> Understanding:
    return Understanding(
        intent=intent,
        cars=cars,
        unrecognized_cars=[],
        standalone_question=question,
        preference_updates=[],
    )


def reply(text: str = "תשובה קצרה") -> Generation:
    return Generation(answer=text, used_chunk_ids=[])


def _pipeline() -> tuple[Pipeline, FakeLLMClient, SpyRetriever]:
    retriever = SpyRetriever()
    llm = FakeLLMClient([])
    return Pipeline(SETTINGS, REGISTRY, retriever, llm), llm, retriever


NAMED = ["kia_ev9", "link_and_co_01", "genesis_gv80"]


def test_recommend_with_named_cars_searches_all_cars() -> None:
    pipeline, llm, retriever = _pipeline()
    llm.add(plan(Intent.RECOMMEND, NAMED), reply())
    answer = pipeline.ask(f"{FAMILY}?", [])
    assert retriever.calls == ["search_all"]  # never filtered down to the named cars
    cars = {hit.chunk.car for hit in answer.retrieved}
    assert {"mg_s6", "aion_ht"} <= cars


def test_named_cars_are_a_hint_their_spec_boxes_join_the_candidates() -> None:
    pipeline, llm, _ = _pipeline()
    llm.add(plan(Intent.RECOMMEND, NAMED), reply())
    ids = [hit.chunk.chunk_id for hit in pipeline.ask(f"{FAMILY}?", []).retrieved]
    for spec in ("kia_ev9:001", "link_and_co_01:001", "genesis_gv80:001"):
        assert spec in ids
    assert len(ids) == len(set(ids))  # a spec box already retrieved is not added twice


def test_follow_up_turn_naming_cars_from_the_history_still_reaches_other_cars() -> None:
    """The recorded family scenario: the last plan names three cars from earlier answers."""
    pipeline, llm, retriever = _pipeline()
    session = Session(history_window=SETTINGS.llm.history_window)
    llm.add(
        plan(Intent.RECOMMEND, [], "אני מחפש רכב חשמלי"),
        reply("בין הרכבים שנבחנו יש את קיה EV9, לינק אנד קו 01 וג'נסיס GV80."),
        plan(Intent.RECOMMEND, NAMED, f"מה מומלץ: {FAMILY}"),
        reply(),
    )
    pipeline.answer("אני מחפש רכב חשמלי", session)
    last = pipeline.answer("אנחנו חמישה, מה אתה ממליץ?", session)
    assert retriever.calls == ["search_all", "search_all"]
    cars = [hit.chunk.car for hit in last.retrieved]
    assert "mg_s6" in cars and "aion_ht" in cars
    assert cars.index("mg_s6") < cars.index("kia_ev9")  # the best matches come first


def test_recommend_without_named_cars_is_unchanged() -> None:
    pipeline, llm, retriever = _pipeline()
    llm.add(plan(Intent.RECOMMEND, []), reply())
    answer = pipeline.ask(f"{FAMILY}?", [])
    assert retriever.calls == ["search_all"]
    assert all(not hit.chunk.table_labels for hit in answer.retrieved[:2])


def test_fact_and_compare_still_restrict_to_the_named_cars() -> None:
    pipeline, llm, retriever = _pipeline()
    llm.add(plan(Intent.FACT, ["kia_ev9"]), reply(), plan(Intent.COMPARE, NAMED[:2]), reply())
    fact = pipeline.ask("כמה טווח לקיה EV9?", [])
    compare = pipeline.ask("קיה EV9 או לינק אנד קו 01?", [])
    assert retriever.calls == ["search", "search_per_car"]
    assert {h.chunk.car for h in fact.retrieved} == {"kia_ev9"}
    assert {h.chunk.car for h in compare.retrieved} == {"kia_ev9", "link_and_co_01"}
