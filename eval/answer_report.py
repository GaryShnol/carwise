"""Run the answer level and write its reports (CW-302).

Why two outputs: the committed report holds metrics only (check names and results,
tokens, cost, latency, ids), because the repository is public and answers quote the
articles; the full answers and the judge's reasons go to eval/runs/, which is
gitignored, so a failure can still be read and classified locally.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from carwise.config import Settings
from carwise.llm.base import LLMClient
from carwise.pipeline import Pipeline
from carwise.prompts import PROMPT_VERSIONS
from carwise.registry import Registry
from eval.answer import (
    BudgetStopError,
    Check,
    behavior_of,
    checks_for,
    excerpt_wording_count,
    fingerprint,
    play,
    stated_numbers,
)
from eval.judge import PROMPT_VERSION as JUDGE_PROMPT
from eval.judge import Judged, criteria_change, criteria_version, judge, load_criteria
from eval.questions import Behavior, Category, Question
from eval.retrieval import percentile

RUNS_DIR = Path(__file__).parent / "runs"


class QuestionRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    behavior: str
    checks: list[Check]
    judge_passed: bool | None  # None: not a judged question, or the judge could not answer
    passed: bool
    post_check: str | None
    cited_cars: list[str]
    llm_calls: int  # every turn of the question
    tokens_in: int
    tokens_out: int
    cost_usd: float  # every turn of the question, judge excluded
    latency_ms: float  # the graded (last) turn, end to end
    generate_ms: float | None
    excerpt_wording: int = 0  # "the excerpts" instead of "the articles" (a metric, not a check)
    # Stability across runs, without storing text: hashes of the answer and of its numbers.
    text_sha: str = ""
    numbers_sha: str = ""


class AnswerQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    category: Category
    expected: Behavior
    judged: bool
    runs: list[QuestionRun]

    @property
    def passed_runs(self) -> int:
        return sum(run.passed for run in self.runs)

    @property
    def same_behavior(self) -> bool:
        return len({run.behavior for run in self.runs}) == 1

    @property
    def same_numbers(self) -> bool:
        return len({run.numbers_sha for run in self.runs}) == 1

    @property
    def identical_text_share(self) -> float:
        """Share of run pairs whose answers are word for word the same (1.0 with one run)."""
        hashes = [run.text_sha for run in self.runs]
        pairs = [(a, b) for i, a in enumerate(hashes) for b in hashes[i + 1 :]]
        return sum(a == b for a, b in pairs) / len(pairs) if pairs else 1.0


class AnswerReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    level: str = "answer"
    created: str
    question_set: str  # tuning | holdout
    profile: str
    models: dict[str, str]
    prompts: dict[str, str]
    runs_per_question: int
    complete: bool  # false when a cost cap stopped the run early
    questions: list[AnswerQuestion]
    cost_usd: dict[str, float]  # answer, judge
    tokens: dict[str, int]
    latency_ms: dict[str, float | None]  # p50 / p95 of the graded turn and of generate
    another_article_total: int
    excerpt_wording_total: int | None = None  # None: a report from before the metric existed
    notes: list[str] = []  # why the judge criteria changed, re-scoring provenance, ...
    runs_log: str | None = None  # the eval/runs/ folder holding this run's answers
    # Questions with the same behavior / the same numbers in every run, and the mean share
    # of identical answer pairs. Empty for reports made before the metric existed.
    stability: dict[str, float] = {}
    post_check: dict[str, int]  # outcome -> count over graded turns


def run_answer_eval(
    questions: Sequence[Question],
    make_pipeline: Callable[[], Pipeline],
    judge_client: LLMClient | None,
    settings: Settings,
    registry: Registry,
    *,
    profile: str,
    models: dict[str, str],
    runs: int,
    question_set: str,
    runs_dir: Path,
    generate_version: str | None = None,
) -> AnswerReport:
    """Play every question `runs` times through the real pipeline, check it, judge it."""
    criteria = load_criteria()
    runs_dir.mkdir(parents=True, exist_ok=True)
    log_path = runs_dir / "answers.jsonl"
    results: list[AnswerQuestion] = []
    judge_cost = 0.0
    judge_in = judge_out = 0
    complete = True
    with log_path.open("w", encoding="utf-8", newline="\n") as log:
        for question in questions:
            question_runs: list[QuestionRun] = []
            for run_index in range(runs):
                pipeline = make_pipeline()  # one client per question run: its own cost total
                try:
                    played = play(question, pipeline, settings.llm.history_window)
                except BudgetStopError as error:
                    print(f"stopped: {error}")
                    complete = False
                    break
                checks = checks_for(question, played, settings, registry)
                verdict: Judged | None = None
                criterion = criteria.get(question.id)
                if criterion and judge_client is not None and behavior_of(played.last) == "answer":
                    verdict = judge(
                        judge_client, models["judge"], criterion, played.user_turns, played.last
                    )
                    judge_cost += verdict.cost_usd
                    judge_in += verdict.tokens_in
                    judge_out += verdict.tokens_out
                last = played.last
                passed = all(c.passed for c in checks) and (
                    verdict is None or verdict.passed is True
                )
                if criterion and verdict is None:
                    passed = False  # a judged question that could not be judged does not pass
                question_runs.append(
                    QuestionRun(
                        behavior=behavior_of(last),
                        checks=checks,
                        judge_passed=verdict.passed if verdict else None,
                        passed=passed,
                        post_check=last.post_check.outcome.value if last.post_check else None,
                        cited_cars=sorted({s.car for s in last.sources}),
                        llm_calls=sum(a.llm_calls for a in played.answers),
                        tokens_in=sum(a.usage.input_tokens for a in played.answers),
                        tokens_out=sum(a.usage.output_tokens for a in played.answers),
                        cost_usd=round(sum(a.cost_usd for a in played.answers), 6),
                        latency_ms=last.latency_ms.get("total", 0.0),
                        generate_ms=last.latency_ms.get("generate"),
                        excerpt_wording=excerpt_wording_count(last.text),
                        text_sha=fingerprint(last.text),
                        numbers_sha=fingerprint(" ".join(stated_numbers(last.text, registry))),
                    )
                )
                log.write(
                    json.dumps(
                        {
                            "id": question.id,
                            "run": run_index + 1,
                            "turns": [
                                {"user": user, "answer": answer.text, "flags": answer.flags}
                                for user, answer in zip(question.turns, played.answers, strict=True)
                            ],
                            "retrieved": [h.chunk.chunk_id for h in last.retrieved],
                            "cited": [s.chunk_id for s in last.sources],
                            "checks": [c.model_dump() for c in checks],
                            "judge": verdict.model_dump() if verdict else None,
                            "preferences": played.preferences.model_dump(),
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
                mark = "pass" if passed else "FAIL"
                print(f"  {question.id} [{run_index + 1}/{runs}] {mark}", flush=True)
            if question_runs:
                results.append(
                    AnswerQuestion(
                        id=question.id,
                        category=question.category,
                        expected=question.expect.behavior,
                        judged=question.id in criteria,
                        runs=question_runs,
                    )
                )
            if not complete:
                break
    every = [run for q in results for run in q.runs]
    graded = [run.latency_ms for run in every]
    generate = [run.generate_ms for run in every if run.generate_ms is not None]
    outcomes: dict[str, int] = {}
    for run in every:
        if run.post_check:
            outcomes[run.post_check] = outcomes.get(run.post_check, 0) + 1
    return AnswerReport(
        created=datetime.now(UTC).isoformat(timespec="seconds"),
        question_set=question_set,
        profile=profile,
        models=models,
        prompts={
            **PROMPT_VERSIONS,
            "generate": generate_version or PROMPT_VERSIONS["generate"],
            "judge": JUDGE_PROMPT,
            "judge_criteria": criteria_version(),
        },
        stability=stability_of(results),
        runs_per_question=runs,
        complete=complete,
        questions=results,
        cost_usd={
            "answer": round(sum(run.cost_usd for run in every), 6),
            "judge": round(judge_cost, 6),
        },
        tokens={
            "answer_in": sum(run.tokens_in for run in every),
            "answer_out": sum(run.tokens_out for run in every),
            "judge_in": judge_in,
            "judge_out": judge_out,
        },
        latency_ms={
            "turn_p50": percentile(graded, 50),
            "turn_p95": percentile(graded, 95),
            "generate_p50": percentile(generate, 50),
            "generate_p95": percentile(generate, 95),
        },
        another_article_total=sum(
            int(c.detail) for run in every for c in run.checks if c.name == "another_article"
        ),
        post_check=outcomes,
        excerpt_wording_total=sum(run.excerpt_wording for run in every),
        runs_log=runs_dir.name,
        notes=[f"judge criteria {criteria_version()}: {criteria_change()}"]
        if criteria_change()
        else [],
    )


def stability_of(questions: Sequence[AnswerQuestion]) -> dict[str, float]:
    if not questions:
        return {}
    return {
        "questions": len(questions),
        "same_behavior": sum(q.same_behavior for q in questions),
        "same_numbers": sum(q.same_numbers for q in questions),
        "identical_text_mean": round(
            sum(q.identical_text_share for q in questions) / len(questions), 3
        ),
    }


def _failed(run: QuestionRun) -> str:
    names = [c.name for c in run.checks if not c.passed]
    if run.judge_passed is False:
        names.append("judge")
    return ", ".join(names) or "-"


def _stable(question: AnswerQuestion) -> str:
    def yes(flag: bool) -> str:
        return "yes" if flag else "NO"

    return (
        f"{yes(question.same_behavior)} / {yes(question.same_numbers)} / "
        f"{question.identical_text_share:.0%}"
    )


def markdown(report: AnswerReport) -> str:
    summary = ["| Category | Passed |", "|---|---|"]
    for category in Category:
        rows = [q for q in report.questions if q.category is category]
        if rows:
            done = sum(q.passed_runs for q in rows)
            total = sum(len(q.runs) for q in rows)
            summary.append(f"| {category.value} | {done}/{total} |")
    done = sum(q.passed_runs for q in report.questions)
    total = sum(len(q.runs) for q in report.questions)
    summary.append(f"| **total** | {done}/{total} |")
    lat = report.latency_ms
    wording = report.excerpt_wording_total
    excerpts = "not recorded" if wording is None else str(wording)

    def ms(value: float | None) -> str:
        return "-" if value is None else f"{value:.0f}"

    lines = [
        f"# Answer eval ({report.question_set} set): {report.profile} profile",
        "",
        f"Created {report.created}. Models: "
        + ", ".join(f"{k} {v}" for k, v in report.models.items())
        + ". Prompts: "
        + ", ".join(f"{k} {v}" for k, v in report.prompts.items())
        + f". {report.runs_per_question} run(s) per question"
        + ("" if report.complete else "; STOPPED EARLY at a cost cap")
        + ".",
        "",
        f"Cost: answers ${report.cost_usd['answer']:.4f}, judge ${report.cost_usd['judge']:.4f}. "
        f"Tokens: answers {report.tokens['answer_in']} in / {report.tokens['answer_out']} out, "
        f"judge {report.tokens['judge_in']} in / {report.tokens['judge_out']} out.",
        "",
        f"Latency of the graded turn: p50 {ms(lat['turn_p50'])} ms, p95 {ms(lat['turn_p95'])} ms; "
        f"generate call p50 {ms(lat['generate_p50'])} ms, p95 {ms(lat['generate_p95'])} ms.",
        "",
        "Post-check outcomes: "
        + (", ".join(f"{k} {v}" for k, v in sorted(report.post_check.items())) or "-")
        + f'. "Another article" phrasings: {report.another_article_total}; '
        + f'"excerpts" wording: {excerpts}.',
        "",
        *([f"Notes: {' '.join(report.notes)}", ""] if report.notes else []),
        *(
            [
                f"Stability over {report.runs_per_question} runs: same behavior in "
                f"{report.stability['same_behavior']:.0f}/{report.stability['questions']:.0f} "
                f"questions, same numbers in {report.stability['same_numbers']:.0f}/"
                f"{report.stability['questions']:.0f}, identical text in "
                f"{report.stability['identical_text_mean']:.0%} of answer pairs (mean).",
                "",
            ]
            if report.stability
            else []
        ),
        "## Summary",
        "",
        *summary,
        "",
        "## Questions",
        "",
        "| Question | Category | Behavior | Post-check | Judge | Failed checks (first run) | "
        "Passed | Same behavior / numbers / text | Cost $ | Latency ms |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for q in report.questions:
        first = q.runs[0]
        behavior = (
            first.behavior
            if first.behavior == q.expected.value
            else f"{first.behavior} (want {q.expected.value})"
        )
        judge_cell = (
            "-" if not q.judged else {True: "pass", False: "FAIL", None: "n/a"}[first.judge_passed]
        )
        cost = sum(run.cost_usd for run in q.runs)
        lines.append(
            f"| {q.id} | {q.category.value} | {behavior} | {first.post_check or '-'} | "
            f"{judge_cell} | {_failed(first)} | {q.passed_runs}/{len(q.runs)} | "
            f"{_stable(q)} | {cost:.4f} | "
            f"{first.latency_ms:.0f} |"
        )
    return "\n".join(lines) + "\n"


def write(report: AnswerReport, out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    name = f"answer-{report.question_set}-{report.profile}"
    json_path, md_path = out_dir / f"{name}.json", out_dir / f"{name}.md"
    data = json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=1)
    json_path.write_text(data + "\n", encoding="utf-8", newline="\n")
    md_path.write_text(markdown(report), encoding="utf-8", newline="\n")
    return [json_path, md_path]
