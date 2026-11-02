"""The Streamlit UI (CW-401): display helpers, and a smoke test of the real script.

The smoke test runs app/ui.py with streamlit.testing (no browser, no server)
and swaps only the heavy wiring (embedding model, index, OpenAI client) for the
same fakes the pipeline tests use, so the UI is exercised end to end, offline.
"""

from __future__ import annotations

import argparse
import types
from collections.abc import Callable, Iterator
from typing import Any

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from app import ui_support as ui
from app import ui_text as text
from carwise.guardrails import LLM_ERROR_REPLY
from carwise.llm.base import (
    BudgetExceededError,
    LLMConfigError,
    LLMUnavailableError,
    SharedBudgetExceededError,
)
from carwise.llm.budget import SharedBudget
from carwise.llm.fake import FakeLLMClient
from carwise.preferences import EMPTY_PREFERENCES, RESET_REPLY
from carwise.retrieval.retriever import SerializedRetriever
from carwise.retrieval.store import IndexNotReadyError
from carwise.schemas import Intent, PreferenceUpdate, RefusalReason, Understanding
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


# Names the understand call returned as "unrecognized cars" (CR-011): raw model output
# that the refusal template embeds, so each must render as plain text.
LINK_NAMES = [
    "[לחצו כאן][1]\n\n[1]: //evil.example/x",
    "![a][i]\n\n[i]: //evil.example/p.png",
    "[כאן](//evil.example)",
    "<https://evil.example>",
    "www.evil.example",
    "a@evil.example",
]


def _render(markdown: str) -> str:
    """CommonMark HTML; Streamlit's frontend renderer (react-markdown) follows CommonMark."""
    markdown_it = pytest.importorskip("markdown_it")
    return str(markdown_it.MarkdownIt("commonmark").render(markdown))


def test_literal_markdown_escapes_punctuation_only_and_once() -> None:
    assert ui.as_literal_markdown("אין לי מידע על ![a][i]: $5.") == (
        "אין לי מידע על \\!\\[a\\]\\[i\\]\\: \\$5\\."
    )
    assert ui.as_literal_markdown("טויוטה קורולה") == "טויוטה קורולה"


@pytest.mark.parametrize("name", LINK_NAMES)
def test_unknown_car_names_cannot_form_links_or_images(name: str) -> None:
    pipeline, _, _ = make([understanding(unrecognized=[name], question=TOYOTA)])
    answer = pipeline.ask(TOYOTA, [])
    assert answer.refusal is RefusalReason.UNKNOWN_CAR and name.split("\n")[0] in answer.text
    html = _render(ui.answer_markdown(answer, REGISTRY))
    assert "<a " not in html and "<img" not in html
    assert "evil.example" in html  # shown as text, not dropped
    assert "\\" not in html  # every escape was consumed: no stray backslash on screen


def test_generated_answer_keeps_its_markdown() -> None:
    reply = generation('**הטווח** בפועל הוא 400 ק"מ ($) (MG S6, פרק 0).')
    pipeline, _, _ = make([understanding(cars=["mg_s6"]), reply])
    answer = pipeline.ask(QUESTION, [])
    shown = ui.answer_markdown(answer, REGISTRY)
    # Bold kept, "$" escaped, the marker hidden (CW-627).
    assert answer.refusal is None and shown == '**הטווח** בפועל הוא 400 ק"מ (\\$).'


# --- smoke test of app/ui.py -------------------------------------------------------------
@pytest.fixture
def run_app(monkeypatch: pytest.MonkeyPatch) -> Iterator[Callable[..., AppTest]]:
    """Start the real script with fake wiring; returns a function of the scripted replies."""
    st.cache_resource.clear()

    def start(
        replies: list[Any],
        *,
        llm_error: Exception | None = None,
        budget: SharedBudget | None = None,
    ) -> AppTest:
        settings = _settings()

        def resources(_: Any, **__: Any) -> ui.Resources:
            return ui.Resources(settings, REGISTRY, SpyRetriever(settings), None)

        def new_llm(_: Any, __: SharedBudget) -> FakeLLMClient:
            if llm_error:
                raise llm_error
            return FakeLLMClient(replies)

        monkeypatch.setattr(ui, "load_resources", resources)
        monkeypatch.setattr(ui, "new_llm", new_llm)
        if budget is not None:
            monkeypatch.setattr(ui, "new_budget", lambda _: budget)
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
    assert not app.exception and app.warning[0].value == ui.as_literal_markdown(LLM_ERROR_REPLY)


def test_cost_cap_stops_the_conversation(run_app: Callable[..., AppTest]) -> None:
    app = run_app([BudgetExceededError("cap reached")])
    app.chat_input[0].set_value(QUESTION).run()
    assert not app.exception
    assert app.chat_input[0].disabled
    assert text.STOPPED in [str(w.value) for w in app.warning]


def test_server_total_stops_with_a_message_that_does_not_suggest_a_refresh(
    run_app: Callable[..., AppTest],
) -> None:
    app = run_app([SharedBudgetExceededError("total reached")])
    app.chat_input[0].set_value(QUESTION).run()
    assert not app.exception and app.chat_input[0].disabled
    warnings = [str(w.value) for w in app.warning]
    assert text.STOPPED_SERVER in warnings and text.STOPPED not in warnings
    assert "לרענן" not in text.STOPPED_SERVER


def test_new_session_opens_stopped_once_the_server_total_is_spent(
    run_app: Callable[..., AppTest],
) -> None:
    spent = SharedBudget(1.0)
    spent.add(1.0)  # other sessions spent it all
    app = run_app([], budget=spent)
    assert not app.exception and app.chat_input[0].disabled
    assert text.STOPPED_SERVER in [str(w.value) for w in app.warning]


def test_sessions_and_a_refresh_share_one_budget_per_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The CR-005 bug: a fresh budget per session (a refresh) would reset the total.
    Each AppTest run is a new browser session in the same process."""
    st.cache_resource.clear()  # isolation; not cleared between the sessions below
    settings = _settings()
    seen: list[SharedBudget] = []

    def resources(_: Any, **__: Any) -> ui.Resources:
        return ui.Resources(settings, REGISTRY, SpyRetriever(settings), None)

    def new_llm(_: Any, budget: SharedBudget) -> FakeLLMClient:
        seen.append(budget)
        return FakeLLMClient([])

    monkeypatch.setattr(ui, "load_resources", resources)
    monkeypatch.setattr(ui, "new_llm", new_llm)
    try:
        for _ in range(2):
            AppTest.from_file(str(ui.SCRIPT), default_timeout=30).run()
        assert len(seen) == 2 and seen[0] is seen[1]
        seen[0].add(seen[0].max_cost_usd)
        third = AppTest.from_file(str(ui.SCRIPT), default_timeout=30)
        third.run()
        assert not third.exception and third.chat_input[0].disabled
        assert text.STOPPED_SERVER in [str(w.value) for w in third.warning]
        assert seen[2] is seen[0]
    finally:
        st.cache_resource.clear()


def test_every_session_client_charges_the_one_shared_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")  # builds the SDK; no network call
    settings = _settings()
    budget = ui.new_budget(settings)
    assert budget.max_cost_usd == settings.llm.max_total_cost_usd
    first, second = ui.new_llm(settings, budget), ui.new_llm(settings, budget)
    assert first is not second
    budget.add(budget.max_cost_usd)  # spent: both refuse before any network call
    model = settings.profile().generate_model
    for client in (first, second):
        with pytest.raises(SharedBudgetExceededError):
            client.complete_json("system", [], Understanding, model=model)


def test_missing_api_key_shows_a_hebrew_message_and_no_chat(
    run_app: Callable[..., AppTest],
) -> None:
    app = run_app([], llm_error=LLMConfigError("OPENAI_API_KEY is not set"))
    assert not app.exception
    assert [e.value for e in app.error] == [text.MISSING_KEY] and not app.chat_input


def test_missing_index_shows_a_hebrew_message(
    run_app: Callable[..., AppTest], monkeypatch: pytest.MonkeyPatch
) -> None:
    def no_index(_: Any, **__: Any) -> ui.Resources:
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
    assert r"[a\[b\]\(c\)](https://example.org/x)" in line


def test_page_links_the_cited_article(run_app: Callable[..., AppTest]) -> None:
    app = run_app([family_plan(), generation()])
    app.chat_input[0].set_value(QUESTION).run()
    assert any(REGISTRY.get("mg_s6").url in text for text in texts(app))


def test_link_separator_keeps_latin_names_in_right_to_left_order() -> None:
    line = ui.links_markdown([("MG S6", "https://a.example"), ("GAC איון HT", "https://b.example")])
    assert "‏ · ‏" in line and line.endswith("‏")


# --- first start in Docker (CW-402) ------------------------------------------------------
class _FirstStart:
    """Fakes for load_resources: no index until ingest has run."""

    def __init__(self, ingest_ok: bool = True) -> None:
        self.indexed = False
        self.ingest_ok = ingest_ok
        self.ingest_embedders: list[object] = []
        self.open_embedders: list[object] = []

    def open_retriever(self, settings: Any, embedder: Any = None) -> SpyRetriever:
        self.open_embedders.append(embedder)
        if not self.indexed:
            raise IndexNotReadyError("index not built")
        return SpyRetriever(_settings())

    def ingest(self, settings: Any, *, embedder: Any = None) -> Any:
        self.ingest_embedders.append(embedder)
        self.indexed = self.ingest_ok
        fallback = None if self.ingest_ok else "place the files in data/raw"
        return types.SimpleNamespace(ok=self.ingest_ok, fallback=fallback, index_error=None)


@pytest.fixture
def first_start(monkeypatch: pytest.MonkeyPatch) -> Callable[[bool], _FirstStart]:
    def install(ingest_ok: bool = True) -> _FirstStart:
        fakes = _FirstStart(ingest_ok)
        monkeypatch.setattr(ui, "open_retriever", fakes.open_retriever)
        monkeypatch.setattr(ui, "ingest", fakes.ingest)
        monkeypatch.setattr(ui, "make_embedder", lambda config: object())
        return fakes

    return install


def test_without_the_flag_a_missing_index_is_reported_not_built(
    first_start: Callable[[bool], _FirstStart],
) -> None:
    fakes = first_start(True)
    with pytest.raises(IndexNotReadyError):
        ui.load_resources(_settings())
    assert fakes.ingest_embedders == []  # the local app never fetches on its own


def test_first_start_builds_the_index_with_one_model_load(
    first_start: Callable[[bool], _FirstStart],
) -> None:
    fakes = first_start(True)
    resources = ui.load_resources(_settings(), ingest_if_missing=True)
    assert isinstance(resources.retriever, SerializedRetriever)
    # ingest and search share the embedder: the 2 GB model is loaded once
    assert len(fakes.ingest_embedders) == 1
    assert fakes.ingest_embedders[0] is fakes.open_embedders[0] is fakes.open_embedders[1]


def test_failed_first_start_gives_a_hebrew_message(
    first_start: Callable[[bool], _FirstStart],
) -> None:
    first_start(False)
    with pytest.raises(ui.FirstStartError) as caught:
        ui.load_resources(_settings(), ingest_if_missing=True)
    assert ui.startup_message(caught.value) == text.FIRST_START_FAILED


def test_ingest_flag_reaches_the_streamlit_process(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, str] = {}

    def fake_call(command: list[str], cwd: Any, env: dict[str, str]) -> int:
        seen.update(env)
        return 0

    monkeypatch.setattr(ui.subprocess, "call", fake_call)
    monkeypatch.delenv(ui.INGEST_ENV, raising=False)
    args = argparse.Namespace(port=8501, address="0.0.0.0", ingest_if_missing=True)
    assert ui.run(args) == 0 and seen[ui.INGEST_ENV] == "1"
    monkeypatch.setenv(ui.INGEST_ENV, "1")
    assert ui.ingest_if_missing()
    monkeypatch.setenv(ui.INGEST_ENV, "0")
    assert not ui.ingest_if_missing()
