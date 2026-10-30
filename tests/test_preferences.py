"""Preference memory, its validation, /prefs and /reset (CW-203)."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.chat import run_command
from carwise.config import load_settings
from carwise.llm.base import LLMOutputError
from carwise.llm.openai_client import response_format
from carwise.preferences import EMPTY_PREFERENCES, RESET_REPLY, Session, grounded_in, merge
from carwise.schemas import (
    Generation,
    Intent,
    Preference,
    Preferences,
    PreferenceUpdate,
    RefusalReason,
    Understanding,
)
from carwise.telemetry import TurnLogger
from tests.test_pipeline import generation, make

WINDOW = load_settings().llm.history_window
MAX_CHARS = load_settings().preferences.max_value_chars


def said(
    *updates: tuple[str, str],
    intent: Intent = Intent.RECOMMEND,
    cars: list[str] | None = None,
    unrecognized: list[str] | None = None,
    question: str = "איזה רכב מתאים לי?",
) -> Understanding:
    return Understanding(
        intent=intent,
        cars=cars or [],
        unrecognized_cars=unrecognized or [],
        standalone_question=question,
        preference_updates=[PreferenceUpdate(field=f, value=v) for f, v in updates],
    )


RECOMMENDATION = generation("מבין שמונה הרכבים שנבחנו, איון HT (GAC איון HT, פרק 1).", [])


# --- merging -----------------------------------------------------------------------------
def test_new_preference_records_value_and_source_message() -> None:
    message = "התקציב שלי עד 200 אלף שקל, מה מתאים?"
    pipeline, _, _ = make([said(("budget", "עד 200 אלף")), RECOMMENDATION])
    answer = pipeline.ask(message, [])
    assert answer.preferences.budget == Preference(value="עד 200 אלף", source=message)
    assert answer.updated_preferences == ["budget"]


def test_later_statement_overrides_and_other_fields_stay() -> None:
    first, second = "עד 200 אלף, ורק חשמלי", "בעצם אפשר עד 250 אלף"
    pipeline, _, _ = make(
        [
            said(("budget", "עד 200 אלף"), ("powertrain", "חשמלי")),
            RECOMMENDATION,
            said(("budget", "עד 250 אלף")),
            RECOMMENDATION,
        ]
    )
    session = Session(history_window=WINDOW)
    pipeline.answer(first, session)
    answer = pipeline.answer(second, session)
    assert session.preferences.budget == Preference(value="עד 250 אלף", source=second)
    assert session.preferences.powertrain == Preference(value="חשמלי", source=first)
    assert answer.updated_preferences == ["budget"]


def test_conflicting_preference_in_a_later_turn_replaces_the_earlier_one() -> None:
    first, second = "אני מחפש רכב חשמלי", "התחרטתי, רק בנזין"
    pipeline, _, _ = make(
        [said(("powertrain", "חשמלי")), RECOMMENDATION, said(("powertrain", "בנזין"))]
        + [RECOMMENDATION]
    )
    session = Session(history_window=WINDOW)
    pipeline.answer(first, session)
    pipeline.answer(second, session)
    assert session.preferences.powertrain == Preference(value="בנזין", source=second)


def test_within_one_turn_the_last_update_on_a_field_wins() -> None:
    message = "חשמלי, או בעצם היברידי"
    updates = [PreferenceUpdate(field="powertrain", value=v) for v in ("חשמלי", "היברידי")]
    prefs, updated, flags = merge(Preferences(), updates, message, MAX_CHARS)
    assert prefs.powertrain == Preference(value="היברידי", source=message)
    assert updated == ["powertrain"] and flags == []


def test_unknown_field_is_dropped_and_flagged() -> None:
    message = "צבע אדום ותקציב עד 200 אלף"
    updates = [
        PreferenceUpdate(field="color", value="אדום"),
        PreferenceUpdate(field="budget", value="עד 200 אלף"),
    ]
    prefs, updated, flags = merge(Preferences(), updates, message, MAX_CHARS)
    assert prefs.field_names() == ["budget"] and updated == ["budget"]
    assert flags == ["preference_unknown_field"]


def test_strict_schema_still_lists_the_allowed_field_names() -> None:
    schema = json.dumps(response_format(Understanding))
    assert '"enum": ["budget", "powertrain", "primary_use", "passengers", "priorities"' in schema
    # ...while parsing accepts any string, so code can drop it instead of failing the call.
    assert PreferenceUpdate.model_validate({"field": "color", "value": "אדום"}).field == "color"


def test_long_value_is_capped_and_flagged() -> None:
    message = "חשוב לי " + " ".join(["נוחות"] * 40)
    update = PreferenceUpdate(field="priorities", value=" ".join(["נוחות"] * 40))
    prefs, _, flags = merge(Preferences(), [update], message, MAX_CHARS)
    assert prefs.priorities is not None and len(prefs.priorities.value) <= MAX_CHARS
    assert flags == ["preference_value_truncated"]


@pytest.mark.parametrize(
    ("value", "message", "expected"),
    [
        ("חשמלי", "אני רוצה רכב חשמלית", True),  # suffix
        ("בחשמלי", "משהו חשמלי", True),  # prefix on the value
        ("עד 200 אלף", "התקציב עד 200 אלף שקל", True),
        ("משפחה עם 3 ילדים", "יש לנו 3 ילדים", True),  # half of the content words
        ("500 אלף", "מה תמליץ?", False),
        ("עד", "עד", False),  # no content word at all
    ],
)
def test_grounded_in_the_users_message(value: str, message: str, expected: bool) -> None:
    assert grounded_in(value, message) is expected


# --- never from assistant turns or article text ------------------------------------------
def test_preference_lifted_from_an_assistant_turn_is_rejected() -> None:
    history = [
        {"role": "user", "content": "שלום"},
        {"role": "assistant", "content": "שמעתי שהתקציב שלך 500 אלף ושאתה רוצה בנזין."},
    ]
    pipeline, _, _ = make([said(("budget", "500 אלף"), ("powertrain", "בנזין")), RECOMMENDATION])
    answer = pipeline.ask("מה תמליץ?", history)
    assert answer.preferences == Preferences() and answer.updated_preferences == []
    assert "preference_not_from_user" in answer.flags


def test_earlier_preference_resent_unchanged_is_kept_without_a_flag() -> None:
    first, second = "עד 200 אלף, ורק חשמלי", "ומה עם תא המטען?"
    pipeline, _, _ = make(
        [
            said(("budget", "עד 200 אלף"), ("powertrain", "חשמלי")),
            RECOMMENDATION,
            # The model repeats both from history, one with different spacing.
            said(("budget", "עד  200 אלף"), ("powertrain", "חשמלי")),
            RECOMMENDATION,
        ]
    )
    session = Session(history_window=WINDOW)
    pipeline.answer(first, session)
    answer = pipeline.answer(second, session)
    assert session.preferences.budget == Preference(value="עד 200 אלף", source=first)
    assert session.preferences.powertrain == Preference(value="חשמלי", source=first)
    assert answer.updated_preferences == [] and "preference_not_from_user" not in answer.flags


def test_new_value_for_a_stored_field_must_still_come_from_the_user() -> None:
    stored = Preferences(budget=Preference(value="עד 200 אלף", source="x"))
    update = PreferenceUpdate(field="budget", value="עד 300 אלף")
    profile, updated, flags = merge(stored, [update], "ומה עם תא המטען?", MAX_CHARS)
    assert profile == stored and updated == [] and flags == ["preference_not_from_user"]


def test_repeat_check_compares_with_the_same_field_only() -> None:
    stored = Preferences(budget=Preference(value="חשמלי", source="x"))
    update = PreferenceUpdate(field="powertrain", value="חשמלי")
    profile, updated, flags = merge(stored, [update], "מה מתאים לי?", MAX_CHARS)
    assert profile == stored and updated == [] and flags == ["preference_not_from_user"]


def test_preference_taken_from_article_text_is_rejected() -> None:
    # "180 אלף" is in the synthetic MG S6 chunk, never in the user's message.
    plan = said(("budget", "180 אלף"), intent=Intent.FACT, cars=["mg_s6"], question="מחיר MG S6")
    pipeline, _, _ = make([plan, generation(ids=["mg_s6:001"])])
    answer = pipeline.ask("כמה עולה MG S6?", [])
    assert answer.preferences.budget is None and "preference_not_from_user" in answer.flags


def test_the_generate_call_cannot_set_preferences() -> None:
    reply = {"answer": "תשובה", "used_chunk_ids": [], "preference_updates": []}
    with pytest.raises(ValidationError):
        Generation.model_validate_json(json.dumps(reply))


# --- how preferences are used --------------------------------------------------------------
def test_recommendation_receives_the_preferences_and_a_fact_question_does_not() -> None:
    message = "עד 200 אלף, איזה רכב?"
    fact = said(intent=Intent.FACT, cars=["mg_s6"], question="מה הטווח של MG S6?")
    pipeline, llm, _ = make([said(("budget", "עד 200 אלף")), RECOMMENDATION, fact, generation()])
    session = Session(history_window=WINDOW)
    pipeline.answer(message, session)
    pipeline.answer("מה הטווח של MG S6?", session)
    recommend_input = llm.calls[1].messages[0]["content"]
    fact_input = llm.calls[3].messages[0]["content"]
    assert "User preferences" in recommend_input and "- budget: עד 200 אלף" in recommend_input
    assert "User preferences" not in fact_input
    assert session.preferences.budget is not None  # still remembered


def test_recommendation_without_preferences_sends_no_block() -> None:
    pipeline, llm, _ = make([said(), RECOMMENDATION])
    pipeline.ask("איזה רכב כדאי לי?", [])
    assert "User preferences" not in llm.calls[1].messages[0]["content"]


def test_preferences_survive_a_refusal_and_an_understand_failure() -> None:
    message = "עד 200 אלף, מה עם טויוטה קורולה?"
    refused = said(("budget", "עד 200 אלף"), intent=Intent.FACT, unrecognized=["טויוטה קורולה"])
    refused = refused.model_copy(update={"standalone_question": message})
    pipeline, _, _ = make([refused, LLMOutputError("bad", attempts=2), generation()])
    session = Session(history_window=WINDOW)
    assert pipeline.answer(message, session).refusal is RefusalReason.UNKNOWN_CAR
    assert session.preferences.budget is not None
    pipeline.answer("כמה טווח יש ל-MG S6?", session)  # understand falls back to the raw message
    assert session.preferences.budget is not None


def test_preferences_do_not_leak_across_sessions() -> None:
    pipeline, _, _ = make([said(("budget", "עד 200 אלף")), RECOMMENDATION, said(), RECOMMENDATION])
    first, second = Session(history_window=WINDOW), Session(history_window=WINDOW)
    pipeline.answer("עד 200 אלף, מה מתאים?", first)
    answer = pipeline.answer("מה מתאים לי?", second)
    assert first.preferences.budget is not None
    assert second.preferences == Preferences() and answer.preferences == Preferences()
    assert second.history[0]["content"] == "מה מתאים לי?" and len(second.history) == 2


# --- chat commands -------------------------------------------------------------------------
def test_prefs_command_shows_each_preference_with_its_source() -> None:
    session = Session(history_window=WINDOW)
    assert run_command("/prefs", session) == EMPTY_PREFERENCES
    session.preferences = Preferences(
        budget=Preference(value="עד 250 אלף", source="בעצם אפשר עד 250 אלף"),
        powertrain=Preference(value="חשמלי", source="רק חשמלי"),
    )
    assert run_command(" /prefs ", session) == (
        "ההעדפות בשיחה הזאת:\n"
        '- תקציב: עד 250 אלף (מתוך: "בעצם אפשר עד 250 אלף")\n'
        '- הנעה: חשמלי (מתוך: "רק חשמלי")'
    )


def test_reset_command_clears_history_and_preferences() -> None:
    session = Session(history_window=WINDOW)
    session.history = [{"role": "user", "content": "שלום"}]
    session.preferences = Preferences(budget=Preference(value="200", source="200"))
    assert run_command("/reset", session) == RESET_REPLY
    assert session.history == [] and session.preferences == Preferences()
    assert run_command("מה הטווח?", session) is None  # a question, not a command


def test_session_keeps_only_the_history_window() -> None:
    pipeline, _, _ = make([said(), RECOMMENDATION] * 4)
    session = Session(history_window=4)
    for index in range(4):
        pipeline.answer(f"שאלה {index}", session)
    assert len(session.history) == 4 and session.history[0]["content"] == "שאלה 2"


# --- telemetry -----------------------------------------------------------------------------
def test_telemetry_has_preference_field_names_only(tmp_path: Path) -> None:
    logger = TurnLogger(tmp_path, profile="dev", models={"understand": "a", "generate": "b"})
    replies = [said(("budget", "עד 200 אלף"), ("powertrain", "חשמלי")), RECOMMENDATION]
    pipeline, _, _ = make(replies, logger=logger)
    pipeline.ask("עד 200 אלף ורק חשמלי", [])
    raw = logger.path.read_text(encoding="utf-8")
    record = json.loads(raw)
    assert record["preferences"] == ["budget", "powertrain"]
    assert record["updated_preferences"] == ["budget", "powertrain"]
    assert "200" not in raw and "חשמלי" not in raw  # no values, no message text
