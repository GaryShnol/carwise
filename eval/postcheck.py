"""Adversarial post-check set: how many scripted bad answers the post-check catches (CW-619).

Why a separate set: the answer eval shows the post-check stays clean on real
answers, which bounds false positives but says nothing about recall (CR-019).
Here each case scripts one generate output against synthetic chunks and runs it
through the real pipeline with a scripted LLM: no model, no key, no cost, the
same result every run. Each case declares the outcome today's code gives, so a
known gap is a pinned, counted miss rather than an untested claim.

Run `uv run python -m eval.postcheck` to rewrite the committed report; a test
fails when the report and the cases disagree.
"""

from __future__ import annotations

import sys
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from carwise.config import Settings, load_settings
from carwise.llm.fake import FakeLLMClient
from carwise.pipeline import Pipeline
from carwise.registry import Registry, load_registry
from carwise.retrieval.retriever import Query
from carwise.schemas import (
    CheckFindings,
    Chunk,
    Generation,
    Intent,
    PostCheckOutcome,
    RetrievedChunk,
    Understanding,
)

CASES_PATH = Path(__file__).with_name("postcheck_cases.yaml")
REPORT_PATH = Path(__file__).parent / "reports" / "postcheck-adversarial.md"
DEFAULT_MESSAGE = "מה כדאי לדעת על הרכב?"  # no number and no car name of its own


class Case(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    kind: str
    bad: bool
    flagged: bool  # what today's post-check gives: True = suspect
    # Why a bad case is not flagged (a review finding or README line), or how a
    # flagged one is caught when it is caught only by accident.
    note: str = ""
    chunks: dict[str, list[str]] = Field(min_length=1)
    message: str = DEFAULT_MESSAGE
    rewrite: str = ""
    unrecognized: list[str] = []
    answer: str

    @model_validator(mode="after")
    def _every_miss_is_explained(self) -> Case:
        if self.bad and not self.flagged and not self.note:
            raise ValueError(f"{self.id}: a bad case expected to pass needs a `note`")
        return self


def load_cases(path: Path = CASES_PATH) -> list[Case]:
    raw: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    cases = [Case.model_validate(item) for item in raw["cases"]]
    ids = [case.id for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate case ids in the post-check set")
    return cases


def hits_for(case: Case, registry: Registry) -> list[RetrievedChunk]:
    """The case's chunks as this turn's retrieved chunks, in a fixed order."""
    hits = []
    for car_id, texts in case.chunks.items():
        car = registry.get(car_id)  # an unknown id fails here, loudly
        for index, text in enumerate(texts):
            chunk = Chunk(
                chunk_id=f"{car_id}:{index:03d}",
                car=car_id,
                car_name=car.display_name,
                section=f"פרק {index}",
                source_url=car.url,
                published=date(2026, 1, 1),
                text=text,
                embed_text=text,
            )
            hits.append(RetrievedChunk(chunk=chunk, score=0.9))
    return hits


class FixedRetriever:
    """Every search returns the case's chunks: retrieval is not under test here."""

    def __init__(self, hits: list[RetrievedChunk]) -> None:
        self._hits = hits

    def embed(self, text: str) -> Query:
        return Query(text=text, vector=[])

    def search(
        self, query: str | Query, car_ids: list[str] | None = None, top_k: int | None = None
    ) -> list[RetrievedChunk]:
        return list(self._hits)

    def search_per_car(
        self, query: str | Query, car_ids: list[str], top_k_per_car: int | None = None
    ) -> list[RetrievedChunk]:
        return list(self._hits)

    def search_all(
        self, query: str | Query, top_k: int | None = None, per_car_cap: int | None = None
    ) -> list[RetrievedChunk]:
        return list(self._hits)

    def spec_boxes(self, query: str | Query, car_ids: list[str]) -> list[RetrievedChunk]:
        return []


class CaseResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    case: Case
    findings: CheckFindings  # the post-check of the scripted answer (first attempt)
    outcome: PostCheckOutcome | None
    llm_calls: int

    @property
    def flagged(self) -> bool:
        return self.findings.suspect

    @property
    def caught_by(self) -> str:
        checks = [name for name, found in self.findings if found]
        return ", ".join(checks) or "-"


def run_case(case: Case, settings: Settings, registry: Registry) -> CaseResult:
    """One turn through the real pipeline; a flagged answer is scripted again for the
    retry, so a caught case must end in the code-built fallback."""
    hits = hits_for(case, registry)
    cars = list(case.chunks)
    plan = Understanding(
        intent=Intent.COMPARE if len(cars) > 1 else Intent.FACT,
        cars=cars,
        unrecognized_cars=case.unrecognized,
        standalone_question=case.rewrite or case.message,
        preference_updates=[],
    )
    bad = Generation(answer=case.answer, used_chunk_ids=[hits[0].chunk.chunk_id])
    llm = FakeLLMClient([plan, bad, bad])
    pipeline = Pipeline(settings, registry, FixedRetriever(hits), llm)
    answer = pipeline.ask(case.message, [])
    check = answer.post_check
    findings = check.attempts[0] if check else CheckFindings(cars=[], numbers=[])
    return CaseResult(
        case=case,
        findings=findings,
        outcome=check.outcome if check else None,
        llm_calls=len(llm.calls),
    )


def run_all(settings: Settings | None = None, registry: Registry | None = None) -> list[CaseResult]:
    settings = settings or load_settings()
    registry = registry or load_registry()
    return [run_case(case, settings, registry) for case in load_cases()]


def markdown(results: list[CaseResult]) -> str:
    """Metrics and case ids only: no chunk or answer text in a committed report."""
    bad = [r for r in results if r.case.bad]
    controls = [r for r in results if not r.case.bad]
    caught = sum(r.flagged for r in bad)
    clean = sum(not r.flagged for r in controls)
    kinds = Counter(r.case.kind for r in bad)
    caught_by_kind = Counter(r.case.kind for r in bad if r.flagged)
    lines = [
        "# Post-check adversarial set (CW-619)",
        "",
        "Scripted bad generate outputs against synthetic chunks, run through the real",
        "pipeline with a scripted LLM (no model calls, no cost). Regenerate with",
        "`uv run python -m eval.postcheck`; `tests/test_postcheck_adversarial.py` fails",
        "when this report and `eval/postcheck_cases.yaml` disagree.",
        "",
        f"- **Bad answers caught:** {caught}/{len(bad)}",
        f"- **Clean controls left clean:** {clean}/{len(controls)}",
        "",
        "| Kind | Caught |",
        "|---|---|",
        *(f"| {kind} | {caught_by_kind[kind]}/{total} |" for kind, total in kinds.items()),
        "",
        "## Known misses",
        "",
        "| Case | Kind | Why not caught |",
        "|---|---|---|",
        *(f"| `{r.case.id}` | {r.case.kind} | {r.case.note} |" for r in bad if not r.flagged),
        "",
        "## All cases",
        "",
        "| Case | Kind | Bad | Flagged by | Outcome | Note |",
        "|---|---|---|---|---|---|",
        *(
            f"| `{r.case.id}` | {r.case.kind} | {'yes' if r.case.bad else 'no'} | "
            f"{r.caught_by} | {r.outcome.value if r.outcome else '-'} | {r.case.note} |"
            for r in results
        ),
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    REPORT_PATH.write_text(markdown(run_all()), encoding="utf-8", newline="\n")
    print(f"wrote {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
