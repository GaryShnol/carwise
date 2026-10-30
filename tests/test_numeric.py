"""Numeric post-check: every number in an answer is stated by a chunk or the user (CW-206).

Synthetic chunk text only; the false-positive suite over the real articles is in
tests/test_numeric_integration.py.
"""

import json
from pathlib import Path

import pytest

from carwise.config import load_settings
from carwise.guardrails import unsupported_numbers
from carwise.numbers import find_numbers
from carwise.prompts import PROMPT_DIR, PROMPT_VERSIONS, regenerate_instruction
from carwise.registry import load_registry
from carwise.schemas import CheckFindings, PostCheckOutcome, RefusalReason, RetrievedChunk
from carwise.telemetry import TurnLogger
from tests.test_pipeline import generation, make, understanding
from tests.test_postcheck import hit

REGISTRY = load_registry()
ALLOWED = load_settings().guardrails.numbers_always_allowed


def check(
    answer: str, chunk_texts: list[str] | str, user: list[str] | None = None, car: str = "mg_s6"
) -> list[str]:
    texts = [chunk_texts] if isinstance(chunk_texts, str) else chunk_texts
    hits: list[RetrievedChunk] = [hit(car, text) for text in texts]
    return unsupported_numbers(answer, hits, user or [], REGISTRY, ALLOWED)


# --- basic -------------------------------------------------------------------------------
def test_number_stated_in_the_chunk_passes() -> None:
    assert check('הטווח הוא 400 ק"מ (MG S6, פרק).', "הטווח בפועל הוא 400 קילומטר") == []


def test_invented_number_is_flagged_as_written() -> None:
    assert check('הטווח הוא 450 ק"מ.', "הטווח בפועל הוא 400 קילומטר") == ["450"]


def test_each_invented_number_is_reported_once() -> None:
    assert check("450 ו-450, ואז 512.", "הטווח הוא 400") == ["450", "512"]


# --- decimal comma and point -------------------------------------------------------------
@pytest.mark.parametrize(
    ("answer", "source"),
    [("3,8 שניות", "3.8 שניות"), ("3.8 שניות", "3,8 שניות"), ("3.8 שניות", "3.8 שניות")],
)
def test_decimal_comma_and_point_are_the_same_number(answer: str, source: str) -> None:
    assert check(f"תאוצה ל-100 ב-{answer}.", f"0 ל-100 קמ״ש ב-{source}") == []


def test_answer_may_round_but_not_add_precision() -> None:
    assert check("3.8 שניות", "3.79 שניות") == []  # rounded to what the answer wrote
    assert check("3.85 שניות", "3.8 שניות") == ["3.85"]  # precision the source lacks
    assert check("3.9 שניות", "3.8 שניות") == ["3.9"]


# --- thousands separators and scale words -------------------------------------------------
@pytest.mark.parametrize("written", ["178,888", "178888", "₪178,888", "178 אלף", "179 אלף"])
def test_thousands_formats_match_a_comma_grouped_price(written: str) -> None:
    assert check(f"המחיר הוא {written} ש״ח.", "המחיר: ₪178,888") == []


@pytest.mark.parametrize("written", ["178,000", "178000", "178 אלף"])
def test_a_price_stated_in_thousands_backs_the_same_round_number(written: str) -> None:
    assert check(f'המחיר הוא {written} ש"ח.', "המחיר עומד על 178 אלף שקלים") == []


def test_exact_figure_is_flagged_when_the_source_gives_only_thousands() -> None:
    assert check('המחיר הוא 178,888 ש"ח.', "המחיר עומד על 178 אלף שקלים") == ["178,888"]


def test_wrong_thousands_figure_is_flagged() -> None:
    assert check("המחיר הוא 185 אלף שקל.", "המחיר: ₪178,888") == ["185 אלף"]
    assert check("המחיר הוא 180 אלף שקל.", "המחיר: ₪178,888") == ["180 אלף"]
    assert check("המחיר הוא 177 אלף שקל.", "המחיר: ₪178,888") == ["177 אלף"]


def test_millions() -> None:
    assert check("נמכרו 1.5 מיליון יחידות.", "נמכרו 1,500,000 יחידות") == []
    assert check("נמכרו 2 מיליון יחידות.", "נמכרו 1,500,000 יחידות") == []  # rounded
    assert check("נמכרו 3 מיליון יחידות.", "נמכרו 1,500,000 יחידות") == ["3 מיליון"]


def test_thousands_written_with_a_point_is_read_both_ways() -> None:
    assert check("המחיר 1.060 שקל בחודש.", "החל מ-₪1,060") == []


# --- ranges -------------------------------------------------------------------------------
@pytest.mark.parametrize("written", ["420-440", "420–440", "420 עד 440", "בין 420 ל-440"])
def test_range_in_any_form_matches(written: str) -> None:
    assert check(f'טווח של {written} ק"מ.', "בחורף מתקבל כ-420–440 ק”מ") == []


def test_range_with_one_invented_end_flags_that_end() -> None:
    assert check('טווח של 420-480 ק"מ.', "בחורף מתקבל כ-420–440 ק”מ") == ["480"]


def test_tyre_size_reads_as_its_parts() -> None:
    assert check("צמיגים במידה 265/30-19.", "צמיגים רחבים יותר: 265/30-19 מלפנים") == []


# --- units and percent --------------------------------------------------------------------
@pytest.mark.parametrize(
    ("answer", "source"),
    [
        ('400 ק"מ', "400 ק”מ"),
        ('114,990 ש"ח', "₪114,990"),
        ('400 כ"ס', "400 כ״ס"),
        ('77 קוט"ש', "סוללה של 77 קוט״ש"),
        ("9.8 שניות", "הביצועים: 9.8 שניות ל-100"),
        ("85%", "כ-85% מהטווח המוצהר"),
    ],
)
def test_units_do_not_change_the_number(answer: str, source: str) -> None:
    assert check(f"הנתון: {answer}.", source) == []


def test_unit_conversion_is_not_backed() -> None:
    # The article says 400 hp; 294 kW is the model's own arithmetic.
    assert check("הספק של 294 קילוואט.", 'המנוע מייצר 400 כ"ס') == ["294"]


def test_wrong_percent_is_flagged() -> None:
    assert check("כ-90% מהטווח.", "כ-85% מהטווח המוצהר") == ["90"]


# --- numbers inside car names -------------------------------------------------------------
@pytest.mark.parametrize(
    "answer",
    [
        "ל-MG S6 יש טווח טוב.",
        "סיטרואן C3 נוחה בעיר, וה-C3 גם זולה.",
        "ג'נסיס GV80 מפנקת, ולג׳נסיס GV80 יש מושב שלישי.",
        "אודי RS3 מהירה, וה-RS3 רועשת.",
        "קיה EV9 גדולה, ובקיה EV9 שבעה מושבים.",
        "לינק אנד קו 01 היא היברידית נטענת, וה-01 שקטה.",
        "איון HT, ומתחרות כמו BMW X5 ואאודי Q8.",
    ],
)
def test_numbers_in_car_names_are_not_claims(answer: str) -> None:
    assert check(answer, "טקסט בלי מספרים") == []


# --- dates, ordinals and list markers -----------------------------------------------------
def test_years_in_the_chunk_count_as_chunk_numbers() -> None:
    source = "הדור הרביעי הוצג ב-2020, ומתיחת הפנים הגיעה ב-2024."
    assert check("הדגם הוצג ב-2020 וחודש ב-2024.", source) == []
    assert check("הדגם הוצג ב-2019.", source) == ["2019"]


def test_section_and_car_name_are_sources_too() -> None:
    # The model sees each excerpt labeled with its car and section ("פרק" in `hit`).
    assert check("לפי הכתבה, 400.", "פסקה", car="mg_s6") == ["400"]
    assert check("סיכום 2026.", "פסקה") == ["2026"]


def test_ordinal_words_are_not_numbers() -> None:
    assert find_numbers("הדור השלישי, הראשון בסדרה, ובשורה השנייה") == []


def test_list_markers_are_not_claims() -> None:
    answer = '1. טווח של 400 ק"מ\n2) מחיר של 180 אלף'
    assert check(answer, 'טווח של 400 ק"מ ומחיר של 180 אלף שקל') == []


def test_lap_time_may_drop_the_fraction() -> None:
    assert check("הקפה ב-7:33 דקות.", "נורבורגרינג, 7:33.23 דקות") == []


def test_zero_of_zero_to_hundred_needs_no_source() -> None:
    assert check("0-100 ב-3.8 שניות.", "תאוצה ל-100 קמ״ש ב-3.8 שניות") == []


# --- the user's own numbers ---------------------------------------------------------------
def test_number_from_the_users_question_passes() -> None:
    answer = "בתקציב של 200 אלף, MG S6 עולה 180 אלף."
    assert check(answer, "המחיר 180 אלף שקל", user=["יש לי עד 200 אלף"]) == []
    assert check(answer, "המחיר 180 אלף שקל") == ["200 אלף"]


# --- derived numbers ----------------------------------------------------------------------
SOURCES = ["MG S6 עולה 180 אלף שקל", "איון HT עולה 170 אלף שקל"]


def test_difference_is_allowed_when_both_operands_are_in_the_answer() -> None:
    answer = "MG S6 עולה 180 אלף ואיון HT עולה 170 אלף, הפרש של 10 אלף."
    assert check(answer, SOURCES) == []


def test_sum_is_allowed_when_both_operands_are_in_the_answer() -> None:
    answer = "יחד: 180 אלף ועוד 170 אלף הם 350 אלף."
    assert check(answer, SOURCES) == []


def test_difference_without_its_operands_is_flagged() -> None:
    assert check("MG S6 יקרה ב-10 אלף מאיון HT.", SOURCES) == ["10 אלף"]


def test_difference_with_one_operand_is_flagged() -> None:
    assert check("MG S6 עולה 180 אלף, יקרה ב-10 אלף.", SOURCES) == ["10 אלף"]


def test_rounded_difference_of_exact_prices_is_allowed() -> None:
    answer = "₪178,888 מול ₪174,000: הפרש של כ-5 אלף."
    assert check(answer, ["המחיר: ₪178,888", "המחיר: ₪174,000"]) == []


def test_operands_must_come_from_the_chunks_not_the_user() -> None:
    answer = "בתקציב 200 אלף ובמחיר 180 אלף נשארים 20 אלף."
    assert check(answer, "המחיר 180 אלף", user=["עד 200 אלף"]) == ["20 אלף"]


# --- regenerate or fall back (reuses CW-202's path) ---------------------------------------
QUESTION = "כמה טווח יש ל-MG S6?"
INVENTED = generation('הטווח בפועל הוא 520 ק"מ (MG S6, פרק 0).')
GOOD = generation()


def test_invented_number_is_regenerated_once_with_the_reason() -> None:
    pipeline, llm, _ = make([understanding(cars=["mg_s6"]), INVENTED, GOOD])
    answer = pipeline.ask(QUESTION, [])

    assert answer.refusal is None and answer.text == GOOD.answer
    assert answer.post_check is not None
    assert answer.post_check.outcome is PostCheckOutcome.REGENERATED
    assert [a.numbers for a in answer.post_check.attempts] == [["520"], []]
    assert {"postcheck_suspect", "postcheck_numbers", "postcheck_regenerated"} <= set(answer.flags)
    assert "postcheck_cars" not in answer.flags
    assert "do not contain: 520" in llm.calls[2].messages[2]["content"]


def test_invented_number_twice_falls_back() -> None:
    pipeline, llm, _ = make([understanding(cars=["mg_s6"]), INVENTED, INVENTED])
    answer = pipeline.ask(QUESTION, [])
    assert answer.refusal is RefusalReason.UNVERIFIED and "520" not in answer.text
    assert answer.post_check is not None
    assert answer.post_check.outcome is PostCheckOutcome.FALLBACK
    assert len(llm.calls) == 3


def test_number_from_the_users_message_is_not_flagged_in_the_pipeline() -> None:
    reply = generation('לפי הכתבה הטווח 400 ק"מ, פחות מ-500 ק"מ שביקשת (MG S6, פרק 0).')
    pipeline, _, _ = make([understanding(cars=["mg_s6"]), reply])
    answer = pipeline.ask('אני צריך לפחות 500 ק"מ, כמה טווח יש ל-MG S6?', [])
    assert answer.post_check is not None
    assert answer.post_check.outcome is PostCheckOutcome.CLEAN


def test_car_and_number_problems_are_both_reported() -> None:
    findings = CheckFindings(cars=["טויוטה"], numbers=["520"])
    assert findings.kinds() == ["postcheck_cars", "postcheck_numbers"]
    instruction = regenerate_instruction(findings.problems())
    assert "do not support: טויוטה" in instruction and "do not contain: 520" in instruction


def test_telemetry_records_the_numbers(tmp_path: Path) -> None:
    logger = TurnLogger(tmp_path, profile="dev", models={"understand": "a", "generate": "b"})
    pipeline, _, _ = make([understanding(cars=["mg_s6"]), INVENTED, GOOD], logger=logger)
    pipeline.ask(QUESTION, [])
    record = json.loads(logger.path.read_text(encoding="utf-8").strip())
    assert record["post_check"]["attempts"][0] == {"cars": [], "numbers": ["520"]}
    assert "postcheck_numbers" in record["flags"]


def test_regenerate_prompt_v2_covers_numbers_and_v1_is_kept() -> None:
    assert PROMPT_VERSIONS["regenerate"] == "v2"
    assert "Write every number exactly as an excerpt or the question states it" in (
        regenerate_instruction(["x"])
    )
    assert (PROMPT_DIR / "regenerate.v1.txt").exists()
