"""Eval reports: a JSON file for tools and a Markdown file for people.

Why metrics only: the repository is public and the articles belong to the
publisher, so a committed report holds ids, scores, ranks, pass/fail, tokens, cost
and latency, never chunk text or answer text (CLAUDE.md section 10).
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from eval.retrieval import (
    CategorySummary,
    ProbeResult,
    QuestionResult,
    ScoreSpread,
    SourceResult,
)

REPORTS_DIR = Path(__file__).parent / "reports"


class RetrievalReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    level: str = "retrieval"
    created: str
    embedder: dict[str, str | None]
    retrieval: dict[str, float | int]
    chunking: dict[str, int]
    recording: dict[str, str | int | float]  # model, prompt version, date, cost of recording it
    runs: int
    warm_up_s: float
    latency_ms: dict[str, float | None]  # p50 / p95 of the retrieve stage over all runs
    summary: list[CategorySummary]
    scores: dict[str, ScoreSpread]  # best score: answerable questions vs threshold probes
    questions: list[QuestionResult]
    probes: list[ProbeResult]


def report_name(report: RetrievalReport) -> str:
    """One file per embedding model, so the CW-305 candidates sit side by side."""
    model = str(report.embedder.get("model") or report.embedder.get("provider"))
    return f"retrieval-{model.rsplit('/', 1)[-1]}"


def write_report(report: RetrievalReport, out_dir: Path = REPORTS_DIR) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    name = report_name(report)
    json_path = out_dir / f"{name}.json"
    md_path = out_dir / f"{name}.md"
    data = json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=1)
    json_path.write_text(data + "\n", encoding="utf-8", newline="\n")
    md_path.write_text(markdown(report), encoding="utf-8", newline="\n")
    return [json_path, md_path]


def _num(value: float | None, digits: int = 3) -> str:
    return "-" if value is None else f"{value:.{digits}f}"


def _source(result: SourceResult) -> str:
    rank = result.rank if result.rank else "miss"
    return f"{result.car} / {result.section}: {rank} (car rank {result.car_rank or '-'})"


def summary_rows(summary: list[CategorySummary]) -> list[str]:
    rows = [
        "| Category | Passed | Sources hit | MRR |",
        "|---|---|---|---|",
    ]
    for row in summary:
        label = f"**{row.category}**" if row.category == "total" else row.category
        rows.append(
            f"| {label} | {row.passed}/{row.questions} | "
            f"{row.sources_hit}/{row.sources} | {_num(row.mrr)} |"
        )
    return rows


def spread_rows(scores: dict[str, ScoreSpread]) -> list[str]:
    rows = [
        "| Best score of | n | min | Q1 | median | Q3 | max |",
        "|---|---|---|---|---|---|---|",
    ]
    for label, s in scores.items():
        values = " | ".join(_num(v) for v in (s.min, s.q1, s.median, s.q3, s.max))
        rows.append(f"| {label} | {s.n} | {values} |")
    return rows


def _pass(passed: bool | None) -> str:
    return "-" if passed is None else ("pass" if passed else "FAIL")


def markdown(report: RetrievalReport) -> str:
    lines = [
        f"# Retrieval eval: {report.embedder.get('model')}",
        "",
        f"Created {report.created}. {report.runs} run(s) per question; no LLM calls "
        f"(understand outputs replayed from a recording by {report.recording['model']}, "
        f"prompt {report.recording['understand_prompt']}, "
        f"recorded {report.recording['recorded_at']}).",
        "",
        "Settings: "
        + ", ".join(f"{k} {v}" for k, v in {**report.retrieval, **report.chunking}.items())
        + ".",
        "",
        "## Summary",
        "",
        *summary_rows(report.summary),
        "",
        f"Retrieve stage latency: p50 {_num(report.latency_ms['p50'], 0)} ms, "
        f"p95 {_num(report.latency_ms['p95'], 0)} ms (query embedding plus scoring, CPU). "
        f"Model warm-up {report.warm_up_s:.1f} s.",
        "",
        "## Score distribution",
        "",
        "Best retrieval score per case. Threshold probes ask about one of the eight cars on a",
        "topic its article does not cover (eval/negatives.yaml); CW-303 sets the relevance",
        "threshold between the two rows.",
        "",
        *spread_rows(report.scores),
        "",
        "## Questions",
        "",
        "| Question | Category | Behavior | Expected sources: rank | Best score | Pass |",
        "|---|---|---|---|---|---|",
    ]
    for q in report.questions:
        sources = [_source(s) for s in q.sources]
        if q.sources_any:
            sources.append("any of: " + "; ".join(_source(s) for s in q.sources_any))
        behavior = q.behavior if q.behavior == q.expected else f"{q.behavior} (want {q.expected})"
        stable = "" if q.stable else " (unstable)"
        lines.append(
            f"| {q.id} | {q.category} | {behavior} | {'<br>'.join(sources) or '-'} | "
            f"{_num(q.best_score)} | {'pass' if q.passed else 'FAIL'}{stable} |"
        )
    lines += [
        "",
        "## Negative probes (no article answers these)",
        "",
        "Behavior probes must get the out-of-scope reply; threshold probes are not graded",
        "here, they supply the score distribution above.",
        "",
        "| Probe | Purpose | Behavior | Intent | Best score | Pass |",
        "|---|---|---|---|---|---|",
    ]
    for p in report.probes:
        lines.append(
            f"| {p.id} | {p.purpose} | {p.behavior} | {p.intent or '-'} | "
            f"{_num(p.best_score)} | {_pass(p.passed)} |"
        )
    return "\n".join(lines) + "\n"
