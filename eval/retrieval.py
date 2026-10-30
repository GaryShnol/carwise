"""Retrieval level of the eval: does each question's plan reach the right chunks?

No LLM and no cost: the understand outputs are replayed from the recording, and
every turn runs through the real `Pipeline.ask` up to the generate call. What is
graded is what the pipeline did (gates, retrieval mode, retrieved chunks), so the
numbers move only when retrieval code, the index or the parameters move.

Why two ranks per expected source: `rank` is its place in what the pipeline
retrieved (what generation would see), and `car_rank` is its place among all of
that car's chunks for the same query. A miss with `car_rank` 6 and `top_k` 5 is a
parameter problem for CW-303; a miss with `car_rank` 20 is an embedding problem for
CW-305.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence

from pydantic import BaseModel, ConfigDict

from carwise.llm.base import LLMClient
from carwise.pipeline import Pipeline
from carwise.preferences import Session
from carwise.retrieval.retriever import ChunkRetriever
from carwise.schemas import Answer, RefusalReason, RetrievedChunk
from eval.questions import Behavior, Category, Negative, ProbePurpose, Question, Source
from eval.recording import Case, RecordedTurn, ReplayClient

CAR_RANK_DEPTH = 10_000  # "every chunk of the car": the corpus has 75 in total
REFUSALS = {RefusalReason.UNKNOWN_CAR: "refusal", RefusalReason.LOW_RELEVANCE: "refusal"}


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Hit(_Model):
    chunk_id: str
    score: float


class SourceResult(_Model):
    car: str
    section: str
    hit: bool
    rank: int | None  # 1-based place among the retrieved chunks
    car_rank: int | None  # 1-based place among all chunks of the car for the same query


class QuestionResult(_Model):
    id: str
    category: Category
    expected: Behavior
    behavior: str  # answer | refusal | out_of_scope | error:<refusal reason>
    intent: str | None
    cars: list[str]
    not_covered: list[str]
    refusal: str | None
    sources: list[SourceResult]
    sources_any: list[SourceResult]
    reciprocal_rank: float | None  # mean over expected sources; None without sources
    best_score: float | None
    retrieved: list[Hit]
    passed: bool
    failures: list[str]
    retrieve_ms: list[float]  # one per run
    stable: bool  # the same chunks and scores in every run


class ProbeResult(_Model):
    id: str
    purpose: ProbePurpose
    behavior: str
    passed: bool | None  # behavior probes: sent to the out-of-scope reply; threshold: not graded
    intent: str | None
    refusal: str | None
    best_score: float | None
    retrieved: list[Hit]


class CategorySummary(_Model):
    category: str
    questions: int
    passed: int
    sources: int  # expected sources; a sources_any group counts as one
    sources_hit: int
    mrr: float | None


class ScoreSpread(_Model):
    """Best retrieval scores of one group; quartiles are nearest-rank, so observed values."""

    n: int
    min: float | None
    q1: float | None
    median: float | None
    q3: float | None
    max: float | None


class Replayed(_Model):
    answer: Answer
    reached_generation: bool


def replay(
    case: Case,
    turns: list[RecordedTurn],
    make_pipeline: Callable[[LLMClient], Pipeline],
    history_window: int,
) -> Replayed:
    """Every turn of the case through the pipeline; the last turn's answer is graded."""
    client = ReplayClient(turns)
    pipeline = make_pipeline(client)
    session = Session(history_window=history_window)
    answer: Answer | None = None
    for message in case.turns:
        client.generate_requested = False
        answer = pipeline.answer(message, session)
    if answer is None:
        raise ValueError(f"{case.id}: a case needs at least one turn")
    return Replayed(answer=answer, reached_generation=client.generate_requested)


def behavior_of(replayed: Replayed) -> str:
    """What the user would get: an answer, a gate refusal, or the out-of-scope reply."""
    if replayed.reached_generation:
        return Behavior.ANSWER.value
    refusal = replayed.answer.refusal
    if refusal in REFUSALS:
        return REFUSALS[refusal]
    if refusal is RefusalReason.OUT_OF_SCOPE:
        return Behavior.OUT_OF_SCOPE.value
    return f"error:{refusal.value if refusal else 'none'}"


def _matches(source: Source, hit: RetrievedChunk) -> bool:
    return hit.chunk.car == source.car and source.section in hit.chunk.section


def _first_rank(source: Source, hits: Sequence[RetrievedChunk]) -> int | None:
    return next((rank for rank, hit in enumerate(hits, 1) if _matches(source, hit)), None)


def _source_result(source: Source, answer: Answer, retriever: ChunkRetriever) -> SourceResult:
    rank = _first_rank(source, answer.retrieved)
    car_rank = None
    if answer.standalone_question:
        ranked = retriever.search(answer.standalone_question, [source.car], CAR_RANK_DEPTH)
        car_rank = _first_rank(source, ranked)
    return SourceResult(
        car=source.car, section=source.section, hit=rank is not None, rank=rank, car_rank=car_rank
    )


def _reciprocal(result: SourceResult) -> float:
    return 1.0 / result.rank if result.rank else 0.0


def _hits(answer: Answer) -> list[Hit]:
    return [Hit(chunk_id=hit.chunk.chunk_id, score=hit.score) for hit in answer.retrieved]


def _best_score(answer: Answer) -> float | None:
    return max((hit.score for hit in answer.retrieved), default=None)


def grade(
    question: Question, runs: Sequence[Replayed], retriever: ChunkRetriever
) -> QuestionResult:
    """Grade the first run; the others only show whether retrieval was the same each time."""
    first = runs[0]
    answer = first.answer
    behavior = behavior_of(first)
    expect = question.expect
    sources = [_source_result(s, answer, retriever) for s in expect.sources]
    alternatives = [_source_result(s, answer, retriever) for s in expect.sources_any]

    failures = []
    if behavior != expect.behavior.value:
        failures.append(f"behavior {behavior}, expected {expect.behavior.value}")
    failures += [
        f"missed {s.car} / {s.section} (car rank {s.car_rank or '-'})" for s in sources if not s.hit
    ]
    if alternatives and not any(s.hit for s in alternatives):
        ranks = ", ".join(f"{s.car} / {s.section} {s.car_rank or '-'}" for s in alternatives)
        failures.append(f"missed every sources_any alternative (car ranks: {ranks})")

    slots = [_reciprocal(s) for s in sources]
    if alternatives:
        slots.append(max(_reciprocal(s) for s in alternatives))
    signature = [_hits(run.answer) for run in runs]
    return QuestionResult(
        id=question.id,
        category=question.category,
        expected=expect.behavior,
        behavior=behavior,
        intent=answer.intent.value if answer.intent else None,
        cars=answer.cars,
        not_covered=answer.not_covered,
        refusal=answer.refusal.value if answer.refusal else None,
        sources=sources,
        sources_any=alternatives,
        reciprocal_rank=sum(slots) / len(slots) if slots else None,
        best_score=_best_score(answer),
        retrieved=signature[0],
        passed=not failures,
        failures=failures,
        retrieve_ms=[run.answer.latency_ms.get("retrieve", 0.0) for run in runs],
        stable=all(item == signature[0] for item in signature),
    )


def probe_result(probe: Negative, replayed: Replayed) -> ProbeResult:
    answer = replayed.answer
    behavior = behavior_of(replayed)
    behavior_probe = probe.purpose is ProbePurpose.BEHAVIOR
    return ProbeResult(
        id=probe.id,
        purpose=probe.purpose,
        behavior=behavior,
        passed=behavior == Behavior.OUT_OF_SCOPE.value if behavior_probe else None,
        intent=answer.intent.value if answer.intent else None,
        refusal=answer.refusal.value if answer.refusal else None,
        best_score=_best_score(answer),
        retrieved=_hits(answer),
    )


def summarize(label: str, results: Sequence[QuestionResult]) -> CategorySummary:
    sources = sum(len(r.sources) + (1 if r.sources_any else 0) for r in results)
    hit = sum(
        sum(s.hit for s in r.sources) + (1 if any(s.hit for s in r.sources_any) else 0)
        for r in results
    )
    ranks = [r.reciprocal_rank for r in results if r.reciprocal_rank is not None]
    return CategorySummary(
        category=label,
        questions=len(results),
        passed=sum(r.passed for r in results),
        sources=sources,
        sources_hit=hit,
        mrr=sum(ranks) / len(ranks) if ranks else None,
    )


def by_category(results: Sequence[QuestionResult]) -> list[CategorySummary]:
    """One row per category in the question set's order, then the total."""
    rows = [
        summarize(category.value, [r for r in results if r.category is category])
        for category in Category
        if any(r.category is category for r in results)
    ]
    return [*rows, summarize("total", results)]


def percentile(values: Sequence[float], pct: float) -> float | None:
    """Nearest-rank percentile: an observed value, never an interpolated one."""
    if not values:
        return None
    ordered = sorted(values)
    index = max(math.ceil(pct / 100 * len(ordered)) - 1, 0)
    return ordered[index]


def spread(values: Sequence[float]) -> ScoreSpread:
    def at(pct: float) -> float | None:
        value = percentile(values, pct)
        return None if value is None else round(value, 4)

    return ScoreSpread(n=len(values), min=at(0), q1=at(25), median=at(50), q3=at(75), max=at(100))


def score_spreads(
    results: Sequence[QuestionResult], probes: Sequence[ProbeResult]
) -> dict[str, ScoreSpread]:
    """Answerable questions against threshold probes: the two samples CW-303 separates.

    Behavior probes are left out: they never reach retrieval, so they have no score.
    """
    answerable = [
        r.best_score for r in results if r.expected is Behavior.ANSWER and r.best_score is not None
    ]
    negatives = [
        p.best_score
        for p in probes
        if p.purpose is ProbePurpose.THRESHOLD and p.best_score is not None
    ]
    return {"answerable": spread(answerable), "threshold_probes": spread(negatives)}
