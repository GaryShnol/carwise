"""`python -m app eval`: record the understand outputs, or run an eval level.

Why recording is a separate, explicit step: it is the only part of the retrieval
eval that calls a model (and costs money), so it runs once on request, prints its
cost and stops at `eval.record_max_cost_usd`; every retrieval run after it is free.
"""

from __future__ import annotations

import argparse
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path

from carwise.config import Settings, load_settings
from carwise.llm.base import LLMClient, LLMConfigError
from carwise.llm.openai_client import OpenAIClient
from carwise.pipeline import Pipeline
from carwise.prompts import understand_system
from carwise.registry import load_registry
from carwise.retrieval.retriever import ChunkRetriever, open_retriever
from carwise.retrieval.store import IndexNotReadyError
from eval.questions import Negative, Question, load_negatives, load_questions
from eval.recording import (
    Recording,
    RecordingError,
    load_recording,
    record,
    save_recording,
    stale_reasons,
)
from eval.report import REPORTS_DIR, RetrievalReport, summary_rows, write_report
from eval.retrieval import by_category, grade, percentile, probe_result, replay

PipelineFactory = Callable[[LLMClient], Pipeline]


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--profile", default=argparse.SUPPRESS, help="dev or final")
    parser.add_argument("--level", choices=["retrieval", "answer"], default="retrieval")
    parser.add_argument("--runs", type=int, default=1, help="runs per question")
    parser.add_argument(
        "--record",
        action="store_true",
        help="record the understand outputs with the real model (costs money, needs a key)",
    )
    parser.add_argument("--out", type=Path, default=REPORTS_DIR, help="report directory")


def with_cost_cap(settings: Settings, cap: float) -> Settings:
    """The same settings with this run's cap in place of llm.max_cost_usd."""
    return settings.model_copy(
        update={"llm": settings.llm.model_copy(update={"max_cost_usd": cap})}
    )


def run(args: argparse.Namespace) -> int:
    settings = load_settings()
    profile_name = getattr(args, "profile", None)
    model = settings.profile(profile_name).understand_model
    registry = load_registry()
    try:
        retriever = open_retriever(settings)
    except IndexNotReadyError as error:
        print(error)
        return 1
    questions = load_questions().questions
    probes = load_negatives().probes
    system = understand_system(registry)

    def make_pipeline(llm: LLMClient) -> Pipeline:
        return Pipeline(settings, registry, retriever, llm, profile=profile_name)

    if args.record:
        return _record(settings, profile_name, [*questions, *probes], make_pipeline, system)
    if args.level == "answer":
        print("The answer level is not implemented yet (second half of CW-302).")
        return 2
    if args.runs < 1:
        print("--runs must be at least 1")
        return 2
    recording = load_recording()
    reasons = (
        ["no recording found"]
        if recording is None
        else stale_reasons(recording, [*questions, *probes], system=system, model=model)
    )
    if recording is None or reasons:
        print("The recorded understand outputs cannot be used:")
        print("\n".join(f"  - {reason}" for reason in reasons))
        print("Record them again: uv run --env-file .env python -m app eval --record")
        return 1
    print("loading the embedding model...", flush=True)
    started = time.perf_counter()
    retriever.warm_up()
    warm_up_s = time.perf_counter() - started
    report = retrieval_report(
        settings, retriever, make_pipeline, recording, questions, probes, args.runs
    )
    report = report.model_copy(update={"warm_up_s": round(warm_up_s, 2)})
    paths = write_report(report, args.out)
    print("\n".join(summary_rows(report.summary)))
    failed = [q for q in report.questions if not q.passed]
    for q in failed:
        print(f"FAIL {q.id}: {'; '.join(q.failures)}")
    unstable = [q.id for q in report.questions if not q.stable]
    if unstable:
        print(f"unstable across runs: {', '.join(unstable)}")
    print(
        f"retrieve p50 {report.latency_ms['p50']:.0f} ms, p95 {report.latency_ms['p95']:.0f} ms; "
        "cost $0 (no LLM calls)"
    )
    print("report: " + ", ".join(str(path) for path in paths))
    return 0


def retrieval_report(
    settings: Settings,
    retriever: ChunkRetriever,
    make_pipeline: PipelineFactory,
    recording: Recording,
    questions: Sequence[Question],
    probes: Sequence[Negative],
    runs: int,
) -> RetrievalReport:
    window = settings.llm.history_window
    results = []
    for question in questions:
        turns = recording.cases[question.id]
        replays = [replay(question, turns, make_pipeline, window) for _ in range(runs)]
        results.append(grade(question, replays, retriever))
    probe_results = [
        probe_result(probe, replay(probe, recording.cases[probe.id], make_pipeline, window))
        for probe in probes
    ]
    latencies = [ms for result in results for ms in result.retrieve_ms]
    embedder = settings.embeddings
    return RetrievalReport(
        created=datetime.now(UTC).isoformat(timespec="seconds"),
        embedder={
            "provider": embedder.provider,
            "model": embedder.model,
            "revision": embedder.revision,
        },
        retrieval=settings.retrieval.model_dump(),
        chunking=settings.chunking.model_dump(),
        recording={
            "model": recording.model,
            "understand_prompt": recording.understand_prompt,
            "recorded_at": recording.recorded_at,
            "cost_usd": recording.cost_usd,
        },
        runs=runs,
        warm_up_s=0.0,
        latency_ms={"p50": percentile(latencies, 50), "p95": percentile(latencies, 95)},
        summary=by_category(results),
        questions=results,
        probes=probe_results,
    )


def _record(
    settings: Settings,
    profile_name: str | None,
    cases: Sequence[Question | Negative],
    make_pipeline: PipelineFactory,
    system: str,
) -> int:
    cap = settings.eval.record_max_cost_usd
    capped = with_cost_cap(settings, cap)
    profile = capped.profile(profile_name)
    try:
        llm = OpenAIClient(capped, profile)
    except LLMConfigError as error:
        print(error)
        return 1
    print(f"recording {len(cases)} cases with {profile.understand_model} (cap ${cap:.2f})...")
    try:
        recording = record(
            cases,
            llm,
            make_pipeline,
            history_window=settings.llm.history_window,
            model=profile.understand_model,
            system=system,
        )
    except RecordingError as error:
        print(f"recording stopped, nothing written: {error} (spent ${llm.total_cost_usd:.4f})")
        return 1
    save_recording(recording)
    fallbacks = [
        case_id
        for case_id, turns in recording.cases.items()
        if any(turn.understanding is None for turn in turns)
    ]
    print(
        f"recorded {len(recording.cases)} cases: {recording.calls} calls, "
        f"tokens in {recording.tokens['input']} out {recording.tokens['output']}, "
        f"cost ${recording.cost_usd:.4f}"
    )
    if fallbacks:
        print(f"understand fell back (invalid output twice) in: {', '.join(fallbacks)}")
    return 0
