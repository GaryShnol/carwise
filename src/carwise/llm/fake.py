"""Scripted `LLMClient` for tests: no network, no key, no cost.

Why scripted replies and not a mock: pipeline tests (CW-105 onward) need to
say "the understand call returns this, the generate call returns that" and
then inspect what was sent. A reply may be a model instance, a JSON string
(validated against the requested schema, as the real client does), or an
exception to raise.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from pydantic import BaseModel

from carwise.llm.base import LLMOutputError, LLMResult, Message, T, Usage

Reply = BaseModel | str | Exception


@dataclass(frozen=True)
class RecordedCall:
    system: str
    messages: list[Message]
    schema: type[BaseModel]
    model: str


class FakeLLMClient:
    def __init__(self, replies: list[Reply] | None = None) -> None:
        self._replies: deque[Reply] = deque(replies or [])
        self.calls: list[RecordedCall] = []

    def add(self, *replies: Reply) -> None:
        self._replies.extend(replies)

    def complete_json(
        self, system: str, messages: list[Message], schema: type[T], *, model: str
    ) -> LLMResult[T]:
        self.calls.append(RecordedCall(system, list(messages), schema, model))
        if not self._replies:
            raise AssertionError(f"FakeLLMClient: no reply scripted for call {len(self.calls)}")
        reply = self._replies.popleft()
        if isinstance(reply, Exception):
            raise reply
        if isinstance(reply, str):
            try:
                parsed = schema.model_validate_json(reply)
            except ValueError as error:
                raise LLMOutputError(f"scripted reply is not a valid {schema.__name__}") from error
        elif isinstance(reply, schema):
            parsed = reply
        else:
            raise AssertionError(
                f"FakeLLMClient: scripted {type(reply).__name__}, call asked for {schema.__name__}"
            )
        return LLMResult(parsed=parsed, usage=Usage(), cost_usd=0.0, latency_ms=0.0, model=model)
