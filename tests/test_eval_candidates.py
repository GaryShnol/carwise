"""CW-305 candidate configuration and the side-by-side comparison. Offline, no model."""

from __future__ import annotations

from carwise.config import load_settings
from eval.candidates import CANDIDATES_DIR, apply, load_candidates, peak_memory_mb
from eval.questions import ProbePurpose
from eval.report import RetrievalReport, comparison_markdown
from eval.retrieval import CategorySummary, ProbeResult, ScoreSpread

SETTINGS = load_settings()


def test_every_candidate_pins_a_revision_and_states_its_prefixes() -> None:
    found = load_candidates()
    assert {"e5-base", "e5-large", "bge-m3", "e5-base-lexical"} <= set(found)
    for candidate in found.values():
        assert len(candidate.embeddings["revision"]) == 40  # a full commit hash
        assert {"query_prefix", "passage_prefix"} <= set(candidate.embeddings)


def test_apply_changes_only_the_embedder_lexical_flag_and_index_dir() -> None:
    found = load_candidates()
    applied = apply(SETTINGS, "e5-base-lexical", found["e5-base-lexical"])
    assert applied.retrieval.lexical.enabled
    assert applied.paths.index_dir == str(CANDIDATES_DIR / "e5-base-lexical" / "index")
    same = {"top_k", "per_car_cap", "cross_car_top_k", "relevance_threshold"}
    assert all(getattr(applied.retrieval, f) == getattr(SETTINGS.retrieval, f) for f in same)
    assert applied.chunking == SETTINGS.chunking
    bge = apply(SETTINGS, "bge-m3", found["bge-m3"])
    assert (bge.embeddings.model, bge.embeddings.query_prefix) == ("BAAI/bge-m3", "")
    assert not bge.retrieval.lexical.enabled


def test_peak_memory_is_measured() -> None:
    peak = peak_memory_mb()
    assert peak is None or peak > 0


def _report(name: str, median: float) -> RetrievalReport:
    spread = ScoreSpread(n=2, min=0.8, q1=0.8, median=median, q3=0.9, max=0.9)
    probes = [
        ProbeResult(
            id=f"thr-{i}",
            purpose=ProbePurpose.THRESHOLD,
            behavior="answer",
            passed=None,
            intent="fact",
            refusal=None,
            best_score=score,
            retrieved=[],
        )
        for i, score in enumerate([0.82, 0.88])
    ]
    return RetrievalReport(
        created="x",
        embedder={"provider": "sentence_transformers", "model": name, "revision": None},
        retrieval=SETTINGS.retrieval,
        chunking=SETTINGS.chunking.model_dump(),
        recording={"model": "m", "understand_prompt": "v1", "recorded_at": "x", "cost_usd": 0},
        runs=1,
        warm_up_s=1.0,
        latency_ms={"p50": 10.0, "p95": 20.0},
        summary=[
            CategorySummary(
                category="comparison", questions=2, passed=1, sources=4, sources_hit=3, mrr=0.5
            ),
            CategorySummary(
                category="total", questions=2, passed=1, sources=4, sources_hit=3, mrr=0.5
            ),
        ],
        scores={"answerable": spread, "threshold_probes": spread},
        questions=[],
        probes=probes,
        resources={"candidate": name, "token_window": 512, "chunks_over_window": 5},
    )


def test_comparison_puts_candidates_side_by_side() -> None:
    text = comparison_markdown({"a": _report("a", 0.85), "b": _report("b", 0.87)})
    assert "| Category | a | b |" in text
    assert "| **total** | 1/2 · 3/4 · 0.500 | 1/2 · 3/4 · 0.500 |" in text
    # Overlap: probes (0.82, 0.88) above the answerable median.
    assert "| a | " in text and "| 1/2 | " in text
    assert "| a | 512 | 5 (None) |" in text
