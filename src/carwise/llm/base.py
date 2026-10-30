"""The one interface the pipeline uses to talk to a language model.

Why so small: the pipeline makes exactly two calls per turn (understand and
generate), and both want a validated object back, never free text. One method
that returns a parsed Pydantic model plus usage, cost and latency is all the
rest of the code needs, and a second provider (for example Bedrock) is then
one new class. No embed(): embeddings stay local (carwise.retrieval).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, Protocol, TypeVar

from pydantic import BaseModel

from carwise.config import Price

T = TypeVar("T", bound=BaseModel)
Message = dict[str, str]  # {"role": "user" | "assistant", "content": "..."}

TOKENS_PER_PRICE_UNIT = 1_000_000  # config prices are USD per 1M tokens


@dataclass(frozen=True)
class Usage:
    """Token counts, summed over every attempt of one call.

    `cached_tokens` is part of `input_tokens`, and `reasoning_tokens` is part of
    `output_tokens`; both are kept because they change the cost estimate and
    the CW-104 question of whether reasoning inflates it.
    """

    input_tokens: int = 0
    cached_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0

    def __add__(self, other: Usage) -> Usage:
        return Usage(
            self.input_tokens + other.input_tokens,
            self.cached_tokens + other.cached_tokens,
            self.output_tokens + other.output_tokens,
            self.reasoning_tokens + other.reasoning_tokens,
        )


class LLMError(RuntimeError):
    """Base for every LLM failure the pipeline may want to catch in one place.

    It carries what the failed call already spent, so a caller that recovers
    (the pipeline's fallbacks) still reports honest per-turn tokens and cost.
    """

    def __init__(
        self, message: str, *, usage: Usage | None = None, cost_usd: float = 0.0, attempts: int = 0
    ) -> None:
        super().__init__(message)
        self.usage = usage or Usage()
        self.cost_usd = cost_usd
        self.attempts = attempts


class LLMConfigError(LLMError):
    """Missing API key, or a model without a price in config."""


class LLMUnavailableError(LLMError):
    """Network, timeout or provider error that survived the configured retries."""


class LLMOutputError(LLMError):
    """The reply did not match the schema, even after the one corrective retry."""


class BudgetExceededError(LLMError):
    """The running cost passed llm.max_cost_usd; the run must stop."""


def cost_usd(usage: Usage, price: Price) -> float:
    """Cached input is billed at its own rate; reasoning is billed as output."""
    uncached = usage.input_tokens - usage.cached_tokens
    total = (
        uncached * price.input
        + usage.cached_tokens * price.cached_input
        + usage.output_tokens * price.output
    )
    return total / TOKENS_PER_PRICE_UNIT


@dataclass(frozen=True)
class LLMResult(Generic[T]):
    parsed: T
    usage: Usage
    cost_usd: float
    latency_ms: float
    model: str
    attempts: int = 1  # 2 when the corrective retry was needed


class LLMClient(Protocol):
    def complete_json(
        self, system: str, messages: list[Message], schema: type[T], *, model: str
    ) -> LLMResult[T]:
        """Send one structured-output request and return the validated object."""
        ...
