"""`LLMClient` over the official OpenAI SDK, Chat Completions API.

Why Chat Completions and not the newer Responses API: it is the API every
OpenAI-compatible server implements (Ollama, vLLM), so a configurable
`base_url` really does switch providers. Why a strict JSON schema *and*
Pydantic validation: strict mode makes OpenAI models follow the schema, but a
local server may ignore it, and the pipeline must never act on a malformed
object. Network retries and timeouts are delegated to the SDK (from config);
the one corrective retry for a bad reply is ours, because only we know the
validation error to send back.
"""

from __future__ import annotations

import os
import time
from typing import Any, cast

import openai
from openai import OpenAI
from openai.types.chat import ChatCompletion, ChatCompletionMessageParam
from openai.types.shared_params import ResponseFormatJSONSchema
from pydantic import ValidationError

from carwise.config import Price, ProfileConfig, Settings
from carwise.llm.base import (
    BudgetExceededError,
    LLMConfigError,
    LLMOutputError,
    LLMResult,
    LLMUnavailableError,
    Message,
    T,
    Usage,
    cost_usd,
)

# A local OpenAI-compatible server needs some key string but ignores its value.
LOCAL_SERVER_KEY = "not-needed"
# Enough of the validation error for the model to fix its reply; keeps the retry cheap.
RETRY_ERROR_CHARS = 1000
RETRY_INSTRUCTION = (
    "Your previous reply did not match the required JSON schema. "
    "Reply again with only a JSON object that matches the schema. Validation error:\n{error}"
)
# Their messages can echo part of the API key, so only the error type is reported.
_AUTH_ERRORS = (openai.AuthenticationError, openai.PermissionDeniedError)


def response_format(schema: type[T]) -> ResponseFormatJSONSchema:
    """Strict JSON schema for a Pydantic model, via the SDK's public helper.

    pydantic_function_tool applies OpenAI's strict-mode rules (all fields
    required, no extra keys) and fails early if a model cannot be made strict.
    """
    strict = openai.pydantic_function_tool(schema)["function"]
    return {
        "type": "json_schema",
        "json_schema": {
            "name": strict["name"],
            "strict": True,
            "schema": dict(strict.get("parameters") or {}),
        },
    }


def _usage(response: ChatCompletion) -> Usage:
    usage = response.usage
    if usage is None:  # some compatible servers omit it; cost is then unknown, counted as 0
        return Usage()
    prompt_details = usage.prompt_tokens_details
    completion_details = usage.completion_tokens_details
    return Usage(
        input_tokens=usage.prompt_tokens,
        cached_tokens=(prompt_details.cached_tokens or 0) if prompt_details else 0,
        output_tokens=usage.completion_tokens,
        reasoning_tokens=(completion_details.reasoning_tokens or 0) if completion_details else 0,
    )


def _describe(error: openai.APIError) -> str:
    status = getattr(error, "status_code", None)
    label = f"{type(error).__name__}" + (f" (HTTP {status})" if status else "")
    if isinstance(error, _AUTH_ERRORS):
        return f"{label}: check OPENAI_API_KEY"
    return f"{label}: {error.message}"


class OpenAIClient:
    """Structured-output client with cost accounting and a hard budget.

    `total_cost_usd` accumulates over the client's lifetime (one chat session
    or one eval run). Once it reaches llm.max_cost_usd every further call is
    refused, so the overrun is bounded by a single call.
    """

    def __init__(
        self,
        settings: Settings,
        profile: ProfileConfig | None = None,
        *,
        sdk: OpenAI | None = None,
    ) -> None:
        self._config = settings.llm
        self._prices = settings.prices
        self.total_cost_usd = 0.0
        self._sdk = sdk or self._make_sdk(settings, profile or settings.profile())

    @staticmethod
    def _make_sdk(settings: Settings, profile: ProfileConfig) -> OpenAI:
        base_url = os.environ.get("OPENAI_BASE_URL") or profile.base_url
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            if base_url is None:
                raise LLMConfigError(
                    "OPENAI_API_KEY is not set. Export it, or run with "
                    "`uv run --env-file .env ...` (see .env.example)."
                )
            api_key = LOCAL_SERVER_KEY
        return OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=settings.llm.timeout_s,
            max_retries=settings.llm.retries,
        )

    def _price(self, model: str) -> Price:
        if model not in self._prices:
            raise LLMConfigError(
                f"No price for model '{model}' in config/settings.yaml; add one "
                "(zeros for a local model) so cost tracking stays honest."
            )
        return self._prices[model]

    def _sampling(self) -> dict[str, Any]:
        """Only the controls set in config are sent; the spike decides which (ADR 0001)."""
        controls = {
            "temperature": self._config.temperature,
            "reasoning_effort": self._config.reasoning_effort,
            "seed": self._config.seed,
        }
        return {name: value for name, value in controls.items() if value is not None}

    def _call(self, conversation: list[Message], schema: type[T], model: str) -> tuple[str, Usage]:
        try:
            response = self._sdk.chat.completions.create(
                model=model,
                messages=cast(list[ChatCompletionMessageParam], conversation),
                response_format=response_format(schema),
                **self._sampling(),
            )
        except openai.APIError as error:
            raise LLMUnavailableError(_describe(error)) from error
        content = response.choices[0].message.content if response.choices else None
        return content or "", _usage(response)

    def complete_json(
        self, system: str, messages: list[Message], schema: type[T], *, model: str
    ) -> LLMResult[T]:
        price = self._price(model)
        if self.total_cost_usd >= self._config.max_cost_usd:
            raise BudgetExceededError(
                f"Spent ${self.total_cost_usd:.4f} of the ${self._config.max_cost_usd:.2f} "
                "budget (llm.max_cost_usd); stopping."
            )
        conversation: list[Message] = [{"role": "system", "content": system}, *messages]
        usage = Usage()
        started = time.perf_counter()
        for attempt in (1, 2):
            try:
                content, call_usage = self._call(conversation, schema, model)
            except LLMUnavailableError as error:
                # A failed retry must not hide what the first attempt already cost.
                spent = cost_usd(usage, price)
                self.total_cost_usd += spent
                raise LLMUnavailableError(
                    str(error), usage=usage, cost_usd=spent, attempts=attempt - 1
                ) from error.__cause__
            usage += call_usage
            try:
                parsed = schema.model_validate_json(content)
            except ValidationError as error:
                if attempt == 2:
                    spent = cost_usd(usage, price)
                    self.total_cost_usd += spent
                    raise LLMOutputError(
                        f"{model} returned invalid {schema.__name__} twice: "
                        f"{error.error_count()} validation error(s)",
                        usage=usage,
                        cost_usd=spent,
                        attempts=attempt,
                    ) from error
                retry = RETRY_INSTRUCTION.format(error=str(error)[:RETRY_ERROR_CHARS])
                conversation = [
                    *conversation,
                    {"role": "assistant", "content": content},
                    {"role": "user", "content": retry},
                ]
                continue
            cost = cost_usd(usage, price)
            self.total_cost_usd += cost
            return LLMResult(
                parsed=parsed,
                usage=usage,
                cost_usd=cost,
                latency_ms=(time.perf_counter() - started) * 1000,
                model=model,
                attempts=attempt,
            )
        raise AssertionError("unreachable: the loop returns or raises")
