"""Single entry point: `python -m app <ingest|search|chat|eval|ui>`.

Why it lives in app/ and not in the core package: the dependency direction is
app and eval -> src/carwise, never the reverse, and `python -m` with a
subcommand works in PowerShell where `make` is not installed.
"""

from __future__ import annotations

import argparse
import io
import os
import sys
from collections.abc import Callable, Sequence

from app import chat, ingest, search
from eval import cli as eval_cli

Command = Callable[[argparse.Namespace], int]
# Command -> (handler, adds its arguments to the subparser, help line).
COMMANDS: dict[str, tuple[Command, Callable[[argparse.ArgumentParser], None] | None, str]] = {
    "ingest": (ingest.run, None, "fetch, clean, chunk and index the articles"),
    "search": (search.run, search.add_arguments, "show retrieved chunks for a query (dev)"),
    "chat": (chat.run, chat.add_arguments, "chat in Hebrew about the eight reviewed cars"),
    "eval": (eval_cli.run, eval_cli.add_arguments, "run the eval (retrieval level is free)"),
}
# Command -> board ticket that implements it. Moved to COMMANDS as they land.
PENDING = {
    "ui": "CW-401",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app", description="carwise")
    parser.add_argument("--profile", help="config profile (dev or final)")
    commands = parser.add_subparsers(dest="command", required=True, metavar="command")
    for name, (_, add_arguments, help_line) in COMMANDS.items():
        subparser = commands.add_parser(name, help=help_line)
        if add_arguments:
            add_arguments(subparser)
    for name, ticket in PENDING.items():
        commands.add_parser(name, help=f"not implemented yet ({ticket})")
    return parser


def use_utf8_output() -> None:
    """Windows consoles default to a legacy code page that cannot print or read Hebrew."""
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if getattr(args, "profile", None):
        os.environ["CARWISE_PROFILE"] = args.profile
    if args.command in COMMANDS:
        use_utf8_output()
        return COMMANDS[args.command][0](args)
    print(f"'{args.command}' is not implemented yet (see {PENDING[args.command]} in BOARD.md).")
    return 2


if __name__ == "__main__":
    sys.exit(main())
