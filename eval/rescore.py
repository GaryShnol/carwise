"""Re-score a logged answer-eval run after a check or a judge criterion changed (CW-302).

    uv run [--env-file .env] python -m eval.rescore REPORT.json ANSWERS.jsonl OUT_DIR \\
        [--rejudge QUESTION_ID ...]

Why: a fix in a check should be measured on the same answers it was found on, not
on a new run whose answers differ by chance. The attribution check is recomputed
from the logged answer text and retrieved chunk ids (chunk text is rebuilt from the
cached articles, so the chunking must be the one the run used); the other
deterministic checks did not change and are kept. Only the questions named with
--rejudge are judged again (with the current criteria); that is the only part that
calls a model, and its cost is printed and noted in the report.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from carwise.config import load_settings
from carwise.llm.base import LLMClient
from carwise.llm.openai_client import OpenAIClient
from carwise.registry import Registry, load_registry
from carwise.schemas import Chunk, RetrievedChunk
from eval.answer import Check, attribution_problems
from eval.answer_report import AnswerReport, write
from eval.candidates import cached_chunks
from eval.judge import criteria_version, judge_text, load_criteria


def _attribution(entry: dict[str, Any], chunks: dict[str, Chunk], registry: Registry) -> Check:
    hits = [RetrievedChunk(chunk=chunks[cid], score=0.0) for cid in entry["retrieved"]]
    users = [turn["user"] for turn in entry["turns"]]
    wrong = attribution_problems(entry["turns"][-1]["answer"], hits, users, registry)
    return Check(
        name="attribution",
        passed=not wrong,
        detail="; ".join(f"{w.number}: {w.placed_with} <- {'/'.join(w.backed_by)}" for w in wrong),
    )


def rescore(
    report: AnswerReport,
    entries: list[dict[str, Any]],
    chunks: dict[str, Chunk],
    registry: Registry,
    *,
    rejudge: set[str],
    judge_client: LLMClient | None,
    judge_model: str,
    source: str,
) -> AnswerReport:
    """The report with attribution recomputed and the named questions judged again."""
    logged = {(e["id"], e["run"]): e for e in entries}
    criteria = load_criteria()
    spent = 0.0
    questions = []
    for question in report.questions:
        runs = []
        for index, run in enumerate(question.runs, 1):
            entry = logged[(question.id, index)]
            checks = [
                _attribution(entry, chunks, registry) if c.name == "attribution" else c
                for c in run.checks
            ]
            judged = run.judge_passed
            if question.id in rejudge:
                if judge_client is None:
                    raise ValueError("--rejudge needs a judge client (OPENAI_API_KEY)")
                hits = [RetrievedChunk(chunk=chunks[cid], score=0.0) for cid in entry["retrieved"]]
                verdict = judge_text(
                    judge_client,
                    judge_model,
                    criteria[question.id],
                    [turn["user"] for turn in entry["turns"]],
                    entry["turns"][-1]["answer"],
                    hits,
                )
                judged, spent = verdict.passed, spent + verdict.cost_usd
                print(f"  re-judged {question.id} run {index}: {verdict.passed}")
            passed = all(c.passed for c in checks) and judged is not False
            if question.judged and judged is None:
                passed = False
            runs.append(
                run.model_copy(update={"checks": checks, "judge_passed": judged, "passed": passed})
            )
        questions.append(question.model_copy(update={"runs": runs}))
    note = (
        f"Re-scored offline from {source}: attribution check recomputed with the current code"
        + (
            f"; re-judged with criteria {criteria_version()}: {', '.join(sorted(rejudge))} "
            f"(${spent:.4f})"
            if rejudge
            else ""
        )
        + "."
    )
    prompts = {**report.prompts}
    if rejudge:
        prompts["judge_criteria"] = f"{criteria_version()} (re-judged: {len(rejudge)} question(s))"
    return report.model_copy(
        update={
            "questions": questions,
            "prompts": prompts,
            "notes": [*report.notes, note],
            "cost_usd": {**report.cost_usd, "judge": round(report.cost_usd["judge"] + spent, 6)},
        }
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("report", type=Path)
    parser.add_argument("answers", type=Path)
    parser.add_argument("out_dir", type=Path)
    parser.add_argument("--rejudge", nargs="*", default=[])
    args = parser.parse_args()
    settings = load_settings()
    registry = load_registry()
    report = AnswerReport.model_validate_json(args.report.read_text(encoding="utf-8"))
    entries = [json.loads(line) for line in args.answers.read_text(encoding="utf-8").splitlines()]
    chunks = {chunk.chunk_id: chunk for chunk in cached_chunks(settings, registry)}
    client = None
    if args.rejudge:
        capped = settings.model_copy(
            update={
                "llm": settings.llm.model_copy(
                    update={"max_cost_usd": settings.eval.judge_max_cost_usd}
                )
            }
        )
        client = OpenAIClient(capped, capped.profile(report.profile))
    rescored = rescore(
        report,
        entries,
        chunks,
        registry,
        rejudge=set(args.rejudge),
        judge_client=client,
        judge_model=settings.eval.judge_model,
        source=args.answers.parent.name,
    )
    out = args.out_dir
    out.mkdir(parents=True, exist_ok=True)
    rescored = rescored.model_copy(update={"question_set": f"{report.question_set}-rescored"})
    paths = write(rescored, out)
    before = sum(q.passed_runs for q in report.questions)
    after = sum(q.passed_runs for q in rescored.questions)
    total = sum(len(q.runs) for q in report.questions)
    print(f"passed: {before}/{total} as graded -> {after}/{total} re-scored")
    print("report: " + ", ".join(str(p) for p in paths))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
