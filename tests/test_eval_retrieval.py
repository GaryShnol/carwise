"""Retrieval level of the eval (CW-302): recording, replay, staleness and grading.

Everything runs offline: synthetic chunks, the hashing embedder and the fake LLM
client. Car ids and names come from the registry because the pipeline resolves
names through it; chunk text is made up (the repository is public).
"""

from __future__ import annotations

from datetime import date

import pytest

from carwise.config import load_settings
from carwise.llm.base import LLMClient, LLMOutputError
from carwise.llm.fake import FakeLLMClient
from carwise.pipeline import Pipeline
from carwise.prompts import understand_system
from carwise.registry import load_registry
from carwise.retrieval.embedder import FakeEmbedder, Vector
from carwise.retrieval.retriever import Retriever
from carwise.schemas import Chunk, Generation, Intent, Understanding
from eval.questions import (
    Behavior,
    Category,
    Expect,
    Negative,
    ProbePurpose,
    Question,
    Source,
)
from eval.recording import (
    RecordedTurn,
    Recording,
    RecordingError,
    ReplayClient,
    record,
    sha256,
    stale_reasons,
)
from eval.report import RetrievalReport, markdown
from eval.retrieval import (
    Replayed,
    behavior_of,
    by_category,
    grade,
    percentile,
    probe_result,
    replay,
    score_spreads,
)

# The hashing test embedder scores on another scale than e5, so the threshold is off here.
_LOADED = load_settings()
SETTINGS = _LOADED.model_copy(
    update={"retrieval": _LOADED.retrieval.model_copy(update={"relevance_threshold": 0.0})}
)
REGISTRY = load_registry()
SYSTEM = understand_system(REGISTRY)
MODEL = "gpt-5.4-nano"
TEXTS = {
    "mg_s6": [("הטווח", "הטווח בפועל בנסיעה רגילה"), ("המחיר", "המחיר עם אבזור מלא")],
    "aion_ht": [("הטווח בפועל", "הטווח בפועל בנסיעה רגילה"), ("מחיר", "המחיר של הגרסה")],
    "kia_ev9": [("קיה EV9", "צריכת החשמל הממוצעת לאורך החודש")],
}
SECRET_TEXT = "הטווח בפועל בנסיעה רגילה"  # stands in for article text: never in a report


def _chunks() -> list[Chunk]:
    chunks = []
    for car_id, sections in TEXTS.items():
        car = REGISTRY.get(car_id)
        for index, (section, text) in enumerate(sections):
            chunks.append(
                Chunk(
                    chunk_id=f"{car_id}:{index:03d}",
                    car=car_id,
                    car_name=car.display_name,
                    section=section,
                    source_url=car.url,
                    published=date(2026, 1, 1),
                    text=text,
                    embed_text=f"{car.display_name} — {section}\n{text}",
                )
            )
    return chunks


class InMemoryStore:
    def __init__(self) -> None:
        self.embedder = FakeEmbedder()
        chunks = _chunks()
        vectors = self.embedder.embed_documents([c.embed_text for c in chunks])
        self.rows = list(zip(chunks, vectors, strict=True))

    def candidates(self, vector: Vector, car_ids: list[str] | None) -> list[tuple[Chunk, float]]:
        return [
            (chunk, round(sum(a * b for a, b in zip(vector, row, strict=True)), 6))
            for chunk, row in self.rows
            if car_ids is None or chunk.car in car_ids
        ]


STORE = InMemoryStore()
RETRIEVER = Retriever(STORE, STORE.embedder, SETTINGS.retrieval)


def make_pipeline(llm: LLMClient) -> Pipeline:
    return Pipeline(SETTINGS, REGISTRY, RETRIEVER, llm)


def understanding(
    question: str,
    cars: list[str],
    intent: Intent = Intent.FACT,
    unrecognized: list[str] | None = None,
) -> Understanding:
    return Understanding(
        intent=intent,
        cars=cars,
        unrecognized_cars=unrecognized or [],
        standalone_question=question,
        preference_updates=[],
    )


def question(
    qid: str,
    turns: list[str],
    behavior: Behavior = Behavior.ANSWER,
    sources: list[Source] | None = None,
    sources_any: list[Source] | None = None,
    category: Category = Category.SINGLE_FACT,
) -> Question:
    if behavior is Behavior.ANSWER and not (sources or sources_any):
        sources = [Source(car="mg_s6", section="הטווח")]  # an answer question must name one
    return Question(
        id=qid,
        category=category,
        turns=turns,
        expect=Expect(behavior=behavior, sources=sources or [], sources_any=sources_any or []),
        why="test",
    )


def recorded(*items: Understanding | None, turns: list[str]) -> list[RecordedTurn]:
    return [
        RecordedTurn(message_sha256=sha256(t), understanding=u)
        for t, u in zip(turns, items, strict=True)
    ]


def recording_for(cases: dict[str, list[RecordedTurn]]) -> Recording:
    return Recording(
        model=MODEL,
        understand_prompt="v1",
        understand_system_sha256=sha256(SYSTEM),
        recorded_at="2026-10-30T00:00:00+00:00",
        calls=0,
        tokens={"input": 0, "cached": 0, "output": 0},
        cost_usd=0.0,
        cases=cases,
    )


# ---------------------------------------------------------------- recording
def test_record_keeps_understand_outputs_and_skips_only_the_last_generation() -> None:
    case = question("q", ["ספר לי על MG S6", "ומה הטווח שלו?"])
    first = understanding("ספר על MG S6", ["mg_s6"])
    second = understanding("מה הטווח של MG S6?", ["mg_s6"])
    fake = FakeLLMClient([first, Generation(answer="תשובה קצרה בעברית", used_chunk_ids=[]), second])

    result = record([case], fake, make_pipeline, history_window=6, model=MODEL, system=SYSTEM)

    schemas = [call.schema for call in fake.calls]
    assert schemas == [Understanding, Generation, Understanding]  # no generation on the last turn
    # The second understand call saw the first answer as history.
    assert any(m["role"] == "assistant" for m in fake.calls[2].messages)
    turns = result.cases["q"]
    assert [t.understanding for t in turns] == [first, second]
    assert [t.message_sha256 for t in turns] == [sha256(m) for m in case.turns]
    assert stale_reasons(result, [case], system=SYSTEM, model=MODEL) == []


def test_record_stores_none_for_an_understand_fallback() -> None:
    case = question("q", ["מה הטווח של MG S6?"])
    fake = FakeLLMClient([LLMOutputError("invalid twice")])
    result = record([case], fake, make_pipeline, history_window=6, model=MODEL, system=SYSTEM)
    assert result.cases["q"][0].understanding is None


def test_record_stops_when_an_earlier_turn_fails() -> None:
    case = question("q", ["ספר לי על MG S6", "ומה הטווח שלו?"])
    fake = FakeLLMClient(
        [understanding("ספר על MG S6", ["mg_s6"]), LLMOutputError("generate failed")]
    )
    with pytest.raises(RecordingError, match="earlier turn"):
        record([case], fake, make_pipeline, history_window=6, model=MODEL, system=SYSTEM)


def test_stale_recording_is_explained() -> None:
    case = question("q", ["מה הטווח של MG S6?"])
    rec = recording_for({"q": recorded(None, turns=["שאלה אחרת"])})
    rec = rec.model_copy(update={"model": "other-model", "understand_system_sha256": "x"})
    reasons = stale_reasons(rec, [case, question("new", ["חדש"])], system=SYSTEM, model=MODEL)
    assert any("other-model" in r for r in reasons)
    assert any("registry" in r for r in reasons)
    assert "q: the turns changed" in reasons
    assert "new: not recorded" in reasons


# ---------------------------------------------------------------- replay and behavior
def test_replay_reaches_generation_without_calling_a_model() -> None:
    case = question("q", ["מה הטווח של MG S6?"])
    turns = recorded(understanding("מה הטווח של MG S6?", ["mg_s6"]), turns=case.turns)
    replayed = replay(case, turns, make_pipeline, 6)
    assert replayed.reached_generation
    assert behavior_of(replayed) == "answer"
    assert {hit.chunk.car for hit in replayed.answer.retrieved} == {"mg_s6"}
    assert replayed.answer.cost_usd == 0.0


def test_replay_maps_gate_refusals_and_out_of_scope() -> None:
    unknown = question("u", ["מה דעתך על טויוטה קורולה?"], Behavior.REFUSAL)
    turns = recorded(
        understanding("טויוטה קורולה", [], unrecognized=["טויוטה קורולה"]), turns=unknown.turns
    )
    assert behavior_of(replay(unknown, turns, make_pipeline, 6)) == "refusal"

    poem = question("p", ["תכתוב שיר על הים"], Behavior.OUT_OF_SCOPE)
    turns = recorded(understanding("שיר על הים", [], Intent.OUT_OF_SCOPE), turns=poem.turns)
    assert behavior_of(replay(poem, turns, make_pipeline, 6)) == "out_of_scope"


def test_replay_of_a_recorded_fallback_uses_the_raw_message() -> None:
    case = question("q", ["מה הטווח של MG S6?"])
    replayed = replay(case, recorded(None, turns=case.turns), make_pipeline, 6)
    assert "understand_fallback" in replayed.answer.flags
    assert replayed.reached_generation  # cars still come from name matching


def test_replay_client_refuses_extra_understand_calls() -> None:
    client = ReplayClient([])
    with pytest.raises(AssertionError):
        client.complete_json("s", [], Understanding, model=MODEL)


# ---------------------------------------------------------------- grading
def _graded(q: Question, plan: Understanding, runs: int = 1) -> Replayed:
    turns = recorded(plan, turns=q.turns)
    return replay(q, turns, make_pipeline, 6)


def test_grade_reports_ranks_and_car_ranks() -> None:
    q = question(
        "compare",
        ["מה ההבדל בטווח בין MG S6 לאיון HT?"],
        sources=[Source(car="mg_s6", section="הטווח"), Source(car="aion_ht", section="הטווח")],
        category=Category.COMPARISON,
    )
    plan = understanding("ההבדל בטווח בין MG S6 לאיון HT", ["mg_s6", "aion_ht"], Intent.COMPARE)
    result = grade(q, [_graded(q, plan), _graded(q, plan)], RETRIEVER)
    assert result.passed and result.stable
    for source in result.sources:
        assert source.hit and source.rank
        # Per-car retrieval returned every chunk of the car here, so its order is the car rank.
        own = [h.chunk_id for h in result.retrieved if h.chunk_id.startswith(source.car)]
        assert source.car_rank == own.index(result.retrieved[source.rank - 1].chunk_id) + 1
    assert result.reciprocal_rank is not None and 0 < result.reciprocal_rank <= 1
    assert len(result.retrieve_ms) == 2


def test_grade_names_each_failure() -> None:
    q = question(
        "miss",
        ["מה הטווח של MG S6?"],
        sources=[Source(car="kia_ev9", section="קיה EV9")],
        sources_any=[Source(car="aion_ht", section="מחיר")],
    )
    result = grade(q, [_graded(q, understanding("הטווח של MG S6", ["mg_s6"]))], RETRIEVER)
    assert not result.passed
    # Each miss names the source's rank within its car: a parameter or an embedding problem.
    assert "missed kia_ev9 / קיה EV9 (car rank 1)" in result.failures
    assert any(f.startswith("missed every sources_any alternative") for f in result.failures)
    assert result.reciprocal_rank == 0.0
    assert result.sources[0].car_rank == 1  # the right chunk exists; the plan picked another car


def test_grade_flags_a_wrong_behavior() -> None:
    q = question("r", ["מה דעתך על טויוטה קורולה?"], Behavior.REFUSAL)
    plan = understanding("טויוטה קורולה מול MG S6", ["mg_s6"])
    result = grade(q, [_graded(q, plan)], RETRIEVER)
    assert result.failures == ["behavior answer, expected refusal"]
    assert result.reciprocal_rank is None


def test_a_gate_refusal_contributes_no_retrieve_latency() -> None:
    q = question("r", ["מה דעתך על טויוטה קורולה?"], Behavior.REFUSAL)
    plan = understanding("טויוטה קורולה", [], unrecognized=["טויוטה קורולה"])
    result = grade(q, [_graded(q, plan), _graded(q, plan)], RETRIEVER)
    assert result.behavior == "refusal"
    assert result.retrieve_ms == []  # not two zeros


def test_summary_counts_a_sources_any_group_once() -> None:
    q = question(
        "any",
        ["מה הטווח של MG S6?"],
        sources_any=[Source(car="mg_s6", section="הטווח"), Source(car="aion_ht", section="מחיר")],
        category=Category.RECOMMENDATION,
    )
    result = grade(q, [_graded(q, understanding("הטווח של MG S6", ["mg_s6"]))], RETRIEVER)
    rows = by_category([result])
    assert [r.category for r in rows] == ["recommendation", "total"]
    assert (rows[-1].sources, rows[-1].sources_hit, rows[-1].passed) == (1, 1, 1)


def test_percentile_is_nearest_rank() -> None:
    assert percentile([], 50) is None
    assert percentile([5.0, 1.0, 3.0, 2.0, 4.0], 50) == 3.0
    assert percentile([float(v) for v in range(1, 21)], 95) == 19.0


def _probe(purpose: ProbePurpose, turns: list[str]) -> Negative:
    absent = ["ביטוח"] if purpose is ProbePurpose.THRESHOLD else []
    return Negative(id=f"neg-{purpose}", purpose=purpose, turns=turns, absent=absent, why="t")


def test_behavior_probes_are_graded_and_threshold_probes_feed_the_spread() -> None:
    off_topic = understanding("ביטוח לרכב", [], Intent.OUT_OF_SCOPE)
    behavior = _probe(ProbePurpose.BEHAVIOR, ["כמה עולה ביטוח לרכב?"])
    behavior_result = probe_result(
        behavior, replay(behavior, recorded(off_topic, turns=behavior.turns), make_pipeline, 6)
    )
    on_topic = understanding("ביטוח ל-MG S6", ["mg_s6"])
    threshold = _probe(ProbePurpose.THRESHOLD, ["כמה עולה ביטוח ל-MG S6?"])
    threshold_result = probe_result(
        threshold, replay(threshold, recorded(on_topic, turns=threshold.turns), make_pipeline, 6)
    )
    assert behavior_result.passed is True and behavior_result.best_score is None
    assert threshold_result.passed is None and threshold_result.best_score is not None

    q = question("q", ["מה הטווח של MG S6?"])
    answered = grade(q, [_graded(q, understanding("הטווח של MG S6", ["mg_s6"]))], RETRIEVER)
    spreads = score_spreads([answered], [behavior_result, threshold_result])
    assert spreads["answerable"].n == 1
    assert spreads["answerable"].median == round(answered.best_score or 0, 4)
    # The behavior probe has no score, so only the threshold probe is in the sample.
    assert spreads["threshold_probes"].n == 1
    assert spreads["threshold_probes"].max == round(threshold_result.best_score, 4)


def test_a_behavior_probe_that_reaches_retrieval_fails() -> None:
    plan = understanding("ביטוח", [])
    probe = _probe(ProbePurpose.BEHAVIOR, ["כמה עולה ביטוח?"])
    result = probe_result(probe, replay(probe, recorded(plan, turns=probe.turns), make_pipeline, 6))
    assert result.passed is False


def test_markdown_report_holds_metrics_and_no_chunk_text() -> None:
    q = question("q", ["מה הטווח של MG S6?"], sources=[Source(car="mg_s6", section="הטווח")])
    result = grade(q, [_graded(q, understanding("הטווח של MG S6", ["mg_s6"]))], RETRIEVER)
    plan = understanding("ביטוח", [])
    probe = _probe(ProbePurpose.BEHAVIOR, ["כמה עולה ביטוח?"])
    probes = [
        probe_result(probe, replay(probe, recorded(plan, turns=probe.turns), make_pipeline, 6))
    ]
    report = RetrievalReport(
        created="2026-10-30T00:00:00+00:00",
        embedder={"provider": "fake", "model": "fake", "revision": None},
        retrieval=SETTINGS.retrieval,
        chunking=SETTINGS.chunking.model_dump(),
        recording={"model": MODEL, "understand_prompt": "v1", "recorded_at": "x", "cost_usd": 0},
        runs=1,
        warm_up_s=0.0,
        latency_ms={"p50": 1.0, "p95": 2.0},
        summary=by_category([result]),
        scores=score_spreads([result], probes),
        questions=[result],
        probes=probes,
    )
    text = markdown(report) + report.model_dump_json()
    assert "| q | single_fact | answer |" in text
    assert "| neg-behavior | behavior | answer | fact |" in text
    assert "| threshold_probes | 0 |" in text
    assert SECRET_TEXT not in text
