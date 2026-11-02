"""Adversarial post-check set (CW-619): what the post-check catches, and what it misses.

Each case in eval/postcheck_cases.yaml states the outcome today's code gives. A
weaker check fails a caught case; a fixed gap fails a pinned miss until the case
is updated, so the published recall can never drift from the code.
"""

import pytest

from carwise.config import load_settings
from carwise.guardrails import unsupported_cars, unsupported_numbers
from carwise.llm.fake import FakeLLMClient
from carwise.pipeline import Pipeline
from carwise.registry import load_registry
from carwise.schemas import (
    CheckFindings,
    Generation,
    Intent,
    PostCheckOutcome,
    RefusalReason,
    Understanding,
)
from eval.postcheck import (
    REPORT_PATH,
    Case,
    FixedRetriever,
    hits_for,
    load_cases,
    markdown,
    run_all,
    run_case,
)

SETTINGS = load_settings()
REGISTRY = load_registry()
CASES = load_cases()


def direct(case: Case) -> CheckFindings:
    """The two post-check functions called directly, as the pipeline calls them."""
    hits = hits_for(case, REGISTRY)
    config = SETTINGS.guardrails
    cars = unsupported_cars(case.answer, hits, case.unrecognized, REGISTRY, config.outside_brands)
    found = unsupported_numbers(
        case.answer, hits, [case.message], REGISTRY, config.numbers_always_allowed
    )
    return CheckFindings(cars=cars, numbers=found)


def test_the_set_has_bad_cases_and_controls_of_every_planned_kind() -> None:
    kinds = {case.kind for case in CASES}
    assert 15 <= len(CASES) <= 30
    assert {"outside_brand", "corpus_car", "sibling_model", "brandless_model"} <= kinds
    assert {"alias_collision", "hebrew_prefix", "cross_car_number", "control"} <= kinds
    assert {"invented_number", "rewrite_number", "number_precision", "number_words"} <= kinds
    assert sum(not case.bad for case in CASES) >= 5
    assert all(not case.flagged for case in CASES if not case.bad)  # controls must stay clean


@pytest.mark.parametrize("case", CASES, ids=[case.id for case in CASES])
def test_post_check_functions_give_the_declared_outcome(case: Case) -> None:
    assert direct(case).suspect is case.flagged, case.note or case.kind


@pytest.mark.parametrize("case", CASES, ids=[case.id for case in CASES])
def test_pipeline_gives_the_declared_outcome(case: Case) -> None:
    result = run_case(case, SETTINGS, REGISTRY)
    assert result.findings == direct(case)  # the pipeline checks what the functions check
    if case.flagged:
        # Scripted bad twice: one regenerate, then the code-built reply, never a third call.
        assert result.outcome is PostCheckOutcome.FALLBACK and result.llm_calls == 3
    else:
        assert result.outcome is PostCheckOutcome.CLEAN and result.llm_calls == 2


def test_number_only_in_the_rewrite_is_caught_end_to_end() -> None:
    # CR-003: the rewrite states 350, the user did not; the pipeline must not count it.
    case = next(case for case in CASES if case.kind == "rewrite_number")
    assert case.rewrite and "350" in case.rewrite and "350" not in case.message
    assert run_case(case, SETTINGS, REGISTRY).findings.numbers == ["350"]


@pytest.mark.parametrize("case_id", ["invented-price", "alias-audi-s6"])
def test_caught_answer_is_replaced_by_a_clean_regeneration(case_id: str) -> None:
    case = next(case for case in CASES if case.id == case_id)
    hits = hits_for(case, REGISTRY)
    plan = Understanding(
        intent=Intent.FACT,
        cars=list(case.chunks),
        unrecognized_cars=[],
        standalone_question=case.message,
        preference_updates=[],
    )
    ids = [hits[0].chunk.chunk_id]
    good = Generation(answer="המחיר והטווח מופיעים בכתבה (MG S6, פרק 0).", used_chunk_ids=ids)
    bad = Generation(answer=case.answer, used_chunk_ids=ids)
    llm = FakeLLMClient([plan, bad, good])
    answer = Pipeline(SETTINGS, REGISTRY, FixedRetriever(hits), llm).ask(case.message, [])

    assert answer.refusal is None and answer.text == good.answer
    assert answer.post_check is not None
    assert answer.post_check.outcome is PostCheckOutcome.REGENERATED
    assert answer.post_check.attempts[0].suspect and not answer.post_check.attempts[1].suspect


def test_caught_answer_never_reaches_the_user() -> None:
    case = next(case for case in CASES if case.id == "outside-brand-hebrew")
    hits = hits_for(case, REGISTRY)
    plan = Understanding(
        intent=Intent.FACT,
        cars=list(case.chunks),
        unrecognized_cars=[],
        standalone_question=case.message,
        preference_updates=[],
    )
    bad = Generation(answer=case.answer, used_chunk_ids=[hits[0].chunk.chunk_id])
    llm = FakeLLMClient([plan, bad, bad])
    answer = Pipeline(SETTINGS, REGISTRY, FixedRetriever(hits), llm).ask(case.message, [])
    assert answer.refusal is RefusalReason.UNVERIFIED and "טויוטה" not in answer.text


def test_committed_report_matches_the_cases() -> None:
    # Regenerate with `uv run python -m eval.postcheck` after changing a case or the check.
    assert REPORT_PATH.read_text(encoding="utf-8") == markdown(run_all(SETTINGS, REGISTRY))
