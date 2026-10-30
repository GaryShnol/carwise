"""Turn telemetry, cost estimate and the cost cap through the pipeline (CW-204).

The cap tests run the real OpenAIClient over a stub SDK (tests.test_llm), so the
budget is enforced by the same code that enforces it in a chat session.
"""

import json
from pathlib import Path
from typing import Any, cast

import pytest
from openai import OpenAI

from app.chat import ends_session
from carwise.config import Settings, load_settings
from carwise.llm.base import LLMUnavailableError, Usage, cost_usd
from carwise.llm.openai_client import OpenAIClient
from carwise.pipeline import Pipeline
from carwise.preferences import Session
from carwise.prompts import PROMPT_VERSIONS
from carwise.registry import load_registry
from carwise.schemas import RefusalReason
from carwise.telemetry import TurnLogger
from tests.test_llm import StubSDK, _completion
from tests.test_pipeline import SpyRetriever, generation, make, understanding

REGISTRY = load_registry()
QUESTION = "כמה טווח יש ל-MG S6?"
UNDERSTOOD = json.dumps(
    {
        "intent": "fact",
        "cars": ["mg_s6"],
        "unrecognized_cars": [],
        "standalone_question": "מה הטווח בפועל של MG S6?",
        "preference_updates": [],
    },
    ensure_ascii=False,
)
GENERATED = json.dumps(
    {"answer": 'הטווח בפועל הוא 400 ק"מ (MG S6, פרק 0).', "used_chunk_ids": ["mg_s6:000"]},
    ensure_ascii=False,
)


def _settings(max_cost_usd: float) -> Settings:
    settings = load_settings()
    llm = settings.llm.model_copy(update={"max_cost_usd": max_cost_usd})
    # The hashing test embedder scores on another scale than e5: no threshold here.
    retrieval = settings.retrieval.model_copy(update={"relevance_threshold": 0.0})
    return settings.model_copy(
        update={"llm": llm, "default_profile": "dev", "retrieval": retrieval}
    )


def real_client_pipeline(
    stub: StubSDK, max_cost_usd: float = 1.0, logger: TurnLogger | None = None
) -> tuple[Pipeline, OpenAIClient]:
    settings = _settings(max_cost_usd)
    client = OpenAIClient(settings, settings.profile("dev"), sdk=cast(OpenAI, stub))
    pipeline = Pipeline(
        settings, REGISTRY, SpyRetriever(settings), client, profile="dev", logger=logger
    )
    return pipeline, client


def _record(logger: TurnLogger, index: int = -1) -> dict[str, Any]:
    lines = logger.path.read_text(encoding="utf-8").strip().split("\n")
    return cast(dict[str, Any], json.loads(lines[index]))


def _logger(tmp_path: Path) -> TurnLogger:
    return TurnLogger(tmp_path, profile="dev", models={"understand": "a", "generate": "b"})


# --- cost estimate -------------------------------------------------------------------------
def test_turn_cost_is_tokens_times_configured_prices() -> None:
    stub = StubSDK(
        _completion(UNDERSTOOD, prompt=2000, cached=1000, out=100),
        _completion(GENERATED, prompt=3000, cached=0, out=200),
    )
    pipeline, client = real_client_pipeline(stub)
    answer = pipeline.ask(QUESTION, [])

    price = load_settings().prices["gpt-5.4-nano"]  # dev profile: nano for both calls
    expected = cost_usd(Usage(2000, 1000, 100), price) + cost_usd(Usage(3000, 0, 200), price)
    assert answer.cost_usd == pytest.approx(expected)
    assert answer.cost_usd == pytest.approx(client.total_cost_usd)
    assert [c.stage for c in answer.calls] == ["understand", "generate"]
    assert sum(c.cost_usd for c in answer.calls) == pytest.approx(answer.cost_usd)
    assert all(
        c.ok and c.model == "gpt-5.4-nano" and c.latency_ms is not None for c in answer.calls
    )


def test_local_model_with_zero_prices_costs_nothing() -> None:
    zero = (
        load_settings()
        .prices["gpt-5.4-nano"]
        .model_copy(update={"input": 0.0, "cached_input": 0.0, "output": 0.0})
    )
    assert cost_usd(Usage(10_000, 0, 10_000), zero) == 0.0


# --- the cost cap through the pipeline -----------------------------------------------------
def test_session_stops_with_a_hebrew_message_once_the_cap_is_reached(tmp_path: Path) -> None:
    # The first turn's generate call crosses a tiny cap and still returns its answer.
    stub = StubSDK(_completion(UNDERSTOOD, prompt=1000), _completion(GENERATED, prompt=20_000))
    logger = _logger(tmp_path)
    pipeline, client = real_client_pipeline(stub, max_cost_usd=0.001, logger=logger)
    session = Session(history_window=6)

    first = pipeline.answer(QUESTION, session)
    assert first.refusal is None and client.total_cost_usd > 0.001
    assert not ends_session(first)

    second = pipeline.answer("ומה המחיר?", session)
    assert second.refusal is RefusalReason.BUDGET_EXCEEDED and ends_session(second)
    assert second.text.startswith("הגעתי למגבלת העלות") and "$0.001" in second.text
    assert len(stub.requests) == 2  # the refused call never reached the API
    assert second.llm_calls == 0 and second.cost_usd == 0.0 and second.calls == []
    assert "budget_exceeded" in second.flags
    assert _record(logger)["refusal"] == "budget_exceeded"


def test_cap_reached_mid_turn_keeps_the_cost_already_spent() -> None:
    stub = StubSDK(_completion(UNDERSTOOD, prompt=50_000, out=5000))
    pipeline, client = real_client_pipeline(stub, max_cost_usd=0.001)
    answer = pipeline.ask(QUESTION, [])
    assert answer.refusal is RefusalReason.BUDGET_EXCEEDED
    assert len(stub.requests) == 1  # understand ran; generate was refused before the API
    assert answer.cost_usd == pytest.approx(client.total_cost_usd) and answer.cost_usd > 0.001
    assert [c.stage for c in answer.calls] == ["understand"]


# --- the telemetry line --------------------------------------------------------------------
def test_line_has_post_check_stage_latency_flags_versions_and_cost(tmp_path: Path) -> None:
    logger = _logger(tmp_path)
    invented = generation('הטווח בפועל הוא 520 ק"מ, כמו בטויוטה (MG S6, פרק 0).')
    pipeline, _, _ = make([understanding(cars=["mg_s6"]), invented, generation()], logger=logger)
    pipeline.ask(QUESTION, [])
    record = _record(logger)

    assert record["post_check"] == {
        "outcome": "regenerated",
        "attempts": [{"cars": ["טויוטה"], "numbers": ["520"]}, {"cars": [], "numbers": []}],
    }
    assert {"understand", "retrieve", "generate", "regenerate", "total"} == set(
        record["latency_ms"]
    )
    assert {"postcheck_cars", "postcheck_numbers", "postcheck_regenerated"} <= set(record["flags"])
    assert record["prompt_versions"] == PROMPT_VERSIONS
    assert record["profile"] == "dev" and record["models"] == {"understand": "a", "generate": "b"}
    assert {"cost_usd", "tokens", "llm_calls"} <= record.keys()
    assert [c["stage"] for c in record["llm_calls_detail"]] == [
        "understand",
        "generate",
        "regenerate",
    ]


def test_cold_start_signals_count_process_and_conversation_turns(tmp_path: Path) -> None:
    logger = _logger(tmp_path)
    replies = [understanding(cars=["mg_s6"]), generation()] * 3
    pipeline, _, _ = make(replies, logger=logger)
    session = Session(history_window=6)
    pipeline.answer(QUESTION, session)
    pipeline.answer("ומה עוד?", session)
    pipeline.answer(QUESTION, Session(history_window=6))  # a new conversation, same process
    turns = [
        (_record(logger, i)["process_turn"], _record(logger, i)["history_messages"])
        for i in range(3)
    ]
    assert turns == [(1, 0), (2, 2), (3, 0)]


def test_failed_call_is_recorded_with_what_it_spent(tmp_path: Path) -> None:
    logger = _logger(tmp_path)
    error = LLMUnavailableError("down", usage=Usage(100, 0, 0), cost_usd=0.00002, attempts=2)
    pipeline, _, _ = make([error], logger=logger)
    pipeline.ask(QUESTION, [])
    [call] = _record(logger)["llm_calls_detail"]
    assert call["stage"] == "understand" and call["ok"] is False and call["model"] is None
    assert call["attempts"] == 2 and call["cost_usd"] == 0.00002 and call["latency_ms"] is None


def test_secrets_and_user_text_never_reach_the_log(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = "sk-test-DO-NOT-LOG-1234567890"
    monkeypatch.setenv("OPENAI_API_KEY", secret)
    logger = _logger(tmp_path)
    stub = StubSDK(_completion(UNDERSTOOD), _completion(GENERATED))
    pipeline, _ = real_client_pipeline(stub, logger=logger)
    pipeline.ask(QUESTION, [])
    raw = logger.path.read_text(encoding="utf-8")
    assert secret not in raw and "sk-" not in raw
    assert "כמה טווח" not in raw and "400 ק" not in raw  # no message, no answer text
