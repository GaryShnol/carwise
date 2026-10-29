"""Single entry point: `python -m app <ingest|chat|eval|ui>`.

Why it lives in app/ and not in the core package: the dependency direction is
app and eval -> src/carwise, never the reverse, and `python -m` with a
subcommand works in PowerShell where `make` is not installed.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence

# Command -> board ticket that implements it. Replaced by real handlers as they land.
PENDING = {
    "ingest": "CW-101",
    "chat": "CW-105",
    "eval": "CW-302",
    "ui": "CW-401",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app", description="carwise")
    parser.add_argument("--profile", help="config profile (dev or final)")
    parser.add_argument("command", choices=sorted(PENDING))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.profile:
        os.environ["CARWISE_PROFILE"] = args.profile
    print(f"'{args.command}' is not implemented yet (see {PENDING[args.command]} in BOARD.md).")
    return 2


if __name__ == "__main__":
    sys.exit(main())
