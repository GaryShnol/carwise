"""LLM judge for what deterministic checks cannot decide (CW-302).

Why a judge at all: "which is cheaper" is answered in free Hebrew prose, and a
correct pair of prices with the wrong conclusion ("the Aion HT is cheaper", seen
once in CW-203) passes every keyword check. Why only for a few questions: a judge
costs money, varies between runs and can be wrong itself, so it grades only the
criteria in eval/judge.yaml.

Why another model than the generator: grading with the generating model invites
self-preference. The judge model and its price are in config (eval.judge_model,
prices), verified on the official pricing page; its spend has its own cap.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict

from carwise.guardrails import escape_attribute, escape_text
from carwise.llm.base import LLMClient, LLMError
from carwise.schemas import Answer

CRITERIA_PATH = Path(__file__).with_name("judge.yaml")
PROMPT_VERSION = "v1"
SYSTEM = Path(__file__).with_name(f"judge.{PROMPT_VERSION}.txt").read_text(encoding="utf-8")


class Verdict(BaseModel):
    """The judge's structured output."""

    model_config = ConfigDict(extra="forbid")

    passed: bool
    reason: str


class Judged(BaseModel):
    model_config = ConfigDict(extra="forbid")

    passed: bool | None  # None: the judge could not be asked (error, cap reached)
    reason: str  # kept in eval/runs only: it may paraphrase the answer
    cost_usd: float
    tokens_in: int
    tokens_out: int


def load_criteria(path: Path = CRITERIA_PATH) -> dict[str, str]:
    raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    return {key: " ".join(str(value).split()) for key, value in raw["criteria"].items()}


def judge_input(criterion: str, user_turns: list[str], answer: Answer) -> str:
    """The judge's user message: the criterion, the conversation, the answer, the excerpts."""
    turns = "\n".join(f"{i}. {escape_text(turn)}" for i, turn in enumerate(user_turns, 1))
    excerpts = "\n".join(
        f'<excerpt car="{escape_attribute(hit.chunk.car_name)}" '
        f'section="{escape_attribute(hit.chunk.section)}">\n'
        f"{escape_text(hit.chunk.text)}\n</excerpt>"
        for hit in answer.retrieved
    )
    return (
        f"Criterion:\n{criterion}\n\n"
        f"User messages, in order:\n{turns}\n\n"
        f"The chatbot's final answer:\n<answer>\n{escape_text(answer.text)}\n</answer>\n\n"
        f"Excerpts the chatbot was given:\n{excerpts}"
    )


def judge(
    client: LLMClient, model: str, criterion: str, user_turns: list[str], answer: Answer
) -> Judged:
    message = judge_input(criterion, user_turns, answer)
    try:
        result = client.complete_json(
            SYSTEM, [{"role": "user", "content": message}], Verdict, model=model
        )
    except LLMError as error:  # budget reached, provider down or unusable output
        return Judged(
            passed=None, reason=f"not judged: {error}", cost_usd=0.0, tokens_in=0, tokens_out=0
        )
    return Judged(
        passed=result.parsed.passed,
        reason=result.parsed.reason,
        cost_usd=result.cost_usd,
        tokens_in=result.usage.input_tokens,
        tokens_out=result.usage.output_tokens,
    )
