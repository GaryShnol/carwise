"""Checks the eval question set against itself and against the real corpus.

Why: a question whose "required fact" is not in the articles can never pass, and one
that expects the wrong car hides a bug. The corpus checks run only when the articles
are cached locally. Assertions are counts and booleans so that a failure never prints
article text into logs (the repository is public).
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

import pytest

from carwise import guardrails
from carwise.ingest.clean import BlockKind, Document, clean_html
from carwise.registry import load_registry
from eval.questions import (
    Behavior,
    Category,
    ProbePurpose,
    Question,
    load_negatives,
    load_questions,
)

RAW_DIR = Path("data/raw")
MIN_TRAPS = 4
MIN_QUESTIONS = 15


def test_question_set_loads_and_is_balanced() -> None:
    questions = load_questions().questions
    counts = Counter(question.category for question in questions)
    assert len(questions) >= MIN_QUESTIONS
    assert set(counts) == set(Category)
    assert counts[Category.TRAP] >= MIN_TRAPS


def test_expected_cars_exist_in_the_registry() -> None:
    known = {car.id for car in load_registry().cars}
    used = {
        source.car
        for question in load_questions().questions
        for source in (*question.expect.sources, *question.expect.sources_any)
    }
    assert used <= known


def test_there_is_a_multi_turn_preference_scenario() -> None:
    scenarios = [q for q in load_questions().questions if q.expect.preferences]
    assert scenarios
    assert all(len(q.turns) >= 3 for q in scenarios)


def test_negative_probes_load_and_never_share_an_id_with_a_question() -> None:
    # The recording keys questions and probes in one map, so a shared id would overwrite one.
    probes = load_negatives().probes
    assert probes
    question_ids = {question.id for question in load_questions().questions}
    assert not question_ids & {probe.id for probe in probes}


def test_behavior_probes_name_no_car_and_threshold_probes_name_one() -> None:
    # A behavior probe that named a car would test the registry gate; a threshold probe
    # must name exactly one car so the understand step sends it to that car's chunks.
    registry = load_registry()
    for probe in load_negatives().probes:
        cars = {car for turn in probe.turns for car in guardrails.cars_in_text(turn, registry)}
        expected = 0 if probe.purpose is ProbePurpose.BEHAVIOR else 1
        assert len(cars) == expected, probe.id


def test_absent_patterns_compile() -> None:
    for probe in load_negatives().probes:
        for pattern in probe.absent:
            re.compile(pattern)


def test_trap_set_covers_the_required_kinds() -> None:
    behaviors = Counter(
        q.expect.behavior for q in load_questions().questions if q.category is Category.TRAP
    )
    assert behaviors[Behavior.REFUSAL] >= 1
    assert behaviors[Behavior.OUT_OF_SCOPE] >= 1
    assert behaviors[Behavior.ANSWER] >= 3  # missing detail, mixing, partial


def test_regexes_compile() -> None:
    for question in load_questions().questions:
        for pattern in question.expect.must_not_match:
            re.compile(pattern)


# ---------------------------------------------------------------- corpus consistency
def _documents() -> dict[str, Document]:
    docs: dict[str, Document] = {}
    for car in load_registry().cars:
        path = RAW_DIR / f"{car.slug}.html"
        if not path.exists():
            pytest.skip("articles are not cached in data/raw")
        html = path.read_text(encoding="utf-8")
        docs[car.id] = clean_html(html, car_id=car.id, source_url=car.url)
    return docs


def _section_texts(doc: Document) -> dict[str, str]:
    """Heading text -> everything under it. The Kia report is one section named by its title."""
    sections: dict[str, list[str]] = {}
    current = doc.title
    sections[current] = []
    for block in doc.blocks:
        if block.kind is BlockKind.HEADING and block.level != 1:
            current = block.text
            sections.setdefault(current, [])
        else:
            sections[current].append(block.text)
    return {name: " ".join([name, *texts]) for name, texts in sections.items()}


def _find_section(doc: Document, fragment: str) -> str | None:
    matches = [text for name, text in _section_texts(doc).items() if fragment in name]
    return " ".join(matches) if matches else None


def _all_text(doc: Document) -> str:
    return " ".join(block.text for block in doc.blocks)


def _questions_with_sources() -> list[Question]:
    return [q for q in load_questions().questions if q.expect.behavior is Behavior.ANSWER]


def test_every_expected_section_exists() -> None:
    docs = _documents()
    missing = 0
    for question in _questions_with_sources():
        for source in (*question.expect.sources, *question.expect.sources_any):
            if _find_section(docs[source.car], source.section) is None:
                missing += 1
    assert missing == 0


def test_required_facts_are_in_the_expected_cars_articles() -> None:
    """Each must_include group needs an alternative somewhere in the sources' articles."""
    docs = _documents()
    unsupported = []
    for question in _questions_with_sources():
        if question.category in (Category.RANKING, Category.TRAP, Category.RECOMMENDATION):
            continue  # ranking, trap and recommendation groups are checked on their own below
        cars = {s.car for s in (*question.expect.sources, *question.expect.sources_any)}
        corpus = " ".join(_all_text(docs[car]) for car in cars)
        for group in question.expect.must_include:
            if not any(alt in corpus for alt in group):
                unsupported.append(question.id)
    assert unsupported == []


def test_ranking_and_recommendation_facts_are_supported() -> None:
    """These questions span cars, so their keywords are looked up in the whole corpus."""
    docs = _documents()
    corpus = " ".join(_all_text(doc) for doc in docs.values())
    notice = load_questions().shared["eight_cars"]  # a required statement, not an article fact
    unsupported = []
    for question in load_questions().questions:
        if question.category not in (Category.RANKING, Category.RECOMMENDATION):
            continue
        for group in question.expect.must_include:
            if group != notice and not any(alt in corpus for alt in group):
                unsupported.append(question.id)
    assert unsupported == []


def test_forbidden_strings_do_not_belong_to_the_expected_car() -> None:
    """A must_not_include value must not be a fact of the car the question is about."""
    docs = _documents()
    leaks = []
    for question in _questions_with_sources():
        cars = {s.car for s in (*question.expect.sources, *question.expect.sources_any)}
        corpus = " ".join(_all_text(docs[car]) for car in cars)
        for forbidden in question.expect.must_not_include:
            if forbidden in corpus:
                leaks.append(question.id)
    assert leaks == []


def test_ranking_claims_hold_across_the_whole_corpus() -> None:
    """Fastest and cheapest are computed from the spec tables, not assumed."""
    docs = _documents()

    def table_value(doc: Document, label: str) -> float | None:
        for block in doc.blocks:
            if block.kind is BlockKind.TABLE_ROW and block.text.startswith(label):
                number = re.search(r"[\d,]+(?:\.\d+)?", block.text.split(":", 1)[1])
                if number:
                    return float(number.group().replace(",", ""))
        return None

    zero_to_hundred = {c: table_value(d, '0 ל-100 קמ"ש') for c, d in docs.items()}
    prices = {c: table_value(d, "מחיר") for c, d in docs.items()}
    fastest = min((v, c) for c, v in zero_to_hundred.items() if v is not None)[1]
    cheapest = min((v, c) for c, v in prices.items() if v is not None)[1]
    assert fastest == "audi_rs3"
    assert cheapest == "citroen_c3"
    assert prices["kia_ev9"] is None  # the ranking question relies on the Kia having no price


def test_trap_premises_hold() -> None:
    """The things the traps say are absent really are absent, and the mixed-up ones differ."""
    docs = _documents()
    corpus = {car: _all_text(doc) for car, doc in docs.items()}
    everything = " ".join(corpus.values())
    assert "קורולה" not in everything  # Toyota Corolla: not in any article
    assert not re.search(r'\d+\s*כ["”״]ס', corpus["kia_ev9"])  # the Kia report states no power
    assert "72.7" in corpus["aion_ht"] and "72.7" not in corpus["mg_s6"]
    assert "77" in corpus["mg_s6"]
    assert "144" in corpus["mg_s6"] and "163" in corpus["aion_ht"]
    assert "144" not in corpus["link_and_co_01"] and "163" not in corpus["link_and_co_01"]
    assert "אינו מציע אפשרות לטעינה מהירה" in corpus["link_and_co_01"]
    assert "X5" in corpus["genesis_gv80"]  # named as a rival, with no price of its own
    assert "טסלה מודל 3" in corpus["aion_ht"]  # rival mentioned only by name


def test_threshold_probes_ask_about_something_their_car_article_lacks() -> None:
    """The absence each threshold probe claims is checked against the cleaned article."""
    docs = _documents()
    registry = load_registry()
    present = []
    for probe in load_negatives().probes:
        if probe.purpose is not ProbePurpose.THRESHOLD:
            continue
        (car,) = {c for turn in probe.turns for c in guardrails.cars_in_text(turn, registry)}
        text = _all_text(docs[car])
        present += [probe.id for pattern in probe.absent if re.search(pattern, text)]
    assert present == []
