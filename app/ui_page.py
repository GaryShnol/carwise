"""The chat page itself: imported by app/ui.py once the title is on screen.

Why it is thin: like the CLI, it holds a Session and calls `Pipeline.answer`
(which is `Pipeline.ask` plus the session update); the pipeline owns every
decision. This module only lays out what an Answer already contains: the text,
the retrieved chunks with scores, tokens and cost, and the refusal state.

Why the model is shared and the client is not: the embedding model and the
index load once per process (about a minute cold), so every browser session
reuses them; the LLM client holds the cost cap, so each browser session gets
its own, and the cap bounds one conversation as it does in the CLI.
"""

from __future__ import annotations

import logging

import streamlit as st

from app import ui_support as ui
from app import ui_text as labels
from app.chat import RESET_COMMAND, run_command
from carwise.config import Settings, load_settings
from carwise.llm.base import LLMConfigError
from carwise.preferences import EMPTY_PREFERENCES, Session
from carwise.registry import Registry
from carwise.retrieval.store import IndexNotReadyError
from carwise.schemas import Answer

log = logging.getLogger("carwise.ui")


@st.cache_resource(show_spinner=False)
def shared_resources() -> ui.Resources:
    return ui.load_resources(load_settings(), ingest_if_missing=ui.ingest_if_missing())


def render_answer(answer: Answer, settings: Settings, registry: Registry) -> None:
    text = ui.as_markdown(answer.text)
    style = ui.refusal_style(answer)
    if style == "info":
        st.info(text, icon="ℹ️")
    elif style == "warning":
        st.warning(text, icon="⚠️")
    else:
        st.markdown(text)
    rows = ui.source_rows(answer, settings.display.max_section_chars)
    if rows:
        with st.expander(labels.SOURCES_TITLE.format(count=len(rows))):
            st.markdown(ui.sources_markdown(rows))
    links = ui.article_links(answer, registry)
    if links:
        st.markdown(ui.links_markdown(links))
    st.caption(ui.as_markdown(ui.cost_line(answer)))


def render_sidebar(session: Session, answers: list[Answer]) -> None:
    with st.sidebar:
        st.header(labels.SIDEBAR_TITLE)
        st.caption(labels.SIDEBAR_HELP)
        rows = ui.preference_rows(session.preferences)
        if not rows:
            st.markdown(EMPTY_PREFERENCES)
        for label, value, source in rows:
            st.markdown(f"**{label}:** {ui.as_markdown(value)}")
            st.caption(ui.as_markdown(f'{labels.SOURCE_PREFIX}: "{source}"'))
        if st.button(labels.RESET_BUTTON, width="stretch"):
            # The same command as /reset in the CLI: history and preferences go.
            reply = run_command(RESET_COMMAND, session) or ""
            st.session_state.turns = []
            st.toast(reply)
            st.rerun()
        st.divider()
        st.caption(
            ui.as_markdown(labels.SESSION_COST.format(cost=sum(a.cost_usd for a in answers)))
        )


def render() -> None:
    """Everything below the title; the title and the first loading message are
    already on the page (app/ui.py)."""
    settings = load_settings()
    state = st.session_state

    if "llm" not in state:
        try:
            state.llm = ui.new_llm(settings)
        except LLMConfigError as error:
            st.error(ui.startup_message(error))
            st.stop()
    try:
        with st.spinner(labels.LOADING):
            resources = shared_resources()
    except (IndexNotReadyError, ui.FirstStartError) as error:
        st.error(ui.startup_message(error))
        st.stop()
    if "pipeline" not in state:
        state.pipeline = ui.new_pipeline(resources, state.llm)
        state.session = Session(history_window=settings.llm.history_window)
        state.turns = []  # (role, text or Answer), for display only
        state.stopped = False
    session: Session = state.session

    message = st.chat_input(
        labels.INPUT_PLACEHOLDER,
        max_chars=settings.input.max_message_chars,
        disabled=state.stopped,
    )
    # Without accept_file the value is a plain string.
    if isinstance(message, str) and message.strip():
        state.turns.append(("user", message))
        command_output = run_command(message, session)
        if command_output is not None:  # /prefs and /reset work here as in the CLI
            state.turns = [] if message.strip() == RESET_COMMAND else state.turns
            state.turns.append(("assistant", command_output))
        else:
            try:
                with st.spinner(labels.THINKING):
                    answer = state.pipeline.answer(message, session)
                state.turns.append(("assistant", answer))
                if ui.stops_session(answer):
                    # The input box above was drawn enabled; draw the page again.
                    state.stopped = True
                    st.rerun()
            except Exception:
                # The pipeline turns provider failures into Hebrew refusals already;
                # this is the last line, so the user never sees a stack trace.
                log.exception("turn failed")
                state.turns.append(("assistant", labels.UNEXPECTED))

    answers = [item for _, item in state.turns if isinstance(item, Answer)]
    render_sidebar(session, answers)
    with st.chat_message("assistant"):
        st.markdown(ui.as_markdown(state.pipeline.greeting()))
    for role, item in state.turns:
        with st.chat_message(role):
            if isinstance(item, Answer):
                render_answer(item, settings, resources.registry)
            else:
                st.markdown(ui.as_markdown(item))
    if state.stopped:
        st.warning(labels.STOPPED)
