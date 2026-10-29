"""Single entry point: `python -m app <ingest|chat|eval|ui>`.

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

from app import ingest

COMMANDS: dict[str, Callable[[], int]] = {
    "ingest": ingest.run,
}
# Command -> board ticket that implements it. Moved to COMMANDS as they land.
PENDING = {
    "chat": "CW-105",
    "eval": "CW-302",
    "ui": "CW-401",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app", description="carwise")
    parser.add_argument("--profile", help="config profile (dev or final)")
    parser.add_argument("command", choices=sorted([*COMMANDS, *PENDING]))
    return parser


def use_utf8_output() -> None:
    """Windows consoles default to a legacy code page that cannot print Hebrew."""
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.profile:
        os.environ["CARWISE_PROFILE"] = args.profile
    if args.command in COMMANDS:
        use_utf8_output()
        return COMMANDS[args.command]()
    print(f"'{args.command}' is not implemented yet (see {PENDING[args.command]} in BOARD.md).")
    return 2


if __name__ == "__main__":
    sys.exit(main())
