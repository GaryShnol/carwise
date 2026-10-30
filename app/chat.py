"""`python -m app chat`: a Hebrew command-line conversation.

Why it is thin: the pipeline owns every decision; this loop only reads a line,
calls `Pipeline.ask`, prints the answer with its sources, and keeps the
history window. Output is Hebrew, which most terminals print left to right;
the words are correct, only the visual order of a mixed line may look off.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from carwise.config import load_settings
from carwise.llm.base import BudgetExceededError, LLMConfigError
from carwise.llm.openai_client import OpenAIClient
from carwise.pipeline import Pipeline
from carwise.preferences import RESET_REPLY, Session
from carwise.preferences import describe as describe_preferences
from carwise.registry import load_registry
from carwise.retrieval.retriever import open_retriever
from carwise.retrieval.store import IndexNotReadyError
from carwise.schemas import Answer
from carwise.telemetry import TurnLogger

EXIT_COMMANDS = {"/exit", "/quit", "יציאה"}
PREFS_COMMAND = "/prefs"
RESET_COMMAND = "/reset"
HELP_LINE = "(העדפות: /prefs | שיחה חדשה: /reset | יציאה: /exit)"
PROMPT = "\nשאלה> "


def run_command(line: str, session: Session) -> str | None:
    """Output of a chat command, or None when the line is a question for the bot."""
    command = line.strip()
    if command == PREFS_COMMAND:
        return describe_preferences(session.preferences)
    if command == RESET_COMMAND:
        session.reset()
        return RESET_REPLY
    return None


def add_arguments(parser: argparse.ArgumentParser) -> None:
    # SUPPRESS keeps a `--profile` given before the subcommand from being reset to None.
    parser.add_argument("--profile", default=argparse.SUPPRESS, help="dev or final")
    parser.add_argument(
        "--show-cost", action="store_true", help="print tokens, cost and latency per answer"
    )


def format_answer(answer: Answer, *, show_cost: bool) -> str:
    lines = [answer.text]
    if answer.sources:
        lines.append("\nמקורות:")
        seen: set[tuple[str, str]] = set()
        for source in answer.sources:
            if (source.car, source.section) in seen:
                continue
            seen.add((source.car, source.section))
            lines.append(f"  - {source.car_name} | {source.section} | {source.source_url}")
    if show_cost:
        usage = answer.usage
        stages = ", ".join(f"{stage} {ms:.0f}" for stage, ms in answer.latency_ms.items())
        lines.append(
            f"\n[{answer.llm_calls} LLM calls | tokens in {usage.input_tokens} "
            f"(cached {usage.cached_tokens}) out {usage.output_tokens} | "
            f"${answer.cost_usd:.5f} | ms: {stages}"
            + (f" | refusal: {answer.refusal.value}" if answer.refusal else "")
            + (f" | flags: {', '.join(answer.flags)}" if answer.flags else "")
            + "]"
        )
    return "\n".join(lines)


def run(args: argparse.Namespace) -> int:
    settings = load_settings()
    profile_name = getattr(args, "profile", None)
    profile = settings.profile(profile_name)
    try:
        retriever = open_retriever(settings)
        llm = OpenAIClient(settings, profile)
    except (IndexNotReadyError, LLMConfigError) as error:
        print(error)
        return 1
    logger = TurnLogger(
        Path(settings.paths.log_dir),
        profile=profile_name or settings.default_profile,
        models={"understand": profile.understand_model, "generate": profile.generate_model},
    )
    pipeline = Pipeline(
        settings, load_registry(), retriever, llm, profile=profile_name, logger=logger
    )
    print("טוען את מודל החיפוש...", flush=True)
    retriever.warm_up()  # otherwise the first question pays the model load (~1 min cold)
    print(pipeline.greeting())
    print(HELP_LINE)
    session = Session(history_window=settings.llm.history_window)
    while True:
        try:
            message = input(PROMPT)
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if message.strip() in EXIT_COMMANDS:
            return 0
        if not message.strip():
            continue
        output = run_command(message, session)
        if output is not None:
            print(output)
            continue
        try:
            answer = pipeline.answer(message, session)
        except BudgetExceededError as error:
            print(error)
            return 1
        print(format_answer(answer, show_cost=args.show_cost))
