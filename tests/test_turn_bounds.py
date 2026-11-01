"""Bounds on one turn (CW-612): an output-token cap per stage, a truncated reply
treated as invalid, and a per-turn deadline checked before every model call."""

from __future__ import annotations

from typing import Any, cast

import pytest
from openai import OpenAI
from openai.types.chat import ChatCompletion

from carwise.config import Settings, load_settings
from carwise.llm.base import LLMOutputError, Message, T, Usage, cost_usd
from carwise.llm.budget import SharedBudget
from carwise.llm.fake import FakeLLMClient
from carwise.llm.openai_client import OpenAIClient
from carwise.pipeline import Pipeline
from carwise.registry import load_registry
from carwise.schemas import Generation, RefusalReason, Understanding
from tests.test_llm import MODEL, VALID, Answer, StubSDK, _ask
from tests.test_pipeline import SpyRetriever, generation, understanding

REGISTRY = load_registry()
# A reply cut off by the cap: the JSON is unfinished.
CUT = '{"answer": "תשובה ארוכה שנקטעה'


def _completion(content: str, finish_reason: str = "stop", out: int = 20) -> Any:
    return ChatCompletion.model_validate(
        {
            "id": "c1",
            "object": "chat.completion",
            "created": 0,
            "model": MODEL,
            "choices": [
                {
                    "index": 0,
                    "finish_reason": finish_reason,
                    "message": {"role": "assistant", "content": content},
                }
            ],
            "usage": {"prompt_tokens": 100, "completion_tokens": out, "total_tokens": 100 + out},
        }
    )


def _settings(**llm: Any) -> Settings:
    settings = load_settings()
    retrieval = settings.retrieval.model_copy(update={"relevance_threshold": 0.0})
    return settings.model_copy(
        update={"llm": settings.llm.model_copy(update=llm), "retrieval": retrieval}
    )


def _client(stub: StubSDK, budget: SharedBudget | None = None) -> OpenAIClient:
    return OpenAIClient(_settings(), sdk=cast(OpenAI, stub), shared_budget=budget)


# --- config ------------------------------------------------------------------------------
def test_caps_and_deadline_come_from_config() -> None:
    llm = load_settings().llm
    assert llm.max_completion_tokens.understand > 0
    assert llm.max_completion_tokens.generate > llm.max_completion_tokens.understand
    assert llm.turn_deadline_s == 90


# --- the cap in the request ----------------------------------------------------------------
def test_cap_is_sent_in_the_request() -> None:
    stub = StubSDK(_completion(VALID))
    _client(stub).complete_json(
        "s", [{"role": "user", "content": "שאלה"}], Answer, model=MODEL, max_completion_tokens=123
    )
    assert stub.requests[0]["max_completion_tokens"] == 123


def test_no_cap_means_none_is_sent() -> None:
    stub = StubSDK(_completion(VALID))
    _ask(_client(stub))  # the eval judge calls like this; its requests are unchanged
    assert "max_completion_tokens" not in stub.requests[0]


def test_pipeline_sends_each_stage_its_configured_cap() -> None:
    settings = _settings()
    llm = FakeLLMClient([understanding(cars=["mg_s6"]), generation()])
    Pipeline(settings, REGISTRY, SpyRetriever(settings), llm).ask("כמה טווח יש ל-MG S6?", [])
    caps = settings.llm.max_completion_tokens
    assert [call.max_completion_tokens for call in llm.calls] == [caps.understand, caps.generate]


def test_regeneration_uses_the_generate_cap() -> None:
    settings = _settings()
    suspect = generation('הטווח בפועל הוא 987 ק"מ (MG S6, פרק 0).')  # 987 is in no chunk
    llm = FakeLLMClient([understanding(cars=["mg_s6"]), suspect, generation()])
    answer = Pipeline(settings, REGISTRY, SpyRetriever(settings), llm).ask(
        "כמה טווח יש ל-MG S6?", []
    )
    assert "postcheck_regenerated" in answer.flags
    assert llm.calls[2].max_completion_tokens == settings.llm.max_completion_tokens.generate


# --- a reply cut off by the cap ------------------------------------------------------------
def test_cut_off_reply_is_retried_and_never_parsed() -> None:
    # Valid JSON, but cut off: a shortened object must not be acted on.
    stub = StubSDK(_completion(VALID, "length"), _completion(VALID))
    result = _ask(_client(stub))
    assert result.attempts == 2 and result.parsed == Answer(answer="תשובה", cars=["mg_s6"])
    retry = stub.requests[1]["messages"]
    assert retry[-2] == {"role": "assistant", "content": VALID}
    assert retry[-1]["role"] == "user" and "cut off" in retry[-1]["content"]
    assert result.usage.output_tokens == 40  # the cut-off attempt is counted


def test_cut_off_twice_raises_output_error_and_is_charged() -> None:
    budget = SharedBudget(5.0)
    stub = StubSDK(_completion(CUT, "length"), _completion(CUT, "length"))
    client = _client(stub, budget)
    with pytest.raises(LLMOutputError, match="cut off") as caught:
        _ask(client)
    assert len(stub.requests) == 2 and caught.value.attempts == 2
    paid = cost_usd(Usage(200, 0, 40), load_settings().prices[MODEL])
    assert caught.value.cost_usd == pytest.approx(paid)
    assert client.total_cost_usd == pytest.approx(paid)
    assert budget.spent_usd == pytest.approx(paid)


def test_cut_off_generation_twice_gives_the_llm_error_reply() -> None:
    settings = _settings()
    stub = StubSDK(
        _completion(understanding(cars=["mg_s6"]).model_dump_json()),
        _completion(CUT, "length"),
        _completion(CUT, "length"),
    )
    client = OpenAIClient(settings, sdk=cast(OpenAI, stub))
    answer = Pipeline(settings, REGISTRY, SpyRetriever(settings), client).ask(
        "כמה טווח יש ל-MG S6?", []
    )
    assert answer.refusal is RefusalReason.LLM_ERROR
    assert "generate_LLMOutputError" in answer.flags
    assert answer.llm_calls == 3 and answer.cost_usd == pytest.approx(client.total_cost_usd)


def test_cut_off_then_valid_generation_is_answered() -> None:
    settings = _settings()
    stub = StubSDK(
        _completion(understanding(cars=["mg_s6"]).model_dump_json()),
        _completion(CUT, "length"),
        _completion(generation().model_dump_json()),
    )
    client = OpenAIClient(settings, sdk=cast(OpenAI, stub))
    answer = Pipeline(settings, REGISTRY, SpyRetriever(settings), client).ask(
        "כמה טווח יש ל-MG S6?", []
    )
    assert answer.refusal is None and "generation_retried" in answer.flags


# --- the per-turn deadline -----------------------------------------------------------------
class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class Slow(FakeLLMClient):
    """Every call for `schema` takes `seconds` on the fake clock."""

    def __init__(self, clock: Clock, schema: type[Any], seconds: float, replies: list[Any]) -> None:
        super().__init__(replies)
        self._clock, self._schema, self._seconds = clock, schema, seconds

    def complete_json(
        self,
        system: str,
        messages: list[Message],
        schema: type[T],
        *,
        model: str,
        max_completion_tokens: int | None = None,
    ) -> Any:
        if schema is self._schema:
            self._clock.now += self._seconds
        return super().complete_json(
            system, messages, schema, model=model, max_completion_tokens=max_completion_tokens
        )


def _slow(seconds: float) -> tuple[Pipeline, Slow]:
    settings, clock = _settings(), Clock()
    llm = Slow(clock, Understanding, seconds, [understanding(cars=["mg_s6"]), generation()])
    pipeline = Pipeline(settings, REGISTRY, SpyRetriever(settings), llm, clock=clock)
    return pipeline, llm


def test_deadline_passed_before_generate_gives_the_llm_error_reply() -> None:
    pipeline, llm = _slow(seconds=load_settings().llm.turn_deadline_s)
    answer = pipeline.ask("כמה טווח יש ל-MG S6?", [])
    assert answer.refusal is RefusalReason.LLM_ERROR
    assert "turn_deadline_exceeded" in answer.flags
    assert [call.schema for call in llm.calls] == [Understanding]  # no generate call


def test_turn_within_the_deadline_is_answered() -> None:
    pipeline, llm = _slow(seconds=load_settings().llm.turn_deadline_s - 1)
    answer = pipeline.ask("כמה טווח יש ל-MG S6?", [])
    assert answer.refusal is None and "turn_deadline_exceeded" not in answer.flags
    assert [call.schema for call in llm.calls] == [Understanding, Generation]


def test_deadline_is_per_turn() -> None:
    pipeline, llm = _slow(seconds=load_settings().llm.turn_deadline_s - 1)
    pipeline.ask("כמה טווח יש ל-MG S6?", [])
    llm.add(understanding(cars=["mg_s6"]), generation())
    assert pipeline.ask("ומה הטווח בחורף?", []).refusal is None  # a new turn, a new deadline


def test_deadline_passed_before_regenerate_gives_the_code_built_fallback() -> None:
    # The regeneration's existing "provider unavailable" path: the unverified reply,
    # built by code, never the suspect answer.
    settings, clock = _settings(), Clock()
    suspect = generation('הטווח בפועל הוא 987 ק"מ (MG S6, פרק 0).')
    replies = [understanding(cars=["mg_s6"]), suspect]
    llm = Slow(clock, Generation, settings.llm.turn_deadline_s, replies)
    pipeline = Pipeline(settings, REGISTRY, SpyRetriever(settings), llm, clock=clock)
    answer = pipeline.ask("כמה טווח יש ל-MG S6?", [])
    assert answer.refusal is RefusalReason.UNVERIFIED and "987" not in answer.text
    assert "turn_deadline_exceeded" in answer.flags and len(llm.calls) == 2
