"""Per-question diff of two answer reports, for a prompt change's before/after (CW-302).

    uv run python -m eval.answer_diff BEFORE.json AFTER.json [OUT.md]

Metrics only, like the reports themselves: pass/fail, failed check names, judge
verdicts, post-check outcomes, cost and latency per question.
"""

from __future__ import annotations

import sys
from pathlib import Path

from eval.answer_report import AnswerQuestion, AnswerReport


def _failed(question: AnswerQuestion) -> str:
    run = question.runs[0]
    names = [c.name for c in run.checks if not c.passed]
    if run.judge_passed is False:
        names.append("judge")
    return ", ".join(names) or "-"


def _count(value: int | None) -> str:
    return "not recorded" if value is None else str(value)


def _state(question: AnswerQuestion | None) -> str:
    if question is None:
        return "not run"
    return f"{question.passed_runs}/{len(question.runs)}"


def diff_markdown(before: AnswerReport, after: AnswerReport) -> str:
    old = {q.id: q for q in before.questions}
    new = {q.id: q for q in after.questions}
    ids = list(dict.fromkeys([*old, *new]))

    def total(report: AnswerReport) -> str:
        done = sum(q.passed_runs for q in report.questions)
        return f"{done}/{sum(len(q.runs) for q in report.questions)}"

    lines = [
        f"# Answer eval diff: generate {before.prompts.get('generate')} -> "
        f"{after.prompts.get('generate')} ({after.profile} profile)",
        "",
        "| | Before | After |",
        "|---|---|---|",
        f"| Passed | {total(before)} | {total(after)} |",
        f"| Answer cost $ | {before.cost_usd['answer']:.4f} | {after.cost_usd['answer']:.4f} |",
        f"| Judge cost $ | {before.cost_usd['judge']:.4f} | {after.cost_usd['judge']:.4f} |",
        f"| Graded turn p50 / p95 ms | {before.latency_ms['turn_p50']:.0f} / "
        f"{before.latency_ms['turn_p95']:.0f} | {after.latency_ms['turn_p50']:.0f} / "
        f"{after.latency_ms['turn_p95']:.0f} |",
        f'| "Another article" phrasings | {before.another_article_total} | '
        f"{after.another_article_total} |",
        f'| "Excerpts" wording | {_count(before.excerpt_wording_total)} | '
        f"{_count(after.excerpt_wording_total)} |",
        f"| Prompts | {before.prompts} | {after.prompts} |",
        "",
        "| Question | Category | Before | After | Change | Failed before | Failed after |",
        "|---|---|---|---|---|---|---|",
    ]
    for qid in ids:
        a, b = old.get(qid), new.get(qid)
        change = "-"
        if a and b and a.passed_runs != b.passed_runs:
            change = "fixed" if b.passed_runs > a.passed_runs else "REGRESSED"
        either = b or a
        category = either.category.value if either else "-"
        lines.append(
            f"| {qid} | {category} | {_state(a)} | {_state(b)} | {change} | "
            f"{_failed(a) if a else '-'} | {_failed(b) if b else '-'} |"
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str]) -> int:
    if len(argv) not in (2, 3):
        print(__doc__)
        return 2
    before, after = (
        AnswerReport.model_validate_json(Path(p).read_text(encoding="utf-8")) for p in argv[:2]
    )
    text = diff_markdown(before, after)
    if len(argv) == 3:
        Path(argv[2]).write_text(text, encoding="utf-8", newline="\n")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
