"""Answer level of the eval (CW-302): checks, attribution, judge and the run, all offline.

Synthetic chunk text only (the repository is public); car ids and names come from the
registry because the pipeline resolves names through it. The LLM is the fake client.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from carwise.config import load_settings
from carwise.llm.base import BudgetExceededError
from carwise.llm.fake import FakeLLMClient
from carwise.pipeline import Pipeline
from carwise.registry import load_registry
from carwise.retrieval.embedder import FakeEmbedder, Vector
from carwise.retrieval.retriever import Retriever
from carwise.schemas import (
    Chunk,
    Generation,
    Intent,
    Preference,
    Preferences,
    RetrievedChunk,
    Understanding,
)
from eval.answer import (
    another_article_count,
    attribution_problems,
    checks_for,
    play,
    preference_checks,
)
from eval.answer_report import markdown, run_answer_eval
from eval.judge import Verdict, criteria_version, judge, judge_input
from eval.questions import Behavior, Category, Expect, Question, Source

REGISTRY = load_registry()
LOADED = load_settings()
SETTINGS = LOADED.model_copy(  # the hashing embedder scores on another scale: no threshold
    update={"retrieval": LOADED.retrieval.model_copy(update={"relevance_threshold": 0.0})}
)
SECRET = "טקסט המבחן הסודי"  # stands in for article text: never in a committed report


def _chunk(car_id: str, index: int, text: str, section: str = "מחיר") -> Chunk:
    car = REGISTRY.get(car_id)
    return Chunk(
        chunk_id=f"{car_id}:{index:03d}",
        car=car_id,
        car_name=car.display_name,
        section=section,
        source_url=car.url,
        published=date(2026, 1, 1),
        text=text,
        embed_text=text,
    )


CHUNKS = [
    _chunk("mg_s6", 0, f"המחיר 168,888 שקלים. {SECRET}"),
    _chunk("aion_ht", 0, "המחיר 179,990 שקלים"),
]
HITS = [RetrievedChunk(chunk=c, score=0.9) for c in CHUNKS]


# ---------------------------------------------------------------- attribution
def test_numbers_with_their_own_car_pass() -> None:
    answer = (
        "MG S6 עולה 168,888 שקלים (MG S6, מחיר), ואילו איון HT עולה 179,990 שקלים "
        "(GAC איון HT, מחיר)."
    )
    assert attribution_problems(answer, HITS, [], REGISTRY) == []


def test_a_swapped_price_is_caught_by_the_citation_that_follows_it() -> None:
    answer = "MG S6 עולה 179,990 שקלים (MG S6, מחיר). איון HT עולה 168,888 (GAC איון HT, מחיר)."
    found = attribution_problems(answer, HITS, [], REGISTRY)
    assert [(p.number, p.placed_with, p.backed_by) for p in found] == [
        ("179,990", "mg_s6", ["aion_ht"]),
        ("168,888", "aion_ht", ["mg_s6"]),
    ]


def test_without_citations_the_car_named_before_the_number_owns_it() -> None:
    answer = "ל-MG S6 המחיר 179,990 ולאיון HT המחיר 168,888."
    found = attribution_problems(answer, HITS, [], REGISTRY)
    assert {(p.number, p.placed_with) for p in found} == {
        ("179,990", "mg_s6"),
        ("168,888", "aion_ht"),
    }


def test_numbers_the_user_stated_or_one_car_only_are_not_attribution_problems() -> None:
    answer = "MG S6 עולה 179,990 (MG S6, מחיר)."
    assert attribution_problems(answer, HITS, ["האם 179,990 זה המחיר?"], REGISTRY) == []
    assert attribution_problems(answer, HITS[:1], [], REGISTRY) == []  # one car retrieved


FAMILY_HITS = [
    RetrievedChunk(chunk=_chunk("mg_s6", 0, "מרחב ראוי לנוסעים"), score=0.9),
    RetrievedChunk(chunk=_chunk("hyundai_elantra_n", 0, "תיבה של 5 הילוכים"), score=0.9),
]
FAMILY_ANSWER = "MG S6 מתאים למשפחה של 5 (MG S6, מרחב)."


def test_a_number_the_user_wrote_as_a_word_is_the_users() -> None:
    assert (
        attribution_problems(FAMILY_ANSWER, FAMILY_HITS, ["אנחנו משפחה של חמישה"], REGISTRY) == []
    )
    assert attribution_problems(FAMILY_ANSWER, FAMILY_HITS, ["ולחמישה נוסעים"], REGISTRY) == []


def test_a_number_word_the_user_did_not_write_does_not_cover_the_number() -> None:
    found = attribution_problems(FAMILY_ANSWER, FAMILY_HITS, ["אנחנו משפחה של ארבעה"], REGISTRY)
    assert [(p.number, p.placed_with, p.backed_by) for p in found] == [
        ("5", "mg_s6", ["hyundai_elantra_n"])
    ]


def test_another_article_phrasings_are_counted() -> None:
    assert another_article_count("לפי הנתונים בכתבה אחרת, ובמאמר אחר") == 2
    assert another_article_count("בכתבה על MG S6") == 0


# ---------------------------------------------------------------- preferences
def test_preference_checks_parse_numbers_words_and_hint_words() -> None:
    profile = Preferences(
        budget=Preference(value="עד 190 אלף שקל", source="m"),
        powertrain=Preference(value="חשמלי", source="m"),
        passengers=Preference(value="חמישה נוסעים", source="m"),
    )
    want = {"powertrain": "electric", "budget_max_nis": 190000, "passengers": 5}
    assert all(c.passed for c in preference_checks(want, profile, SETTINGS))
    empty = preference_checks(want, Preferences(), SETTINGS)
    assert [c.passed for c in empty] == [False, False, False]


# ---------------------------------------------------------------- checks through the pipeline
class InMemoryStore:
    def __init__(self) -> None:
        self.embedder = FakeEmbedder()
        vectors = self.embedder.embed_documents([c.embed_text for c in CHUNKS])
        self.rows = list(zip(CHUNKS, vectors, strict=True))

    def candidates(self, vector: Vector, car_ids: list[str] | None) -> list[tuple[Chunk, float]]:
        return [
            (chunk, round(sum(a * b for a, b in zip(vector, row, strict=True)), 6))
            for chunk, row in self.rows
            if car_ids is None or chunk.car in car_ids
        ]


STORE = InMemoryStore()
RETRIEVER = Retriever(STORE, STORE.embedder, SETTINGS.retrieval)
COMPARE = Question(
    id="compare-cheaper",
    category=Category.COMPARISON,
    turns=["מה זול יותר, MG S6 או איון HT?"],
    expect=Expect(
        behavior=Behavior.ANSWER,
        sources=[Source(car="mg_s6", section="מחיר"), Source(car="aion_ht", section="מחיר")],
        must_include=[["168,888"], ["179,990"]],
        must_not_include=["187,000"],
    ),
    why="test",
)
PLAN = Understanding(
    intent=Intent.COMPARE,
    cars=["mg_s6", "aion_ht"],
    unrecognized_cars=[],
    standalone_question="מה זול יותר, MG S6 או איון HT?",
    preference_updates=[],
)
GOOD = Generation(
    answer="MG S6 זולה יותר: 168,888 שקלים (MG S6, מחיר) מול 179,990 (GAC איון HT, מחיר).",
    used_chunk_ids=["mg_s6:000", "aion_ht:000"],
)


def _pipeline(llm: FakeLLMClient) -> Pipeline:
    return Pipeline(SETTINGS, REGISTRY, RETRIEVER, llm)


def test_a_good_comparison_passes_every_check() -> None:
    played = play(COMPARE, _pipeline(FakeLLMClient([PLAN, GOOD])), 6)
    checks = {c.name: c for c in checks_for(COMPARE, played, SETTINGS, REGISTRY)}
    assert set(checks) == {
        "behavior", "sources_cited", "must_include", "must_not_include",
        "post_check", "another_article", "attribution",
    }  # fmt: skip
    assert all(c.passed for c in checks.values()), checks


def test_missing_citation_and_keyword_are_reported_by_name() -> None:
    thin = Generation(answer="MG S6 זולה יותר (MG S6, מחיר).", used_chunk_ids=["mg_s6:000"])
    played = play(COMPARE, _pipeline(FakeLLMClient([PLAN, thin])), 6)
    failed = {
        c.name: c.detail for c in checks_for(COMPARE, played, SETTINGS, REGISTRY) if not c.passed
    }
    assert failed["sources_cited"] == "aion_ht"
    assert "must_include" in failed


# ---------------------------------------------------------------- judge
def test_judge_returns_the_verdict_and_its_cost() -> None:
    played = play(COMPARE, _pipeline(FakeLLMClient([PLAN, GOOD])), 6)
    client = FakeLLMClient([Verdict(passed=True, reason="MG S6 is cheaper.")])
    verdict = judge(client, "gpt-5.4", "MG S6 is cheaper.", COMPARE.turns, played.last)
    assert verdict.passed is True
    message = client.calls[0].messages[0]["content"]
    assert "Criterion:" in message and "<excerpt car=" in message


def test_judge_that_cannot_answer_yields_no_verdict() -> None:
    played = play(COMPARE, _pipeline(FakeLLMClient([PLAN, GOOD])), 6)
    client = FakeLLMClient([BudgetExceededError("cap reached")])
    verdict = judge(client, "gpt-5.4", "criterion", COMPARE.turns, played.last)
    assert verdict.passed is None and "not judged" in verdict.reason
    assert "<answer>" in judge_input("c", COMPARE.turns, played.last)


# ---------------------------------------------------------------- the run and its reports
def test_run_keeps_answers_out_of_the_committed_report(tmp_path: Path) -> None:
    llm = FakeLLMClient([PLAN, GOOD])
    report = run_answer_eval(
        [COMPARE],
        lambda: _pipeline(llm),
        None,
        SETTINGS,
        REGISTRY,
        profile="dev",
        models={"understand": "m", "generate": "m", "judge": "j"},
        runs=1,
        question_set="tuning",
        runs_dir=tmp_path / "runs",
    )
    assert report.complete and report.questions[0].passed_runs == 1
    assert report.prompts["judge_criteria"] == criteria_version() == "v2"
    committed = markdown(report) + report.model_dump_json()
    assert SECRET not in committed and "זולה יותר" not in committed
    logged = (tmp_path / "runs" / "answers.jsonl").read_text(encoding="utf-8")
    assert json.loads(logged)["turns"][0]["answer"] == GOOD.answer  # kept locally, gitignored
