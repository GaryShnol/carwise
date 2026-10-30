"""Recorded understand outputs, so the retrieval eval is free and repeatable.

Why record: the understand call (LLM call 1) decides the intent, the cars and the
rewritten question, and retrieval depends on all three. Replaying the model's real
outputs grades retrieval on what the system actually does, with no API key, no cost
and no drift between runs, so CW-305 (embedders) and CW-303 (parameters) compare on
exactly the same plans. The replay goes through the real `Pipeline.ask`, so the
gates, the car matching and the retrieval mode are the production code, not a copy.

Why a stale recording is refused: a changed question, understand prompt, car
registry (it is inlined in the prompt) or model would grade retrieval against plans
the current system would not make.

What is stored: the structured understand output per turn, which holds only our own
questions rewritten and the preference values taken from them. No answer text: the
earlier turns of a follow-up are answered for real while recording (their answers are
the history of the next turn), but those answers are never written.
"""

from __future__ import annotations

import hashlib
import json
from collections import deque
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol, TypeVar

from pydantic import BaseModel, ConfigDict

from carwise.llm.base import (
    LLMClient,
    LLMOutputError,
    LLMResult,
    LLMUnavailableError,
    Message,
    T,
    Usage,
)
from carwise.pipeline import Pipeline
from carwise.preferences import Session
from carwise.prompts import PROMPT_VERSIONS
from carwise.schemas import Answer, RefusalReason, Understanding

RECORDING_PATH = Path(__file__).parent / "recorded" / "understand.json"
FORMAT_VERSION = 1


class Case(Protocol):
    """Anything with an id and user turns: an eval question or a negative probe."""

    @property
    def id(self) -> str: ...

    @property
    def turns(self) -> list[str]: ...


C = TypeVar("C", bound=Case)


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class RecordedTurn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message_sha256: str
    understanding: Understanding | None  # None: invalid output twice, the pipeline fell back


class Recording(BaseModel):
    model_config = ConfigDict(extra="forbid")

    format: int = FORMAT_VERSION
    model: str
    understand_prompt: str  # the prompt version, as telemetry records it
    understand_system_sha256: str  # prompt text with the registry inlined
    recorded_at: str
    calls: int
    tokens: dict[str, int]
    cost_usd: float
    cases: dict[str, list[RecordedTurn]]


def stale_reasons(
    recording: Recording, cases: Sequence[Case], *, system: str, model: str
) -> list[str]:
    """Why this recording cannot stand in for the current understand step (empty: it can)."""
    reasons = []
    if recording.format != FORMAT_VERSION:
        reasons.append(f"format {recording.format}, expected {FORMAT_VERSION}")
    if recording.model != model:
        reasons.append(f"recorded with {recording.model}, the profile uses {model}")
    if recording.understand_prompt != PROMPT_VERSIONS["understand"]:
        reasons.append(
            f"understand prompt {recording.understand_prompt}, "
            f"current {PROMPT_VERSIONS['understand']}"
        )
    if recording.understand_system_sha256 != sha256(system):
        reasons.append("the understand prompt text or the car registry changed")
    for case in cases:
        turns = recording.cases.get(case.id)
        if turns is None:
            reasons.append(f"{case.id}: not recorded")
        elif [turn.message_sha256 for turn in turns] != [sha256(t) for t in case.turns]:
            reasons.append(f"{case.id}: the turns changed")
    return reasons


def missing(recording: Recording, cases: Sequence[C]) -> list[C]:
    """Cases the recording lacks, or whose turns changed since they were recorded."""
    return [
        case
        for case in cases
        if [turn.message_sha256 for turn in recording.cases.get(case.id, [])]
        != [sha256(t) for t in case.turns]
    ]


def merge(old: Recording, new: Recording) -> Recording:
    """The old recording plus newly recorded cases, with the spend of both.

    Only valid when both come from the same model and understand prompt: a
    recording mixing two would grade some plans against another system.
    """
    if (old.model, old.understand_prompt, old.understand_system_sha256) != (
        new.model,
        new.understand_prompt,
        new.understand_system_sha256,
    ):
        raise RecordingError("cannot merge recordings of different models or prompts")
    return new.model_copy(
        update={
            "calls": old.calls + new.calls,
            "tokens": {k: old.tokens.get(k, 0) + v for k, v in new.tokens.items()},
            "cost_usd": round(old.cost_usd + new.cost_usd, 6),
            "cases": {**old.cases, **new.cases},
        }
    )


def load_recording(path: Path = RECORDING_PATH) -> Recording | None:
    if not path.exists():
        return None
    return Recording.model_validate_json(path.read_text(encoding="utf-8"))


def save_recording(recording: Recording, path: Path = RECORDING_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(recording.model_dump(mode="json"), ensure_ascii=False, indent=1)
    path.write_text(text + "\n", encoding="utf-8", newline="\n")


class GenerationSkippedError(LLMUnavailableError):
    """Raised in place of a generate call: the retrieval eval stops before generation.

    A subclass of LLMUnavailableError, so the pipeline takes its ordinary "provider
    unavailable" path after retrieval, and the answer still carries the plan and hits.
    """


class ReplayClient:
    """Answers understand calls from a recording and refuses every generate call."""

    def __init__(self, turns: list[RecordedTurn]) -> None:
        self._turns = deque(turns)
        self.generate_requested = False  # set when the turn reached generation

    def complete_json(
        self, system: str, messages: list[Message], schema: type[T], *, model: str
    ) -> LLMResult[T]:
        if schema is not Understanding:
            self.generate_requested = True
            raise GenerationSkippedError("the retrieval eval does not generate")
        if not self._turns:
            raise AssertionError("ReplayClient: more understand calls than recorded turns")
        recorded = self._turns.popleft().understanding
        if recorded is None:
            raise LLMOutputError("recorded: the understand output was invalid twice")
        parsed = schema.model_validate(recorded.model_dump())
        return LLMResult(parsed=parsed, usage=Usage(), cost_usd=0.0, latency_ms=0.0, model=model)


class RecordingClient:
    """Passes calls to the real client and keeps every understand output.

    Generation runs for the earlier turns of a case (the next turn's history needs
    their answers) and is skipped on the last turn, which only needs its plan.
    """

    def __init__(self, inner: LLMClient) -> None:
        self._inner = inner
        self.skip_generation = False
        self.understood: list[Understanding | None] = []
        self.usage = Usage()
        self.cost_usd = 0.0
        self.calls = 0

    def complete_json(
        self, system: str, messages: list[Message], schema: type[T], *, model: str
    ) -> LLMResult[T]:
        if schema is not Understanding and self.skip_generation:
            raise GenerationSkippedError("recording stops before the last generation")
        try:
            result = self._inner.complete_json(system, messages, schema, model=model)
        except LLMOutputError as error:
            self._spend(error.usage, error.cost_usd, error.attempts)
            if schema is Understanding:
                self.understood.append(None)
            raise
        self._spend(result.usage, result.cost_usd, result.attempts)
        if isinstance(result.parsed, Understanding):
            self.understood.append(result.parsed)
        return result

    def _spend(self, usage: Usage, cost: float, attempts: int) -> None:
        self.usage += usage
        self.cost_usd += cost
        self.calls += attempts


class RecordingError(RuntimeError):
    """A case could not be recorded faithfully (provider down, budget reached)."""


def record(
    cases: Sequence[Case],
    inner: LLMClient,
    make_pipeline: Callable[[LLMClient], Pipeline],
    *,
    history_window: int,
    model: str,
    system: str,
) -> Recording:
    """Run every case through the real pipeline once and keep its understand outputs."""
    client = RecordingClient(inner)
    pipeline = make_pipeline(client)
    recorded: dict[str, list[RecordedTurn]] = {}
    for case in cases:
        session = Session(history_window=history_window)
        turns = []
        for index, message in enumerate(case.turns):
            client.skip_generation = index == len(case.turns) - 1
            before = len(client.understood)
            answer = pipeline.answer(message, session)
            _check_turn(case.id, answer, len(client.understood) - before, client.skip_generation)
            understanding = client.understood[-1]
            turns.append(RecordedTurn(message_sha256=sha256(message), understanding=understanding))
        recorded[case.id] = turns
    return Recording(
        model=model,
        understand_prompt=PROMPT_VERSIONS["understand"],
        understand_system_sha256=sha256(system),
        recorded_at=datetime.now(UTC).isoformat(timespec="seconds"),
        calls=client.calls,
        tokens={
            "input": client.usage.input_tokens,
            "cached": client.usage.cached_tokens,
            "output": client.usage.output_tokens,
        },
        cost_usd=round(client.cost_usd, 6),
        cases=recorded,
    )


def _check_turn(case_id: str, answer: Answer, understand_calls: int, last: bool) -> None:
    if answer.refusal is RefusalReason.BUDGET_EXCEEDED:
        raise RecordingError(f"{case_id}: the recording budget was reached")
    if understand_calls != 1:
        # A provider error on the understand call: nothing faithful to record.
        raise RecordingError(f"{case_id}: the understand call failed ({', '.join(answer.flags)})")
    if not last and answer.refusal is RefusalReason.LLM_ERROR:
        # An earlier turn's answer is the next turn's history; an error text would skew it.
        raise RecordingError(f"{case_id}: an earlier turn failed ({', '.join(answer.flags)})")
