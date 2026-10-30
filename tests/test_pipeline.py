import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from carwise.config import Settings, load_settings
from carwise.guardrails import answer_text_problem, mentioned
from carwise.llm.base import LLMOutputError
from carwise.llm.fake import FakeLLMClient
from carwise.pipeline import Pipeline
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
from carwise.telemetry import TurnLogger

# Synthetic chunks only (the repository is public); real car ids and names come
# from the registry, because the pipeline resolves names through it.
REGISTRY = load_registry()
TEXTS = {
    "mg_s6": ["הטווח בפועל הוא 400 קילומטר בנסיעה רגילה", "המחיר הוא 180 אלף שקל עם אבזור מלא"],
    "aion_ht": ["הטווח בפועל הוא 350 קילומטר בנסיעה רגילה", "המחיר הוא 170 אלף שקל"],
    "kia_ev9": ["צריכת החשמל הממוצעת נמדדה לאורך כל החודש"],
}


def _chunks() -> list[Chunk]:
    chunks = []
    for car_id, texts in TEXTS.items():
        car = REGISTRY.get(car_id)
        for index, text in enumerate(texts):
            section = f"פרק {index}"
            chunks.append(
                Chunk(
                    chunk_id=f"{car_id}:{index:03d}",
                    car=car_id,
                    car_name=car.display_name,
                    section=section,
                    source_url=car.url,
                    published=date(2026, 1, 1),
                    text=text,
                    embed_text=f"{car.display_name} — {section}\n{text}",
                )
            )
    return chunks


class InMemoryStore:
    """The retriever's store contract over a list, scored with the hashing embedder."""

    def __init__(self, chunks: list[Chunk]) -> None:
        self.embedder = FakeEmbedder()
        vectors = self.embedder.embed_documents([c.embed_text for c in chunks])
        self.rows = list(zip(chunks, vectors, strict=True))

    def candidates(self, vector: Vector, car_ids: list[str] | None) -> list[tuple[Chunk, float]]:
        return [
            (chunk, round(sum(a * b for a, b in zip(vector, row, strict=True)), 6))
            for chunk, row in self.rows
            if car_ids is None or chunk.car in car_ids
        ]


class SpyRetriever(Retriever):
    def __init__(self, settings: Settings) -> None:
        store = InMemoryStore(_chunks())
        super().__init__(store, store.embedder, settings.retrieval)
        self.calls: list[tuple[str, Any]] = []

    def search(self, query: str, car_ids: Any = None, top_k: Any = None) -> list[RetrievedChunk]:
        self.calls.append(("search", car_ids))
        return super().search(query, car_ids, top_k)

    def search_per_car(
        self, query: str, car_ids: Any, top_k_per_car: Any = None
    ) -> list[RetrievedChunk]:
        self.calls.append(("search_per_car", car_ids))
        return super().search_per_car(query, car_ids, top_k_per_car)

    def search_all(
        self, query: str, top_k: Any = None, per_car_cap: Any = None
    ) -> list[RetrievedChunk]:
        self.calls.append(("search_all", None))
        return super().search_all(query, top_k, per_car_cap)


def _settings(threshold: float = 0.0) -> Settings:
    settings = load_settings()
    retrieval = settings.retrieval.model_copy(update={"relevance_threshold": threshold})
    return settings.model_copy(update={"retrieval": retrieval})


def understanding(
    intent: Intent = Intent.FACT,
    cars: list[str] | None = None,
    unrecognized: list[str] | None = None,
    question: str = "מה הטווח בפועל של MG S6?",
) -> Understanding:
    return Understanding(
        intent=intent,
        cars=cars or [],
        unrecognized_cars=unrecognized or [],
        standalone_question=question,
        preference_updates=[],
    )


def generation(
    answer: str = 'הטווח בפועל הוא 400 ק"מ (MG S6, פרק 0).', ids: list[str] | None = None
) -> Generation:
    return Generation(answer=answer, used_chunk_ids=["mg_s6:000"] if ids is None else ids)


def make(
    replies: list[Any], threshold: float = 0.0, logger: TurnLogger | None = None
) -> tuple[Pipeline, FakeLLMClient, SpyRetriever]:
    settings = _settings(threshold)
    llm = FakeLLMClient(replies)
    retriever = SpyRetriever(settings)
    return Pipeline(settings, REGISTRY, retriever, llm, logger=logger), llm, retriever


# --- happy path ------------------------------------------------------------------------
def test_fact_question_is_answered_with_checked_citations() -> None:
    pipeline, llm, retriever = make([understanding(cars=["mg_s6"]), generation()])
    answer = pipeline.ask("כמה טווח יש ל-MG S6?", [])

    assert answer.refusal is None and answer.intent is Intent.FACT
    assert answer.text.startswith("הטווח בפועל")
    assert [s.chunk_id for s in answer.sources] == ["mg_s6:000"]
    assert answer.sources[0].car_name == "MG S6" and answer.sources[0].source_url.startswith(
        "https://"
    )
    assert retriever.calls == [("search", ["mg_s6"])]
    assert {hit.chunk.car for hit in answer.retrieved} == {"mg_s6"}
    assert answer.llm_calls == 2 and answer.dropped_chunk_ids == []
    assert {"understand", "retrieve", "generate", "total"} <= answer.latency_ms.keys()

    profile = load_settings().profile()
    assert [call.model for call in llm.calls] == [profile.understand_model, profile.generate_model]
    generate_input = llm.calls[1].messages[0]["content"]
    assert (
        'id="mg_s6:000"' in generate_input
        and "Question: מה הטווח בפועל של MG S6?" in generate_input
    )


def test_comparison_retrieves_each_car_separately() -> None:
    plan = understanding(Intent.COMPARE, ["mg_s6", "aion_ht"], question="השווה טווח MG S6 ואיון HT")
    pipeline, _, retriever = make([plan, generation(ids=["mg_s6:000", "aion_ht:000"])])
    answer = pipeline.ask("מה ההבדל בטווח בין MG S6 לאיון HT?", [])
    assert retriever.calls == [("search_per_car", ["mg_s6", "aion_ht"])]
    assert {hit.chunk.car for hit in answer.retrieved} == {"mg_s6", "aion_ht"}
    assert [s.car for s in answer.sources] == ["mg_s6", "aion_ht"]


def test_question_without_a_car_searches_all_cars() -> None:
    plan = understanding(Intent.RECOMMEND, question="איזה רכב חשמלי זול?")
    pipeline, _, retriever = make([plan, generation(ids=["aion_ht:001"])])
    pipeline.ask("איזה רכב חשמלי הכי זול?", [])
    assert retriever.calls == [("search_all", None)]


# --- registry gate -----------------------------------------------------------------------
def test_unknown_car_is_refused_without_a_generation_call() -> None:
    plan = understanding(unrecognized=["טויוטה קורולה"], question="מה דעתך על טויוטה קורולה?")
    pipeline, llm, retriever = make([plan])
    answer = pipeline.ask("מה דעתך על טויוטה קורולה?", [])
    assert answer.refusal is RefusalReason.UNKNOWN_CAR
    assert "טויוטה קורולה" in answer.text and "MG S6" in answer.text  # helps within the corpus
    assert len(llm.calls) == 1 and retriever.calls == [] and answer.sources == []


def test_outside_brand_is_caught_even_when_the_model_misses_it() -> None:
    pipeline, llm, _ = make([understanding(question="כמה עולה הטסלה?")])
    answer = pipeline.ask("כמה עולה הטסלה?", [])  # prefix ה before the brand
    assert answer.refusal is RefusalReason.UNKNOWN_CAR and "טסלה" in answer.not_covered
    assert len(llm.calls) == 1


def test_known_and_unknown_car_together_is_answered_with_a_note() -> None:
    plan = understanding(
        cars=["mg_s6"], unrecognized=["BMW X5"], question="כמה עולה BMW X5 לעומת MG S6?"
    )
    pipeline, llm, _ = make([plan, generation(ids=["mg_s6:001"])])
    answer = pipeline.ask("כמה עולה BMW X5 לעומת MG S6?", [])
    assert answer.refusal is None and answer.not_covered == ["BMW X5"]  # brand "BMW" deduplicated
    assert "Cars the articles do not cover: BMW X5" in llm.calls[1].messages[0]["content"]


def test_unknown_car_refusal_suggests_cars_from_the_users_own_words() -> None:
    message = "כמה טווח יש לטסלה מודל Y החשמלית?"
    plan = understanding(unrecognized=["טסלה מודל Y"], question=message)
    pipeline, llm, retriever = make([plan])
    answer = pipeline.ask(message, [])
    assert answer.refusal is RefusalReason.UNKNOWN_CAR
    assert answer.suggested_cars == ["kia_ev9", "mg_s6", "aion_ht"]  # the three electric cars
    assert "MG S6 (רכב פנאי, חשמלי)" in answer.text and "ג'נסיס GV80" not in answer.text
    assert len(llm.calls) == 1 and retriever.calls == []


# --- similarity gate ---------------------------------------------------------------------
def test_low_similarity_is_refused_without_a_generation_call() -> None:
    pipeline, llm, _ = make([understanding(cars=["mg_s6"])], threshold=0.99)
    answer = pipeline.ask("כמה טווח יש ל-MG S6?", [])
    assert answer.refusal is RefusalReason.LOW_RELEVANCE
    assert len(llm.calls) == 1 and answer.retrieved  # retrieval ran, generation did not
    assert answer.suggested_cars == ["mg_s6"]  # closest by chunk score, inside the corpus
    assert answer.text.startswith("לא מצאתי בכתבות") and "MG S6" in answer.text


def test_threshold_comes_from_config_and_passes_scores_at_or_above_it() -> None:
    probe, _, _ = make([understanding(cars=["mg_s6"])], threshold=0.99)
    best = max(hit.score for hit in probe.ask("כמה טווח יש ל-MG S6?", []).retrieved)
    pipeline, llm, _ = make([understanding(cars=["mg_s6"]), generation()], threshold=best)
    answer = pipeline.ask("כמה טווח יש ל-MG S6?", [])
    assert answer.refusal is None and len(llm.calls) == 2 and answer.suggested_cars == []


# --- history -------------------------------------------------------------------------------
def test_follow_up_uses_history_and_the_rewritten_question() -> None:
    history = [
        {"role": "user", "content": "מה המחיר של MG S6?"},
        {"role": "assistant", "content": "המחיר הוא 180 אלף שקל (MG S6, פרק 1)."},
    ]
    plan = understanding(cars=["aion_ht"], question="מה המחיר של איון HT?")
    pipeline, llm, retriever = make([plan, generation(ids=["aion_ht:001"])])
    answer = pipeline.ask("ומה לגבי איון?", history)
    assert llm.calls[0].messages == [*history, {"role": "user", "content": "ומה לגבי איון?"}]
    assert retriever.calls == [("search", ["aion_ht"])]
    assert answer.standalone_question == "מה המחיר של איון HT?"
    assert [s.car for s in answer.sources] == ["aion_ht"]


def test_history_is_cut_to_the_configured_window() -> None:
    window = load_settings().llm.history_window
    history = [{"role": "user", "content": f"הודעה {i}"} for i in range(window + 4)]
    pipeline, llm, _ = make([understanding(cars=["mg_s6"]), generation()])
    pipeline.ask("כמה טווח יש ל-MG S6?", history)
    assert llm.calls[0].messages[:-1] == history[-window:]


# --- citations and output guard ------------------------------------------------------------
def test_cited_ids_that_were_not_retrieved_are_dropped() -> None:
    reply = generation(ids=["mg_s6:000", "kia_ev9:000", "made_up:999"])
    pipeline, _, _ = make([understanding(cars=["mg_s6"]), reply])
    answer = pipeline.ask("כמה טווח יש ל-MG S6?", [])
    assert [s.chunk_id for s in answer.sources] == ["mg_s6:000"]
    assert answer.dropped_chunk_ids == ["kia_ev9:000", "made_up:999"]
    assert "dropped_unretrieved_ids" in answer.flags


@pytest.mark.parametrize(
    "text",
    [
        "צריכת הדלק לא מוזכרת בכתבה. mentioned_in_context=false",  # seen in the CW-104 spike
        'הטווח הוא 400 ק"מ, used_chunk_ids: mg_s6:000',
        'הטווח הוא 400 ק"מ (mg_s6:000)',
        "The range is 400 km.",
        "   ",
    ],
)
def test_answer_guard_rejects_field_names_ids_and_non_hebrew(text: str) -> None:
    assert answer_text_problem(text) is not None
    with pytest.raises(ValueError):
        Generation(answer=text, used_chunk_ids=[])


def test_answer_guard_accepts_hebrew_with_latin_car_names() -> None:
    text = 'הטווח בפועל של MG S6 הוא 400 ק"מ (MG S6, הטווח). ל-RS3 יש 400 כ"ס.'
    assert answer_text_problem(text) is None


def test_unusable_generation_gives_a_polite_error_not_a_crash() -> None:
    bad_json = json.dumps({"answer": "אין מידע. mentioned_in_context=false", "used_chunk_ids": []})
    pipeline, _, _ = make([understanding(cars=["mg_s6"]), bad_json])
    answer = pipeline.ask("כמה טווח יש ל-MG S6?", [])
    assert answer.refusal is RefusalReason.LLM_ERROR and "mentioned_in_context" not in answer.text


# --- routing and input -------------------------------------------------------------------
@pytest.mark.parametrize("intent", [Intent.CHITCHAT, Intent.OUT_OF_SCOPE])
def test_chitchat_and_off_topic_skip_retrieval(intent: Intent) -> None:
    pipeline, llm, retriever = make([understanding(intent, question="תכתוב שיר")])
    answer = pipeline.ask("תכתוב לי שיר על הים", [])
    assert answer.refusal is RefusalReason.OUT_OF_SCOPE and "רכב" in answer.text
    assert retriever.calls == [] and len(llm.calls) == 1


def test_understand_failure_falls_back_to_the_raw_message() -> None:
    pipeline, _, retriever = make([LLMOutputError("bad twice", attempts=2), generation()])
    answer = pipeline.ask("כמה טווח יש ל-MG S6?", [])
    assert "understand_fallback" in answer.flags
    assert retriever.calls == [("search", ["mg_s6"])]  # car found by name matching
    assert answer.standalone_question == "כמה טווח יש ל-MG S6?" and answer.refusal is None


@pytest.mark.parametrize("message", ["", "   ", "א" * 501])
def test_empty_or_too_long_input_never_reaches_the_model(message: str) -> None:
    pipeline, llm, _ = make([])
    answer = pipeline.ask(message, [])
    assert answer.refusal in (RefusalReason.EMPTY, RefusalReason.TOO_LONG)
    assert llm.calls == [] and answer.llm_calls == 0


def test_greeting_says_knowledge_is_limited_to_the_eight_cars() -> None:
    pipeline, _, _ = make([])
    text = pipeline.greeting()
    assert "שמונה" in text and all(car.display_name in text for car in REGISTRY.cars)


# --- name matching and telemetry -----------------------------------------------------------
def test_name_matching_handles_prefixes_and_apostrophe_variants() -> None:
    assert mentioned("כמה עולה לאודי RS3?", ["אודי RS3"]) == ["אודי RS3"]
    assert mentioned("ומה עם הג׳נסיס GV80", ["ג'נסיס GV80"]) == ["ג'נסיס GV80"]
    assert mentioned("רכב משפחתי", ["רנו"]) == []  # no match inside other words
    assert mentioned("bmw x5", ["BMW"]) == ["BMW"]


def test_outside_brands_never_shadow_a_car_in_the_corpus() -> None:
    brands = load_settings().guardrails.outside_brands
    for car in REGISTRY.cars:
        overlap = mentioned(" ".join(car.aliases), brands)
        assert overlap == [], car.id


def test_telemetry_line_has_ids_and_costs_but_no_text(tmp_path: Path) -> None:
    logger = TurnLogger(tmp_path, profile="dev", models={"understand": "a", "generate": "b"})
    pipeline, _, _ = make([understanding(cars=["mg_s6"]), generation()], logger=logger)
    pipeline.ask("כמה טווח יש ל-MG S6?", [])
    record = json.loads(logger.path.read_text(encoding="utf-8").strip())
    assert record["used_chunk_ids"] == ["mg_s6:000"] and record["intent"] == "fact"
    assert (
        record["retrieved"][0]["chunk_id"].startswith("mg_s6:")
        and "score" in record["retrieved"][0]
    )
    assert {"understand", "generate", "total"} <= record["latency_ms"].keys()
    raw = logger.path.read_text(encoding="utf-8")
    assert "כמה טווח" not in raw and TEXTS["mg_s6"][0] not in raw  # no message, no chunk text
