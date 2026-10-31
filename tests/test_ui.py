"""The Streamlit UI (CW-401): display helpers, and a smoke test of the real script.

The smoke test runs app/ui.py with streamlit.testing (no browser, no server)
and swaps only the heavy wiring (embedding model, index, OpenAI client) for the
same fakes the pipeline tests use, so the UI is exercised end to end, offline.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from app import ui_support as ui
from app import ui_text as text
from carwise.guardrails import LLM_ERROR_REPLY
from carwise.llm.base import BudgetExceededError, LLMConfigError, LLMUnavailableError
from carwise.llm.fake import FakeLLMClient
from carwise.preferences import EMPTY_PREFERENCES, RESET_REPLY
from carwise.retrieval.store import IndexNotReadyError
from carwise.schemas import Intent, PreferenceUpdate, Understanding
from tests.test_pipeline import REGISTRY, SpyRetriever, _settings, generation, make, understanding

QUESTION = "כמה טווח יש ל-MG S6?"
TOYOTA = "מה דעתך על טויוטה קורולה?"


def family_plan() -> Understanding:
    return Understanding(
        intent=Intent.FACT,
        cars=["mg_s6"],
        unrecognized_cars=[],
        standalone_question=QUESTION,
        preference_updates=[PreferenceUpdate(field="powertrain", value="חשמלי")],
    )


# --- display helpers -------------------------------------------------------------------
def test_sources_list_every_retrieved_chunk_best_first_and_mark_the_cited() -> None:
    pipeline, _, _ = make([understanding(cars=["mg_s6"]), generation()])
    answer = pipeline.ask(QUESTION, [])
    rows = ui.source_rows(answer, max_section_chars=60)
    assert len(rows) == len(answer.retrieved)
    assert [r.score for r in rows] == sorted((r.score for r in rows), reverse=True)
    assert [r.cited for r in rows].count(True) == 1 and rows[0].car == "MG S6"


def test_sources_table_escapes_pipes_and_dollar_signs() -> None:
    row = ui.SourceRow(car="MG S6", section="מחיר | $40", score=0.81234, cited=True)
    table = ui.sources_markdown([row])
    assert "מחיר \\| \\$40" in table and "0.812" in table and text.CITED_MARK in table


def test_cost_line_has_tokens_cost_and_seconds() -> None:
    pipeline, _, _ = make([understanding(cars=["mg_s6"]), generation()])
    line = ui.cost_line(pipeline.ask(QUESTION, []))
    assert "טוקנים" in line and "$0.0" in line and "שניות" in line


def test_refusal_styles_tell_not_covered_from_failure() -> None:
    covered, _, _ = make([understanding(unrecognized=["טויוטה קורולה"], question=TOYOTA)])
    assert ui.refusal_style(covered.ask(TOYOTA, [])) == "info"
    down, _, _ = make([LLMUnavailableError("down")])
    assert ui.refusal_style(down.ask(QUESTION, [])) == "warning"
    ok, _, _ = make([understanding(cars=["mg_s6"]), generation()])
    assert ui.refusal_style(ok.ask(QUESTION, [])) is None


def test_startup_messages_are_hebrew_and_never_the_exception_text() -> None:
    assert ui.startup_message(LLMConfigError("OPENAI_API_KEY is not set")) == text.MISSING_KEY
    assert ui.startup_message(IndexNotReadyError("run ingest")) == text.INDEX_MISSING
    assert ui.startup_message(RuntimeError("boom")) == text.UNEXPECTED


def test_dollar_does_not_start_latex() -> None:
    assert ui.as_markdown("עד $0.5 לשיחה") == "עד \\$0.5 לשיחה"


# --- smoke test of app/ui.py -------------------------------------------------------------
@pytest.fixture
def run_app(monkeypatch: pytest.MonkeyPatch) -> Iterator[Callable[..., AppTest]]:
    """Start the real script with fake wiring; returns a function of the scripted replies."""
    st.cache_resource.clear()

    def start(replies: list[Any], *, llm_error: Exception | None = None) -> AppTest:
        settings = _settings()

        def resources(_: Any) -> ui.Resources:
            return ui.Resources(settings, REGISTRY, SpyRetriever(settings), None)

        def new_llm(_: Any) -> FakeLLMClient:
            if llm_error:
                raise llm_error
            return FakeLLMClient(replies)

        monkeypatch.setattr(ui, "load_resources", resources)
        monkeypatch.setattr(ui, "new_llm", new_llm)
        app = AppTest.from_file(str(ui.SCRIPT), default_timeout=30)
        app.run()
        return app

    yield start
    st.cache_resource.clear()


def texts(app: AppTest) -> list[str]:
    """Every text the page shows, sidebar included."""
    elements = [*app.markdown, *app.caption, *app.info, *app.warning, *app.error]
    elements += [*app.sidebar.markdown, *app.sidebar.caption]
    return [str(element.value) for element in elements]


def test_page_opens_with_the_greeting_and_an_empty_profile(run_app: Callable[..., AppTest]) -> None:
    app = run_app([])
    assert not app.exception
    assert app.title[0].value == text.TITLE
    assert any("שמונה רכבים" in text for text in texts(app))
    assert EMPTY_PREFERENCES in [str(m.value) for m in app.sidebar.markdown]
    assert app.chat_input[0].max_chars == _settings().input.max_message_chars


def test_answer_shows_sources_cost_and_updates_the_profile(
    run_app: Callable[..., AppTest],
) -> None:
    app = run_app([family_plan(), generation()])
    app.chat_input[0].set_value(f"אני רוצה חשמלי. {QUESTION}").run()
    assert not app.exception
    shown = texts(app)
    assert any("הטווח בפועל הוא 400" in text for text in shown)
    assert app.expander and app.expander[0].label.startswith("מקורות")
    assert any("טוקנים" in text for text in shown)
    assert any("חשמלי" in str(m.value) for m in app.sidebar.markdown)
    assert not app.info and not app.warning  # a normal answer, not a refusal


def test_refusal_has_its_own_style(run_app: Callable[..., AppTest]) -> None:
    app = run_app([understanding(unrecognized=["טויוטה קורולה"], question=TOYOTA)])
    app.chat_input[0].set_value(TOYOTA).run()
    assert not app.exception and len(app.info) == 1 and "טויוטה קורולה" in app.info[0].value


def test_llm_outage_is_a_hebrew_warning_not_a_trace(run_app: Callable[..., AppTest]) -> None:
    app = run_app([LLMUnavailableError("down")])
    app.chat_input[0].set_value(QUESTION).run()
    assert not app.exception and app.warning[0].value == ui.as_markdown(LLM_ERROR_REPLY)


def test_cost_cap_stops_the_conversation(run_app: Callable[..., AppTest]) -> None:
    app = run_app([BudgetExceededError("cap reached")])
    app.chat_input[0].set_value(QUESTION).run()
    assert not app.exception
    assert app.chat_input[0].disabled
    assert text.STOPPED in [str(w.value) for w in app.warning]


def test_missing_api_key_shows_a_hebrew_message_and_no_chat(
    run_app: Callable[..., AppTest],
) -> None:
    app = run_app([], llm_error=LLMConfigError("OPENAI_API_KEY is not set"))
    assert not app.exception
    assert [e.value for e in app.error] == [text.MISSING_KEY] and not app.chat_input


def test_missing_index_shows_a_hebrew_message(
    run_app: Callable[..., AppTest], monkeypatch: pytest.MonkeyPatch
) -> None:
    def no_index(_: Any) -> ui.Resources:
        raise IndexNotReadyError("index not built")

    app = run_app([])
    monkeypatch.setattr(ui, "load_resources", no_index)
    st.cache_resource.clear()
    fresh = AppTest.from_file(str(ui.SCRIPT), default_timeout=30)
    fresh.run()
    assert not app.exception and not fresh.exception
    assert [e.value for e in fresh.error] == [text.INDEX_MISSING]


def test_unexpected_failure_shows_a_friendly_message(run_app: Callable[..., AppTest]) -> None:
    app = run_app([RuntimeError("bug")])  # not an LLM error: the pipeline lets it through
    app.chat_input[0].set_value(QUESTION).run()
    assert not app.exception and text.UNEXPECTED in texts(app)


def test_reset_button_clears_the_conversation_and_preferences(
    run_app: Callable[..., AppTest],
) -> None:
    app = run_app([family_plan(), generation()])
    app.chat_input[0].set_value(f"אני רוצה חשמלי. {QUESTION}").run()
    app.sidebar.button[0].click().run()
    assert not app.exception
    assert EMPTY_PREFERENCES in [str(m.value) for m in app.sidebar.markdown]
    assert not app.expander and app.session_state.session.history == []
    assert app.toast and app.toast[0].value == RESET_REPLY


def test_typed_prefs_command_does_not_call_the_model(run_app: Callable[..., AppTest]) -> None:
    app = run_app([])  # no scripted replies: a model call would fail the test
    app.chat_input[0].set_value("/prefs").run()
    assert not app.exception and EMPTY_PREFERENCES in texts(app)


def test_the_api_key_is_never_shown(
    run_app: Callable[..., AppTest], monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = "sk-test-not-a-real-key-123"
    monkeypatch.setenv("OPENAI_API_KEY", secret)
    app = run_app([understanding(unrecognized=["טויוטה קורולה"], question=TOYOTA)])
    app.chat_input[0].set_value(TOYOTA).run()
    assert not app.exception and not any(secret in text for text in texts(app))


# --- article links (CW-401 review) -----------------------------------------------------
def test_article_links_come_from_the_registry_once_per_cited_car() -> None:
    ids = ["mg_s6:000", "mg_s6:001", "aion_ht:000"]
    pipeline, _, _ = make([understanding(cars=["mg_s6", "aion_ht"]), generation(ids=ids)])
    links = ui.article_links(pipeline.ask(QUESTION, []), REGISTRY)
    assert links == [
        (REGISTRY.get("mg_s6").display_name, REGISTRY.get("mg_s6").url),
        (REGISTRY.get("aion_ht").display_name, REGISTRY.get("aion_ht").url),
    ]


def test_a_refusal_has_no_article_links() -> None:
    pipeline, _, _ = make([understanding(unrecognized=["טויוטה קורולה"], question=TOYOTA)])
    assert ui.article_links(pipeline.ask(TOYOTA, []), REGISTRY) == []


def test_link_text_cannot_break_the_markdown_link() -> None:
    line = ui.links_markdown([("a[b](c)", "https://example.org/x")])
    assert "[a\[b\]\(c\)](https://example.org/x)" in line


def test_page_links_the_cited_article(run_app: Callable[..., AppTest]) -> None:
    app = run_app([family_plan(), generation()])
    app.chat_input[0].set_value(QUESTION).run()
    assert any(REGISTRY.get("mg_s6").url in text for text in texts(app))


def test_link_separator_keeps_latin_names_in_right_to_left_order() -> None:
    line = ui.links_markdown([("MG S6", "https://a.example"), ("GAC איון HT", "https://b.example")])
    assert "‏ · ‏" in line and line.endswith("‏")
