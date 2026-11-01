"""CW-306: a recommendation searches all cars; the cars its plan names are only a hint.

The follow-up case mirrors the recorded family scenario: after earlier answers, the plan
of the last turn names Kia EV9, Link & Co 01 and Genesis GV80, while the electric family
cars the user is after (MG S6, Aion HT) must still be reachable. Synthetic chunk text
only (the repository is public); car ids come from the registry.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

import pytest

from carwise import guardrails
from carwise.config import load_settings
from carwise.llm.fake import FakeLLMClient
from carwise.pipeline import Pipeline
from carwise.preferences import Session
from carwise.registry import load_registry
from carwise.retrieval.embedder import FakeEmbedder, Vector
from carwise.retrieval.retriever import Retriever
from carwise.schemas import (
    Chunk,
    Generation,
    Intent,
    RefusalReason,
    RetrievedChunk,
    Understanding,
)

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


# --- CW-606: a recommendation or ranking says it covers only the eight cars ------------
SCOPED = [
    "מבין שמונה הרכבים שנבחנו, MG S6 הכי מתאים.",
    "MG S6 הכי מהיר מבין 8 הרכבים בכתבות.",
    "מתוך שמונת הדגמים שנבחנו, איון HT הכי זול.",
    "לפי שמונה כתבות המבחן, MG S6 מתאים.",
    "בין שמונה כלי הרכב שנבחנו, MG S6 מתאים.",
    "מבין השמונה שנבחנו, איון HT הכי זול.",
    "מתוך שמונת שנסקרו, MG S6 מתאים.",
    "MG S6 הכי מתאים מבין השמונה.",
    "מתוך ה-8, איון HT הכי זול.",
    "מכל הרכבים השמונה, MG S6 הכי מהיר.",
    "בין השמונה שבכתבות, איון HT מתאים.",
    "הזול ביותר מהשמונה הוא סיטרואן C3.",
    "הכי מהיר מהשמונה: אודי RS3.",
    "מתוך השמונה – MG S6 הכי מתאים.",
    "MG S6 הכי מתאים מבין ה-8",
    "**שמונה** הרכבים שנבחנו כוללים את MG S6.",
    'מבין "שמונה" הרכבים, MG S6 מתאים.',
    "ומבין השמונה, MG S6 הכי מתאים.",
    "לכל השמונה יש מסך מגע.",
    guardrails.SCOPE_NOTE,
]
UNSCOPED = [
    "MG S6 הכי מתאים למשפחה (MG S6, פרק).",
    "לאיון HT יש תיבה בת שמונה הילוכים.",
    "MG S6 מאיץ בשמונה שניות.",
    "שמונים רכבים נמכרו.",
    "18 רכבים נבדקו.",
    "יש לו שמונה מושבים.",
    "ברכב 8 כריות אוויר.",
    "ניתנות שמונה שנות אחריות.",
    "השמונה שניות האלה מרשימות.",
    "בשמונה שעבר הוא נמכר.",
    "כל השמונה שניות עברו מהר.",
    "בין השמונה לתשע שניות.",
    "רוב הרכבים מאיצים בין השמונה לעשר שניות.",
    "מבין השמונה שניות, רוב הזמן הוא בהילוך ראשון.",
    "כל ה-8 שניות עברו מהר.",
    "בין ה-8 ל-9 שניות.",
    "מבין ה-8 שניות, שתיים בהילוך ראשון.",
    'מתוך ה-8 קמ"ש הראשונים.',
    "בין ה-8-9 שניות.",
    "בין ה-8.5 ל-9 שניות.",
    "בשמונה שניות.",
]


@pytest.mark.parametrize("text", SCOPED)
def test_scope_statement_is_detected_in_several_phrasings(text: str) -> None:
    assert guardrails.states_scope(text)


@pytest.mark.parametrize("text", UNSCOPED)
def test_eight_of_something_else_is_not_a_scope_statement(text: str) -> None:
    assert not guardrails.states_scope(text)


def test_scope_note_cannot_trip_the_post_check() -> None:
    brands = SETTINGS.guardrails.outside_brands
    note = guardrails.SCOPE_NOTE
    assert not re.search(r"\d", note) and guardrails.answer_text_problem(note) is None
    assert guardrails.cars_in_text(note, REGISTRY, brands) == []
    assert guardrails.unsupported_cars(note, [], [], REGISTRY, brands) == []
    allowed = SETTINGS.guardrails.numbers_always_allowed
    assert guardrails.unsupported_numbers(note, [], [], REGISTRY, allowed) == []


def test_recommendation_without_the_statement_gets_it_once() -> None:
    pipeline, llm, _ = _pipeline()
    text = "MG S6 הכי מתאים למשפחה (MG S6, פרק)."
    llm.add(plan(Intent.RECOMMEND, []), Generation(answer=text, used_chunk_ids=["mg_s6:000"]))
    answer = pipeline.ask(f"{FAMILY}?", [])
    assert answer.text == f"{guardrails.SCOPE_NOTE}\n\n{text}"
    assert answer.text.count(guardrails.SCOPE_NOTE) == 1
    assert [source.chunk_id for source in answer.sources] == ["mg_s6:000"]
    assert answer.refusal is None and "scope_note_added" in answer.flags
    assert answer.post_check is not None and not answer.post_check.attempts[0].suspect


def test_ranking_follow_up_does_not_stack_the_note() -> None:
    """Each turn is checked on its own answer: a second ranking turn gets one note too."""
    pipeline, llm, _ = _pipeline()
    session = Session(history_window=SETTINGS.llm.history_window)
    llm.add(
        plan(Intent.RECOMMEND, []),
        reply("הכי מהיר: MG S6."),
        plan(Intent.RECOMMEND, []),
        reply("הכי זול: איון HT."),
    )
    pipeline.answer("מה הכי מהיר?", session)
    second = pipeline.answer("ומה הכי זול?", session)
    assert second.text.count(guardrails.SCOPE_NOTE) == 1


# The digit form is detected too, but the numeric check flags "8" in a model answer.
@pytest.mark.parametrize("text", [SCOPED[0], *SCOPED[2:6]])
def test_recommendation_that_states_the_scope_is_unchanged(text: str) -> None:
    pipeline, llm, _ = _pipeline()
    llm.add(plan(Intent.RECOMMEND, []), reply(text))
    answer = pipeline.ask(f"{FAMILY}?", [])
    assert answer.text == text and "scope_note_added" not in answer.flags


@pytest.mark.parametrize(
    ("intent", "cars"), [(Intent.FACT, ["kia_ev9"]), (Intent.COMPARE, NAMED[:2])]
)
def test_fact_and_compare_answers_never_get_the_note(intent: Intent, cars: list[str]) -> None:
    pipeline, llm, _ = _pipeline()
    llm.add(plan(intent, cars), reply("תשובה קצרה (קיה EV9, פרק)."))
    answer = pipeline.ask("כמה טווח לקיה EV9?", [])
    assert guardrails.SCOPE_NOTE not in answer.text and "scope_note_added" not in answer.flags


def test_fallback_after_a_failed_post_check_does_not_get_the_note() -> None:
    pipeline, llm, _ = _pipeline()
    invented = reply("MG S6 עולה 999 אלף שקל.")  # a number no chunk states, twice
    llm.add(plan(Intent.RECOMMEND, []), invented, invented)
    answer = pipeline.ask(f"{FAMILY}?", [])
    assert answer.refusal is RefusalReason.UNVERIFIED
    assert guardrails.SCOPE_NOTE not in answer.text


def test_clarifying_question_of_a_recommendation_also_gets_the_note() -> None:
    """Deliberate: rule 8 replaces the recommendation, not the scope, with the question,
    and the user learns the scope before answering it."""
    pipeline, llm, _ = _pipeline()
    question = "מה התקציב שלך?"
    llm.add(plan(Intent.RECOMMEND, []), reply(question))
    answer = pipeline.ask("איזה רכב כדאי לי?", [])
    assert answer.text == f"{guardrails.SCOPE_NOTE}\n\n{question}"
