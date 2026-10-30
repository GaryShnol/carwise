"""CW-303 step 3: one-at-a-time sweep of top_k and the per-car / cross-car caps.

Why one at a time from the current values, not a grid: 23 questions cannot support
picking the best of dozens of combinations (that would fit noise), and the question
asked is "what is the smallest change that fixes the misses", which a one-knob-at-a-
time table answers directly. The model loads once and the recorded plans are
replayed, so the sweep is free and repeatable:

    uv run python -m eval.sweep
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from carwise.config import Settings, load_settings
from carwise.llm.base import LLMClient
from carwise.pipeline import Pipeline
from carwise.registry import load_registry
from carwise.retrieval.embedder import make_embedder
from carwise.retrieval.retriever import open_retriever
from eval.candidates import cached_chunks
from eval.cli import retrieval_report
from eval.questions import load_negatives, load_questions
from eval.recording import load_recording
from eval.report import REPORTS_DIR

OUT = REPORTS_DIR / "cw303" / "step3" / "sweep.md"
# (label, retrieval overrides): the current values first, then one knob at a time.
VARIANTS: list[tuple[str, dict[str, Any]]] = [
    ("current", {}),
    ("per_car_cap 2", {"per_car_cap": 2}),
    ("per_car_cap 4", {"per_car_cap": 4}),
    ("top_k 3", {"top_k": 3}),
    ("top_k 4", {"top_k": 4}),
    ("top_k 7", {"top_k": 7}),
    ("cross_car_per_car_cap 3", {"cross_car_per_car_cap": 3}),
    ("cross_car_top_k 16", {"cross_car_top_k": 16}),
]


def main() -> int:
    settings = load_settings()
    registry = load_registry()
    recording = load_recording()
    if recording is None:
        print("no recording; run `python -m app eval --record` first")
        return 1
    questions = load_questions().questions
    probes = load_negatives().probes
    texts = {chunk.chunk_id: chunk.text for chunk in cached_chunks(settings, registry)}
    embedder = make_embedder(settings.embeddings)  # loaded once, shared by every variant
    embedder.warm_up()
    rows = [
        "| Setting | Passed | Sources hit | MRR | Failing questions "
        "| Mean chunks / chars per answer |",
        "|---|---|---|---|---|---|",
    ]
    for label, overrides in VARIANTS:
        retrieval = settings.retrieval.model_copy(update=overrides)
        varied: Settings = settings.model_copy(update={"retrieval": retrieval})
        retriever = open_retriever(varied, embedder)  # same model, same index

        def make_pipeline(llm: LLMClient, s: Settings = varied, r: Any = retriever) -> Pipeline:
            return Pipeline(s, registry, r, llm)

        report = retrieval_report(varied, retriever, make_pipeline, recording, questions, probes, 1)
        total = report.summary[-1]
        answered = [q for q in report.questions if q.behavior == "answer"]
        chunks = sum(len(q.retrieved) for q in answered) / len(answered)
        chars = sum(len(texts[h.chunk_id]) for q in answered for h in q.retrieved) / len(answered)
        failing = ", ".join(q.id for q in report.questions if not q.passed) or "-"
        rows.append(
            f"| {label} | {total.passed}/{total.questions} | {total.sources_hit}/{total.sources} | "
            f"{total.mrr:.3f} | {failing} | {chunks:.2f} / {chars:.0f} |"
        )
        print(rows[-1], flush=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    header = (
        "# CW-303 step 3: top_k and caps, one at a time\n\n"
        "Same recording, e5-large, spec boxes forced (step 2), 1 run per setting "
        "(retrieval is deterministic). Chars are chunk text sent to generation.\n\n"
    )
    Path(OUT).write_text(header + "\n".join(rows) + "\n", encoding="utf-8", newline="\n")
    print(f"written: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
