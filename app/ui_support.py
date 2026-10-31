"""Everything the Streamlit UI needs that is not Streamlit: wiring, display text, launch.

Why a separate module: `app/ui.py` is a Streamlit script (it runs top to bottom on
every interaction), so its helpers live here, where unit tests import them
without a browser and the smoke test can swap the heavy wiring for fakes. Like
the CLI, nothing here decides anything about an answer: the pipeline does, and
these helpers only turn its `Answer` into rows and lines to show.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from app.ui_text import (
    ARTICLES_PREFIX,
    CITED_MARK,
    FIRST_START_FAILED,
    INDEX_MISSING,
    MISSING_KEY,
    SOURCES_HEADERS,
    UNEXPECTED,
)
from carwise.config import Settings, load_settings
from carwise.guardrails import section_label
from carwise.ingest.run import ingest
from carwise.llm.base import LLMClient, LLMConfigError
from carwise.llm.openai_client import OpenAIClient
from carwise.pipeline import Pipeline
from carwise.preferences import FIELD_LABELS
from carwise.registry import Registry, load_registry
from carwise.retrieval.embedder import make_embedder
from carwise.retrieval.retriever import ChunkRetriever, SerializedRetriever, open_retriever
from carwise.retrieval.store import IndexNotReadyError
from carwise.schemas import Answer, Preferences, RefusalReason
from carwise.telemetry import TurnLogger

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = Path(__file__).resolve().parent / "ui.py"
DEFAULT_PORT = 8501
INGEST_ENV = "CARWISE_INGEST_IF_MISSING"


class FirstStartError(RuntimeError):
    """Ingest at first start did not finish (articles blocked or missing, or index build)."""


def ingest_if_missing() -> bool:
    """Set by `python -m app ui --ingest-if-missing` for the Streamlit process (Docker)."""
    return os.environ.get(INGEST_ENV) == "1"


@dataclass(frozen=True)
class Resources:
    """What every browser session shares: loaded once per process (model, index)."""

    settings: Settings
    registry: Registry
    retriever: ChunkRetriever
    logger: TurnLogger | None


def load_resources(settings: Settings, *, ingest_if_missing: bool = False) -> Resources:
    """Open the index and load the embedding model now, not on the first question.

    Raises IndexNotReadyError when ingest has not run. With ingest_if_missing (the
    Docker image's first start) it runs ingest instead: fetch the articles politely,
    download the model, build the index, all into the mounted volume, while the
    page shows its loading state. Raises FirstStartError when that fails."""
    embedder = make_embedder(settings.embeddings)  # one model load for ingest and search
    try:
        retriever = open_retriever(settings, embedder)
    except IndexNotReadyError:
        if not ingest_if_missing:
            raise
        result = ingest(settings, embedder=embedder)
        if not result.ok:
            raise FirstStartError(
                result.fallback or result.index_error or "ingest failed"
            ) from None
        retriever = open_retriever(settings, embedder)
    retriever.warm_up()
    profile = settings.profile()
    logger = TurnLogger(
        Path(settings.paths.log_dir),
        profile=os.environ.get("CARWISE_PROFILE") or settings.default_profile,
        models={"understand": profile.understand_model, "generate": profile.generate_model},
    )
    # Shared by every browser session's thread: one retrieval at a time.
    return Resources(settings, load_registry(), SerializedRetriever(retriever), logger)


def new_llm(settings: Settings) -> LLMClient:
    """One client per browser session, so the cost cap bounds one conversation, as
    in the CLI. Raises LLMConfigError when the API key is missing (no network call)."""
    return OpenAIClient(settings, settings.profile())


def new_pipeline(resources: Resources, llm: LLMClient) -> Pipeline:
    return Pipeline(
        resources.settings, resources.registry, resources.retriever, llm, logger=resources.logger
    )


def startup_message(error: Exception) -> str:
    """A Hebrew message for a start-up failure; never the exception text, which is English."""
    if isinstance(error, LLMConfigError):
        return MISSING_KEY
    if isinstance(error, IndexNotReadyError):
        return INDEX_MISSING
    if isinstance(error, FirstStartError):
        return FIRST_START_FAILED
    return UNEXPECTED


# --- turning an Answer into what the page shows --------------------------------------
@dataclass(frozen=True)
class SourceRow:
    car: str
    section: str
    score: float
    cited: bool


def source_rows(answer: Answer, max_section_chars: int) -> list[SourceRow]:
    """Every chunk retrieved this turn, best first, marking the ones the answer cited.

    Why all of them and not only the cited ones: the gate and the answer both
    depend on what was retrieved, so showing it is what makes grounding visible."""
    cited = {source.chunk_id for source in answer.sources}
    return [
        SourceRow(
            car=hit.chunk.car_name,
            section=section_label(hit.chunk.section, max_section_chars),
            score=round(hit.score, 3),
            cited=hit.chunk.chunk_id in cited,
        )
        for hit in sorted(answer.retrieved, key=lambda h: h.score, reverse=True)
    ]


def article_links(answer: Answer, registry: Registry) -> list[tuple[str, str]]:
    """(car name, article URL) for each car the answer cited, in citation order.

    Why from the registry: the URL is trusted data checked at load time (https, the
    article's slug), so a link can never come from model output or article text."""
    links: dict[str, tuple[str, str]] = {}
    for source in answer.sources:
        if source.car not in links:
            car = registry.get(source.car)
            links[source.car] = (car.display_name, car.url)
    return list(links.values())


# A right-to-left mark on each side of the separator: without it the browser's bidi
# algorithm joins a Latin-only name ("MG S6") and the separator into one
# left-to-right run, and the links read out of order in the Hebrew line.
_RLM = "‏"
LINK_SEPARATOR = f"{_RLM} · {_RLM}"


def links_markdown(links: list[tuple[str, str]]) -> str:
    """One markdown line of article links; the names cannot break the link syntax."""
    items = [f"[{_link_text(name)}]({url})" for name, url in links]
    return as_markdown(f"{ARTICLES_PREFIX}: " + LINK_SEPARATOR.join(items) + _RLM)


def _link_text(text: str) -> str:
    return "".join("\\" + c if c in "\\[]()" else c for c in text)


def _cell(text: str) -> str:
    return text.replace("|", "\\|")


def sources_markdown(rows: list[SourceRow]) -> str:
    """A markdown table of the retrieved chunks (st.dataframe does not read right to left)."""
    header = " | ".join(SOURCES_HEADERS)
    lines = [f"| {header} |", "|" + "---|" * len(SOURCES_HEADERS)]
    for row in rows:
        mark = CITED_MARK if row.cited else ""
        lines.append(f"| {_cell(row.car)} | {_cell(row.section)} | {row.score:.3f} | {mark} |")
    return as_markdown("\n".join(lines))


def cost_line(answer: Answer) -> str:
    usage = answer.usage
    seconds = answer.latency_ms.get("total", 0.0) / 1000
    return (
        f"קריאות למודל: {answer.llm_calls} · טוקנים: {usage.input_tokens} נכנסו "
        f"({usage.cached_tokens} מהמטמון), {usage.output_tokens} יצאו · "
        f"עלות משוערת: ${answer.cost_usd:.5f} · {seconds:.1f} שניות"
    )


# A refusal where the articles do not cover the question, versus one where
# something failed: the first is normal behavior, the second deserves attention.
_NOT_COVERED = {
    RefusalReason.UNKNOWN_CAR,
    RefusalReason.LOW_RELEVANCE,
    RefusalReason.OUT_OF_SCOPE,
    RefusalReason.EMPTY,
    RefusalReason.TOO_LONG,
}


def refusal_style(answer: Answer) -> str | None:
    """The box style: "info" when the corpus does not cover the question,
    "warning" when a step failed, None for a normal answer."""
    if answer.refusal is None:
        return None
    return "info" if answer.refusal in _NOT_COVERED else "warning"


def stops_session(answer: Answer) -> bool:
    """The cost cap ends the conversation: every later call would be refused (CW-204)."""
    return answer.refusal is RefusalReason.BUDGET_EXCEEDED


def preference_rows(preferences: Preferences) -> list[tuple[str, str, str]]:
    """(label, value, the user's message it came from) for each stated preference."""
    return [(FIELD_LABELS[name], pref.value, pref.source) for name, pref in preferences.items()]


def as_markdown(text: str) -> str:
    """Text for st.markdown: "$" would otherwise start LaTeX ("$0.5" in the budget reply)."""
    return text.replace("$", "\\$")


# --- `python -m app ui` --------------------------------------------------------------
def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--profile", default=argparse.SUPPRESS, help="dev or final")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    # Local only by default: Streamlit otherwise listens on every interface. The
    # Docker image passes 0.0.0.0, since the container's port is mapped explicitly.
    parser.add_argument("--address", default="localhost", help="interface to listen on")
    parser.add_argument(
        "--ingest-if-missing",
        action="store_true",
        help="build the index at first start if it is missing (the Docker image uses this)",
    )


def streamlit_command(port: int, address: str) -> list[str]:
    return [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(SCRIPT),
        f"--server.port={port}",
        f"--server.address={address}",
        # No "Deploy" button: this app is run locally or in its own container.
        "--client.toolbarMode=minimal",
        # Streamlit's own usage statistics would send events to a third party.
        "--browser.gatherUsageStats=false",
    ]


def run(args: argparse.Namespace) -> int:
    load_settings()  # fail here, in the terminal, if the config itself is broken
    # The script imports app.* and eval-free carwise; the repository root must be on
    # the path of the Streamlit process, as it is for `python -m app`.
    paths = [str(ROOT), os.environ.get("PYTHONPATH", "")]
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(path for path in paths if path)}
    if args.ingest_if_missing:
        env[INGEST_ENV] = "1"
    try:
        return subprocess.call(streamlit_command(args.port, args.address), cwd=ROOT, env=env)
    except KeyboardInterrupt:
        return 0
