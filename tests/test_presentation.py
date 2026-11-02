"""Inline "(car, section)" markers are hidden in the display only (CW-627).

All text here is synthetic; no article text.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app import ui_support as ui
from app.chat import format_answer
from carwise.presentation import strip_inline_citations
from carwise.registry import load_registry
from tests.test_pipeline import generation, make, understanding

REGISTRY = load_registry()
ROOT = Path(__file__).resolve().parent.parent
IMPORTS_PRESENTATION = re.compile(r"carwise\.presentation|import\s+presentation\b")


def strip(text: str) -> str:
    return strip_inline_citations(text, REGISTRY)


def test_single_marker_is_removed() -> None:
    assert strip('הטווח הוא 400 ק"מ (MG S6, טווח).') == 'הטווח הוא 400 ק"מ.'


def test_two_adjacent_markers_are_removed() -> None:
    text = "שני הרכבים חשמליים (MG S6, הנעה) (קיה EV9, סוללה)."
    assert strip(text) == "שני הרכבים חשמליים."


def test_semicolon_joined_markers_in_one_group_are_removed() -> None:
    text = "שניהם נוחים (MG S6, נוחות; קיה EV9, תא נוסעים) בנסיעה ארוכה."
    assert strip(text) == "שניהם נוחים בנסיעה ארוכה."


def test_group_with_one_non_citation_segment_is_kept() -> None:
    text = "שניהם נוחים (MG S6, נוחות; ראו גם בהמשך) בנסיעה."
    assert strip(text) == text


def test_nested_parentheses_in_a_section_title_are_removed() -> None:
    text = "הצריכה סבירה (קיה EV9, דוח ארוך: קיה EV9 'גרסה' (דוח מס' 4)) לאורך זמן."
    assert strip(text) == "הצריכה סבירה לאורך זמן."


def test_merged_headings_with_slashes_are_removed() -> None:
    text = "הטעינה מהירה (MG S6, כמה זמן לוקח? / כמה זה עולה?)."
    assert strip(text) == "הטעינה מהירה."


def test_marker_after_a_full_stop_is_removed() -> None:
    text = "הרכב שקט. (MG S6, נסיעה) והוא גם נוח."
    assert strip(text) == "הרכב שקט. והוא גם נוח."


def test_marker_at_end_after_full_stop() -> None:
    assert strip("הרכב שקט. (MG S6, נסיעה)") == "הרכב שקט."


def test_trailing_paragraph_of_markers_only_disappears() -> None:
    text = "הרכב שקט ונוח.\n\n(MG S6, נסיעה) (קיה EV9, נוחות)"
    assert strip(text) == "הרכב שקט ונוח."


def test_middle_paragraph_of_markers_only_disappears_with_its_blank_line() -> None:
    text = "פסקה ראשונה.\n\n(MG S6, נסיעה)\n\nפסקה שנייה."
    assert strip(text) == "פסקה ראשונה.\n\nפסקה שנייה."


def test_marker_repeated_twice_in_a_row_is_removed() -> None:
    text = "הטווח טוב (MG S6, טווח) (MG S6, טווח), והטעינה מהירה."
    assert strip(text) == "הטווח טוב, והטעינה מהירה."


@pytest.mark.parametrize(
    "text",
    [
        'הספק מרבי (5800 סל"ד) בסיבובים גבוהים.',
        "צריכה לפי תקן (WLTP) בלבד.",
        "הנעה היברידית (Plug-in Hybrid) נטענת.",
        "תאוצה (מ-0 ל-100) של שש שניות.",
        "גרסה אחת (בסיסית, עם חבילה) בלבד.",
        "מחיר (לפני הנחות) של 200 אלף.",
    ],
)
def test_non_citation_parentheses_are_kept(text: str) -> None:
    assert strip(text) == text


@pytest.mark.parametrize(
    "text",
    ["הרכב הנבחן (MG S6) שקט.", "הרכב הנבחן (MG S6 בגרסה הבסיסית) שקט."],
)
def test_car_name_without_a_comma_is_kept(text: str) -> None:
    assert strip(text) == text


def test_another_model_built_on_an_alias_is_kept() -> None:
    text = "דגם אחר (אאודי S6, מבחן אחר) לא נבחן."
    assert strip(text) == text


def test_latin_only_alias_is_removed() -> None:
    assert strip("שקט מאוד (S6, נסיעה).") == "שקט מאוד."


def test_hebrew_prefix_form_is_removed() -> None:
    assert strip("הסוללה גדולה (בקיה EV9, סוללה).") == "הסוללה גדולה."


def test_leading_whitespace_inside_the_group_is_allowed() -> None:
    assert strip("שקט מאוד ( MG S6, נסיעה).") == "שקט מאוד."


def test_text_without_markers_is_unchanged() -> None:
    text = "שורה  עם רווח כפול ,ופיסוק מוזר .\n\n- פריט ברשימה  \n"
    assert strip(text) == text


def test_list_markers_and_lines_are_kept() -> None:
    text = "- טווח ארוך (MG S6, טווח)\n- סוללה גדולה (קיה EV9, סוללה)\n  - פירוט (MG S6, פרק)"
    assert strip(text) == "- טווח ארוך\n- סוללה גדולה\n  - פירוט"


def test_marker_before_bold_closing_keeps_the_bold() -> None:
    assert strip("**שקט מאוד (MG S6, נסיעה)**.") == "**שקט מאוד**."


def test_full_stop_after_marker_is_not_doubled() -> None:
    assert strip("טקסט. (MG S6, נתונים).") == "טקסט."


def test_list_item_of_markers_only_disappears() -> None:
    assert strip("- (MG S6, נתונים)\n- שני") == "- שני"


def test_one_space_between_the_words_around_a_marker() -> None:
    assert strip("שתיים  (MG S6, נתונים)  רווחים.") == "שתיים רווחים."
    assert strip("מילה(MG S6, נתונים)מילה") == "מילה מילה"


def test_idempotent() -> None:
    text = "שקט (MG S6, נסיעה). (קיה EV9, א (ב)) נוח.\n\n(MG S6, x)"
    once = strip(text)
    assert strip(once) == once


def test_result_that_would_be_empty_returns_the_original() -> None:
    text = "(MG S6, נסיעה) (קיה EV9, סוללה)"
    assert strip(text) == text


@pytest.mark.parametrize(
    "text",
    ["שקט מאוד (MG S6, נסיעה.", "שקט מאוד (MG S6, נסיעה (פרק 2)."],
)
def test_unbalanced_parenthesis_is_kept(text: str) -> None:
    assert strip(text) == text


def test_stray_open_parenthesis_does_not_hide_a_later_marker() -> None:
    assert strip("ראו ( למטה. שקט (MG S6, נסיעה).") == "ראו ( למטה. שקט."


# --- surfaces -----------------------------------------------------------------------
MARKED = 'הטווח בפועל הוא 400 ק"מ (MG S6, פרק 0).'


def test_cli_hides_the_marker_and_keeps_the_sources_list() -> None:
    pipeline, _, _ = make([understanding(cars=["mg_s6"]), generation(MARKED)])
    answer = pipeline.ask("מה הטווח בפועל של MG S6?", [])
    before = answer.model_copy(deep=True)
    printed = format_answer(answer, show_cost=False, max_section_chars=60, registry=REGISTRY)
    assert printed.startswith('הטווח בפועל הוא 400 ק"מ.\n')
    assert "(MG S6," not in printed
    assert "\nמקורות:" in printed and "  - MG S6 | " in printed
    assert answer == before and answer.text == MARKED


def test_ui_hides_the_marker_and_keeps_the_sources() -> None:
    pipeline, _, _ = make([understanding(cars=["mg_s6"]), generation(MARKED)])
    answer = pipeline.ask("מה הטווח בפועל של MG S6?", [])
    before = answer.model_copy(deep=True)
    shown = ui.answer_markdown(answer, REGISTRY)
    assert shown == 'הטווח בפועל הוא 400 ק"מ.'
    rows = ui.source_rows(answer, 60)
    assert rows and rows[0].car == "MG S6" and any(row.cited for row in rows)
    assert "MG S6" in ui.sources_markdown(rows)
    assert ui.article_links(answer, REGISTRY)[0][0] == "MG S6"
    assert answer == before and answer.text == MARKED


def test_core_and_eval_never_import_presentation() -> None:
    files = [
        ROOT / "src" / "carwise" / "pipeline.py",
        ROOT / "src" / "carwise" / "guardrails.py",
        *sorted((ROOT / "eval").rglob("*.py")),
    ]
    assert len(files) > 2
    for path in files:
        source = path.read_text(encoding="utf-8")
        assert not IMPORTS_PRESENTATION.search(source), path
