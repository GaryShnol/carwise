"""Post-check of car names and the regenerate-or-fallback path (CW-202)."""

import json
from datetime import date
from pathlib import Path

from carwise.config import load_settings
from carwise.guardrails import unsupported_cars
from carwise.llm.base import LLMOutputError
from carwise.prompts import GENERATE_SYSTEM, PROMPT_DIR, PROMPT_VERSIONS
from carwise.registry import load_registry
from carwise.schemas import Chunk, PostCheckOutcome, RefusalReason, RetrievedChunk
from carwise.telemetry import TurnLogger
from tests.test_pipeline import generation, make, understanding

REGISTRY = load_registry()
BRANDS = load_settings().guardrails.outside_brands
QUESTION = "כמה טווח יש ל-MG S6?"


def hit(car_id: str, text: str) -> RetrievedChunk:
    car = REGISTRY.get(car_id)
    chunk = Chunk(
        chunk_id=f"{car_id}:000",
        car=car_id,
        car_name=car.display_name,
        section="פרק",
        source_url=car.url,
        published=date(2026, 1, 1),
        text=text,
        embed_text=text,
    )
    return RetrievedChunk(chunk=chunk, score=0.8)


def check(answer: str, hits: list[RetrievedChunk], not_covered: list[str] | None = None) -> list:
    return unsupported_cars(answer, hits, not_covered or [], REGISTRY, BRANDS)


# --- the check itself --------------------------------------------------------------------
def test_answer_about_the_retrieved_car_is_clean() -> None:
    hits = [hit("mg_s6", "הטווח בפועל הוא 400 קילומטר")]
    assert check('הטווח של MG S6 הוא 400 ק"מ (MG S6, פרק).', hits) == []


def test_corpus_car_that_was_not_retrieved_is_flagged() -> None:
    hits = [hit("mg_s6", "הטווח בפועל הוא 400 קילומטר")]
    assert check('ל-MG S6 טווח של 400 ק"מ, יותר מאשר לג׳נסיס GV80.', hits) == ["ג'נסיס GV80"]


def test_outside_brand_with_a_hebrew_prefix_is_flagged() -> None:
    hits = [hit("mg_s6", "הטווח בפועל הוא 400 קילומטר")]
    assert check('ל-MG S6 טווח של 400 ק"מ, בדומה לטויוטה.', hits) == ["טויוטה"]


def test_rival_named_in_a_retrieved_chunk_is_allowed() -> None:
    hits = [hit("mg_s6", "המתחרה העיקרית היא טסלה מודל Y, וגם הקיה EV9 בקטגוריה")]
    answer = "הכתבה משווה את MG S6 לטסלה מודל Y ולקיה EV9 (MG S6, פרק)."
    assert check(answer, hits) == []


def test_brand_the_user_asked_about_may_be_named_as_not_covered() -> None:
    hits = [hit("mg_s6", "המחיר הוא 180 אלף שקל")]
    answer = "אין בכתבות מידע על BMW X5. המחיר של MG S6 הוא 180 אלף שקל (MG S6, פרק)."
    assert check(answer, hits, ["BMW X5"]) == []
    assert check(answer, hits) == ["BMW"]


# --- regenerate or fall back -------------------------------------------------------------
BAD = generation('הטווח הוא 400 ק"מ, כמו בטויוטה קורולה (MG S6, פרק 0).')
GOOD = generation()


def test_clean_answer_costs_no_extra_call() -> None:
    pipeline, llm, _ = make([understanding(cars=["mg_s6"]), GOOD])
    answer = pipeline.ask(QUESTION, [])
    assert answer.post_check is not None
    assert answer.post_check.outcome is PostCheckOutcome.CLEAN
    assert len(llm.calls) == 2 and "postcheck_suspect" not in answer.flags


def test_suspect_answer_is_regenerated_once_with_the_reason() -> None:
    pipeline, llm, _ = make([understanding(cars=["mg_s6"]), BAD, GOOD])
    answer = pipeline.ask(QUESTION, [])

    assert answer.refusal is None and answer.text == GOOD.answer
    assert answer.post_check is not None
    assert answer.post_check.outcome is PostCheckOutcome.REGENERATED
    assert [a.cars for a in answer.post_check.attempts] == [["טויוטה"], []]
    assert {"postcheck_suspect", "postcheck_regenerated"} <= set(answer.flags)
    assert len(llm.calls) == 3 and answer.llm_calls == 3
    assert "regenerate" in answer.latency_ms

    retry = llm.calls[2].messages
    assert [m["role"] for m in retry] == ["user", "assistant", "user"]
    assert retry[0] == llm.calls[1].messages[0]  # same question and excerpts
    assert "טויוטה קורולה" in retry[1]["content"]  # the rejected answer
    assert "do not support: טויוטה" in retry[2]["content"]


def test_answer_suspect_twice_falls_back_to_a_reply_built_in_code() -> None:
    pipeline, llm, _ = make([understanding(cars=["mg_s6"]), BAD, BAD])
    answer = pipeline.ask(QUESTION, [])

    assert answer.refusal is RefusalReason.UNVERIFIED and answer.sources == []
    assert "טויוטה" not in answer.text and "MG S6" in answer.text
    assert answer.text.startswith("לא הצלחתי לנסח תשובה שנשענת רק על הכתבות")
    assert answer.post_check is not None
    assert answer.post_check.outcome is PostCheckOutcome.FALLBACK
    assert len(answer.post_check.attempts) == 2
    assert "postcheck_fallback" in answer.flags and len(llm.calls) == 3  # never a third generate


def test_failed_regeneration_call_also_falls_back() -> None:
    error = LLMOutputError("bad twice", attempts=2)
    pipeline, _, _ = make([understanding(cars=["mg_s6"]), BAD, error])
    answer = pipeline.ask(QUESTION, [])
    assert answer.refusal is RefusalReason.UNVERIFIED
    assert answer.post_check is not None and len(answer.post_check.attempts) == 1
    assert {"regenerate_LLMOutputError", "postcheck_fallback"} <= set(answer.flags)
    assert answer.llm_calls == 1 + 1 + 2  # understand, generate, two failed retry attempts


def test_refusals_before_generation_have_no_post_check() -> None:
    message = "מה דעתך על טויוטה קורולה?"
    pipeline, _, _ = make([understanding(unrecognized=["טויוטה קורולה"], question=message)])
    assert pipeline.ask(message, []).post_check is None


def test_telemetry_records_both_post_check_attempts(tmp_path: Path) -> None:
    logger = TurnLogger(tmp_path, profile="dev", models={"understand": "a", "generate": "b"})
    pipeline, _, _ = make([understanding(cars=["mg_s6"]), BAD, GOOD], logger=logger)
    pipeline.ask(QUESTION, [])
    record = json.loads(logger.path.read_text(encoding="utf-8").strip())
    assert record["post_check"] == {
        "outcome": "regenerated",
        "attempts": [{"cars": ["טויוטה"]}, {"cars": []}],
    }
    assert record["prompt_versions"] == PROMPT_VERSIONS


# --- prompt v2 ---------------------------------------------------------------------------
def test_generate_prompt_forbids_another_article_since_v2_and_keeps_old_versions() -> None:
    assert PROMPT_VERSIONS["generate"] >= "v2"
    assert "בכתבה אחרת" in GENERATE_SYSTEM and "one set of eight" in GENERATE_SYSTEM
    assert (PROMPT_DIR / "generate.v1.txt").exists() and (PROMPT_DIR / "generate.v2.txt").exists()
