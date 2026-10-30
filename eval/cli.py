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
from carwise.prompts import PROMPT_VERSIONS, understand_system
from carwise.registry import Registry, load_registry
from carwise.retrieval.retriever import ChunkRetriever, Retriever, open_retriever
from carwise.retrieval.store import IndexNotReadyError
from eval import candidates
from eval.answer_report import RUNS_DIR, run_answer_eval
from eval.answer_report import markdown as answer_markdown
from eval.answer_report import write as write_answer_report
from eval.questions import Negative, Question, load_negatives, load_questions
from eval.recording import (
    Recording,
    RecordingError,
    load_recording,
    merge,
    missing,
    record,
    save_recording,
    stale_reasons,
)
from eval.report import (
    REPORTS_DIR,
    RetrievalReport,
    comparison_markdown,
    load_report,
    spread_rows,
    summary_rows,
    write_report,
)
from eval.retrieval import (
    by_category,
    grade,
    percentile,
    probe_result,
    replay,
    score_spreads,
)

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
    parser.add_argument(
        "--record-missing",
        action="store_true",
        help="record only the cases the recording lacks (same model and prompt), and merge",
    )
    parser.add_argument(
        "--holdout",
        action="store_true",
        help="run only the hold-out questions written after CW-303 (default: the tuning set)",
    )
    parser.add_argument(
        "--generate-prompt",
        help="answer level: generate prompt version to use (default: the configured one)",
    )
    parser.add_argument("--out", type=Path, default=REPORTS_DIR, help="report directory")
    parser.add_argument(
        "--candidate",
        help="CW-305: run the retrieval level with a candidate from eval/candidates.yaml",
    )
    parser.add_argument(
        "--compare",
        action="store_true",
        help="CW-305: write the side-by-side table of the candidate reports",
    )


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
    if args.compare:
        return _compare(args.out)
    prepared: candidates.Prepared | None = None
    if args.candidate:
        if args.candidate not in candidates.load_candidates():
            print(f"unknown candidate {args.candidate!r}; see eval/candidates.yaml")
            return 2
        print(f"preparing candidate {args.candidate} (model load, fresh index)...", flush=True)
        prepared = candidates.prepare(settings, registry, args.candidate)
        settings = prepared.settings
    try:
        retriever = prepared.retriever if prepared else open_retriever(settings)
    except IndexNotReadyError as error:
        print(error)
        return 1
    every_question = load_questions().questions
    probes = load_negatives().probes
    # The hold-out set is reported on its own, never mixed into the tuning numbers.
    questions = [q for q in every_question if q.holdout == args.holdout]
    system = understand_system(registry)

    def make_pipeline(llm: LLMClient) -> Pipeline:
        return Pipeline(settings, registry, retriever, llm, profile=profile_name)

    if args.record or args.record_missing:
        cases: list[Question | Negative] = [*every_question, *probes]
        return _record(settings, profile_name, cases, make_pipeline, system, args.record_missing)
    if args.runs < 1:
        print("--runs must be at least 1")
        return 2
    if args.level == "answer":
        return _answer(args, settings, registry, retriever, profile_name, questions)
    if args.runs < 1:
        print("--runs must be at least 1")
        return 2
    recording = load_recording()
    reasons = (
        ["no recording found"]
        if recording is None
        else stale_reasons(recording, [*every_question, *probes], system=system, model=model)
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
        settings,
        retriever,
        make_pipeline,
        recording,
        questions,
        [] if args.holdout else probes,
        args.runs,
    )
    report = report.model_copy(update={"warm_up_s": round(warm_up_s, 2)})
    if prepared:  # the model was loaded (and timed) while preparing the candidate
        resources = {**prepared.resources, "peak_rss_mb": candidates.peak_memory_mb()}
        load_s = prepared.resources["model_load_s"]
        report = report.model_copy(
            update={"warm_up_s": float(load_s or 0.0), "resources": resources}
        )
    paths = write_report(report, args.out)
    print("\n".join(summary_rows(report.summary)))
    failed = [q for q in report.questions if not q.passed]
    for q in failed:
        print(f"FAIL {q.id}: {'; '.join(q.failures)}")
    for p in report.probes:
        if p.passed is False:
            print(f"FAIL probe {p.id}: behavior {p.behavior}, expected out_of_scope")
        if p.passed is None and p.best_score is None:
            print(f"threshold probe {p.id} gave no score (behavior {p.behavior})")
    print("\n".join(spread_rows(report.scores)))
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
        retrieval=settings.retrieval,
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
        scores=score_spreads(results, probe_results),
        questions=results,
        probes=probe_results,
    )


def _record(
    settings: Settings,
    profile_name: str | None,
    cases: Sequence[Question | Negative],
    make_pipeline: PipelineFactory,
    system: str,
    only_missing: bool = False,
) -> int:
    cap = settings.eval.record_max_cost_usd
    capped = with_cost_cap(settings, cap)
    profile = capped.profile(profile_name)
    try:
        llm = OpenAIClient(capped, profile)
    except LLMConfigError as error:
        print(error)
        return 1
    existing = load_recording() if only_missing else None
    if only_missing:
        if existing is None:
            print("no recording to add to; run --record first")
            return 1
        reasons = stale_reasons(existing, [], system=system, model=profile.understand_model)
        if reasons:
            print("the recording was made with another model or prompt; run --record instead:")
            print("\n".join(f"  - {reason}" for reason in reasons))
            return 1
        cases = missing(existing, cases)
        if not cases:
            print("nothing to record: every case is in the recording")
            return 0
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
    added = recording
    if existing is not None:
        recording = merge(existing, recording)
    save_recording(recording)
    print(
        f"this run: {len(added.cases)} cases, {added.calls} calls, "
        f"tokens in {added.tokens['input']} out {added.tokens['output']}, "
        f"cost ${added.cost_usd:.4f}"
    )
    fallbacks = [
        case_id
        for case_id, turns in recording.cases.items()
        if any(turn.understanding is None for turn in turns)
    ]
    print(
        f"recording now holds {len(recording.cases)} cases: {recording.calls} calls, "
        f"tokens in {recording.tokens['input']} out {recording.tokens['output']}, "
        f"cost ${recording.cost_usd:.4f}"
    )
    if fallbacks:
        print(f"understand fell back (invalid output twice) in: {', '.join(fallbacks)}")
    return 0


def _compare(out_dir: Path) -> int:
    """Side-by-side table of every candidate that has a report, in candidates.yaml order."""
    reports = {}
    for name in candidates.load_candidates():
        path = out_dir / f"retrieval-{name}.json"
        if path.exists():
            reports[name] = load_report(path)
    if not reports:
        print("no candidate reports yet; run `python -m app eval --candidate NAME` first")
        return 1
    path = out_dir / "candidates.md"
    path.write_text(comparison_markdown(reports), encoding="utf-8", newline="\n")
    print(f"compared {', '.join(reports)}: {path}")
    return 0


def _answer(
    args: argparse.Namespace,
    settings: Settings,
    registry: Registry,
    retriever: Retriever,
    profile_name: str | None,
    questions: Sequence[Question],
) -> int:
    """The answer level: real calls on the chosen profile, each with its own cost cap."""
    answer_cap = settings.eval.answer_max_cost_usd
    judge_cap = settings.eval.judge_max_cost_usd
    answer_settings = with_cost_cap(settings, answer_cap)
    profile = answer_settings.profile(profile_name)
    name = profile_name or settings.default_profile
    try:
        answer_client = OpenAIClient(answer_settings, profile)
        judge_client = OpenAIClient(with_cost_cap(settings, judge_cap), profile)
    except LLMConfigError as error:
        print(error)
        return 1
    models = {
        "understand": profile.understand_model,
        "generate": profile.generate_model,
        "judge": settings.eval.judge_model,
    }

    def make_pipeline() -> Pipeline:
        # One client for the whole run, so the cap bounds the run, not a question.
        return Pipeline(
            answer_settings,
            registry,
            retriever,
            answer_client,
            profile=profile_name,
            generate_version=args.generate_prompt,
        )

    question_set = "holdout" if args.holdout else "tuning"
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    prompt = args.generate_prompt or PROMPT_VERSIONS["generate"]
    runs_dir = RUNS_DIR / f"answer-{question_set}-{name}-generate{prompt}-{stamp}"
    print(
        f"answer eval: {len(questions)} questions x {args.runs} on {name} "
        f"({models['generate']}), caps ${answer_cap:.2f} answers / ${judge_cap:.2f} judge",
        flush=True,
    )
    retriever.warm_up()
    report = run_answer_eval(
        questions,
        make_pipeline,
        judge_client,
        answer_settings,
        registry,
        profile=name,
        models=models,
        runs=args.runs,
        question_set=question_set,
        runs_dir=runs_dir,
        generate_version=args.generate_prompt,
    )
    paths = write_answer_report(report, args.out)
    print(answer_markdown(report).split("## Questions")[0].rstrip())
    spent = answer_client.total_cost_usd, judge_client.total_cost_usd
    print(f"spent: answers ${spent[0]:.4f}, judge ${spent[1]:.4f}")
    print("report: " + ", ".join(str(path) for path in paths))
    print(f"answers (gitignored): {runs_dir}")
    return 0 if report.complete else 1
