import json
from typing import Any, cast

import httpx
import openai
import pytest
from openai import OpenAI
from openai.types.chat import ChatCompletion
from pydantic import BaseModel

from carwise.config import Price, Settings, load_settings
from carwise.llm.base import (
    BudgetExceededError,
    LLMConfigError,
    LLMOutputError,
    LLMUnavailableError,
    Usage,
    cost_usd,
)
from carwise.llm.fake import FakeLLMClient
from carwise.llm.openai_client import OpenAIClient
from carwise.schemas import Generation

MODEL = "gpt-5.4-nano"
NANO = Price(input=0.20, cached_input=0.02, output=1.25)


class Answer(BaseModel):
    answer: str
    cars: list[str]


VALID = json.dumps({"answer": "תשובה", "cars": ["mg_s6"]}, ensure_ascii=False)


def _completion(content: str | None, prompt: int = 100, cached: int = 0, out: int = 20) -> Any:
    return ChatCompletion.model_validate(
        {
            "id": "c1",
            "object": "chat.completion",
            "created": 0,
            "model": MODEL,
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": content},
                }
            ],
            "usage": {
                "prompt_tokens": prompt,
                "completion_tokens": out,
                "total_tokens": prompt + out,
                "prompt_tokens_details": {"cached_tokens": cached},
                "completion_tokens_details": {"reasoning_tokens": 5},
            },
        }
    )


class StubSDK:
    """Stands in for openai.OpenAI: records every request, replays scripted replies."""

    def __init__(self, *replies: Any) -> None:
        self.replies = list(replies)
        self.requests: list[dict[str, Any]] = []
        self.chat = self
        self.completions = self

    def create(self, **kwargs: Any) -> Any:
        self.requests.append(kwargs)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def _settings(**llm: Any) -> Settings:
    settings = load_settings()
    return settings.model_copy(update={"llm": settings.llm.model_copy(update=llm)})


def _client(stub: StubSDK, **llm: Any) -> OpenAIClient:
    return OpenAIClient(_settings(**llm), sdk=cast(OpenAI, stub))


def _ask(client: OpenAIClient, model: str = MODEL) -> Any:
    return client.complete_json(
        "system prompt", [{"role": "user", "content": "שאלה"}], Answer, model=model
    )


def _status_error(cls: type[openai.APIStatusError], status: int, message: str) -> Any:
    response = httpx.Response(status, request=httpx.Request("POST", "https://example.test"))
    return cls(message, response=response, body=None)


def test_cost_bills_cached_input_and_output_at_their_rates() -> None:
    usage = Usage(input_tokens=1_000_000, cached_tokens=200_000, output_tokens=500_000)
    assert cost_usd(usage, NANO) == pytest.approx(0.8 * 0.20 + 0.2 * 0.02 + 0.5 * 1.25)


def test_valid_reply_is_parsed_with_usage_cost_and_latency() -> None:
    client = _client(StubSDK(_completion(VALID, prompt=1000, cached=400, out=100)))
    result = _ask(client)
    assert result.parsed == Answer(answer="תשובה", cars=["mg_s6"])
    assert result.usage == Usage(1000, 400, 100, 5)
    assert result.cost_usd == pytest.approx((600 * 0.20 + 400 * 0.02 + 100 * 1.25) / 1e6)
    assert result.attempts == 1 and result.model == MODEL and result.latency_ms >= 0
    assert client.total_cost_usd == pytest.approx(result.cost_usd)


def test_request_sends_system_first_strict_schema_and_configured_controls() -> None:
    stub = StubSDK(_completion(VALID))
    _ask(_client(stub, temperature=None, reasoning_effort="low", seed=7))
    request = stub.requests[0]
    assert request["messages"][0] == {"role": "system", "content": "system prompt"}
    assert request["messages"][1] == {"role": "user", "content": "שאלה"}
    schema = request["response_format"]["json_schema"]
    assert schema["strict"] is True and schema["schema"]["additionalProperties"] is False
    assert "temperature" not in request  # null in config means "do not send"
    assert request["reasoning_effort"] == "low" and request["seed"] == 7


def test_invalid_reply_is_retried_once_with_the_error() -> None:
    stub = StubSDK(_completion('{"answer": 1}', prompt=100, out=10), _completion(VALID, 150, 0, 20))
    result = _ask(_client(stub))
    assert result.attempts == 2
    assert result.usage.input_tokens == 250 and result.usage.output_tokens == 30  # both attempts
    retry_messages = stub.requests[1]["messages"]
    assert retry_messages[-2] == {"role": "assistant", "content": '{"answer": 1}'}
    assert retry_messages[-1]["role"] == "user"
    assert "did not match the required JSON schema" in retry_messages[-1]["content"]
    assert "cars" in retry_messages[-1]["content"]  # the validation error names the missing field


def test_answer_with_a_link_gets_the_corrective_retry() -> None:
    linked = json.dumps(
        {"answer": 'הטווח 400 ק"מ, https://example.org', "used_chunk_ids": []}, ensure_ascii=False
    )
    fixed = json.dumps({"answer": 'הטווח 400 ק"מ.', "used_chunk_ids": []}, ensure_ascii=False)
    stub = StubSDK(_completion(linked), _completion(fixed))
    client = _client(stub)
    result = client.complete_json(
        "system prompt", [{"role": "user", "content": "שאלה"}], Generation, model=MODEL
    )
    assert result.attempts == 2 and result.parsed.answer == 'הטווח 400 ק"מ.'
    assert "link or an image" in stub.requests[1]["messages"][-1]["content"]


def test_second_invalid_reply_raises_and_is_still_charged() -> None:
    stub = StubSDK(_completion("not json"), _completion(None))  # garbage, then an empty reply
    client = _client(stub)
    with pytest.raises(LLMOutputError, match="twice"):
        _ask(client)
    assert len(stub.requests) == 2  # exactly one retry
    assert client.total_cost_usd > 0  # the failed attempts were paid for


def test_paid_first_attempt_is_charged_when_the_retry_fails_to_connect() -> None:
    first = _completion("not json", prompt=1000, out=100)
    stub = StubSDK(
        first, openai.APIConnectionError(request=httpx.Request("POST", "https://x.test"))
    )
    client = _client(stub)
    with pytest.raises(LLMUnavailableError):
        _ask(client)
    assert len(stub.requests) == 2
    assert client.total_cost_usd == pytest.approx((1000 * 0.20 + 100 * 1.25) / 1e6)


def test_budget_refuses_calls_once_exceeded() -> None:
    stub = StubSDK(_completion(VALID, prompt=10_000, out=10_000), _completion(VALID))
    client = _client(stub, max_cost_usd=0.001)
    _ask(client)  # this call crosses the budget and still returns its paid-for answer
    assert client.total_cost_usd > 0.001
    with pytest.raises(BudgetExceededError, match="max_cost_usd"):
        _ask(client)
    assert len(stub.requests) == 1  # the refused call never reached the API


def test_model_without_price_is_refused_before_any_request() -> None:
    stub = StubSDK(_completion(VALID))
    with pytest.raises(LLMConfigError, match="No price"):
        _ask(_client(stub), model="gpt-unknown")
    assert stub.requests == []


def test_provider_errors_become_llm_unavailable() -> None:
    error = _status_error(openai.BadRequestError, 400, "Unsupported value: 'temperature'")
    with pytest.raises(LLMUnavailableError, match="HTTP 400.*temperature"):
        _ask(_client(StubSDK(error)))


def test_auth_error_message_is_not_echoed() -> None:
    error = _status_error(openai.AuthenticationError, 401, "Incorrect API key provided: sk-ab***yz")
    with pytest.raises(LLMUnavailableError) as raised:
        _ask(_client(StubSDK(error)))
    assert "sk-" not in str(raised.value)
    assert "OPENAI_API_KEY" in str(raised.value)


def test_missing_key_without_base_url_is_a_config_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    with pytest.raises(LLMConfigError, match="OPENAI_API_KEY is not set"):
        OpenAIClient(load_settings())


def test_local_server_needs_no_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_BASE_URL", "http://localhost:11434/v1")
    OpenAIClient(load_settings())  # constructs without a network call


def test_fake_client_replays_models_json_and_errors() -> None:
    fake = FakeLLMClient([Answer(answer="א", cars=[]), VALID, LLMOutputError("scripted")])
    assert fake.complete_json("s", [], Answer, model="m").parsed.answer == "א"
    assert fake.complete_json("s", [], Answer, model="m").parsed.cars == ["mg_s6"]
    with pytest.raises(LLMOutputError, match="scripted"):
        fake.complete_json("s", [], Answer, model="m")
    assert [call.model for call in fake.calls] == ["m", "m", "m"]
    assert fake.calls[0].schema is Answer


def test_fake_client_rejects_invalid_json_and_running_out() -> None:
    fake = FakeLLMClient(['{"answer": 1}'])
    with pytest.raises(LLMOutputError):
        fake.complete_json("s", [], Answer, model="m")
    with pytest.raises(AssertionError, match="no reply scripted"):
        fake.complete_json("s", [], Answer, model="m")
