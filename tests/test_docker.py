"""Static checks of the Docker setup (CW-402); they need no Docker.

What they guard: no secret or publisher content can enter the image, the API key
is never a build argument or baked into ENV, the container runs as a non-root
user, and the image builds the model and index into the volume at first start.
"""

from __future__ import annotations

import fnmatch
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DOCKERFILE = (ROOT / "Dockerfile").read_text(encoding="utf-8")
IGNORE_LINES = [
    line.strip()
    for line in (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
    if line.strip() and not line.startswith("#")
]
# Instructions only, without comment lines (a comment may name the key on purpose).
INSTRUCTIONS = "\n".join(
    line for line in DOCKERFILE.splitlines() if not line.lstrip().startswith("#")
)


def _matches(path: str, pattern: str) -> bool:
    """fnmatch's "*" also crosses "/", so "**/x" is tried at the root and below."""
    if pattern.startswith("**/"):
        tail = pattern[3:]
        return fnmatch.fnmatchcase(path, tail) or fnmatch.fnmatchcase(path, "*/" + tail)
    return fnmatch.fnmatchcase(path, pattern)


def ignored(path: str) -> bool:
    """Docker's rule, simplified enough for this file: the last matching pattern
    wins, "!" re-includes, and a pattern that matches a folder covers what is in it."""
    parts = path.split("/")
    prefixes = ["/".join(parts[: i + 1]) for i in range(len(parts))]
    result = False
    for line in IGNORE_LINES:
        negate = line.startswith("!")
        pattern = line.removeprefix("!").rstrip("/")
        if any(_matches(prefix, pattern) for prefix in prefixes):
            result = not negate
    return result


@pytest.mark.parametrize(
    "path",
    [
        ".env",
        ".env.local",
        "config/.env",
        "app/.env",
        "data/raw/mg-s6.html",
        "data/index/chroma.sqlite3",
        "data/huggingface/hub/model.safetensors",
        "logs/turns.jsonl",
        "eval/runs/answer-tuning-final/answers.jsonl",
        ".git/config",
        ".venv/bin/python",
        "src/carwise/__pycache__/config.cpython-313.pyc",
        ".streamlit/secrets.toml",
        "config/server.key",
        "tests/test_ui.py",
        "pr-e3-description.md",
    ],
)
def test_secrets_data_and_local_files_stay_out_of_the_build_context(path: str) -> None:
    assert ignored(path), path


@pytest.mark.parametrize(
    "path",
    [
        "pyproject.toml",
        "uv.lock",
        "README.md",
        "src/carwise/pipeline.py",
        "src/carwise/llm/prompts/generate.v3.txt",
        "app/ui.py",
        "eval/questions.yaml",
        "config/settings.yaml",
        "config/cars.yaml",
    ],
)
def test_what_the_image_needs_is_in_the_build_context(path: str) -> None:
    assert not ignored(path), path


def test_the_api_key_is_never_a_build_argument_or_baked_into_env() -> None:
    assert not re.search(r"^\s*ARG\b", INSTRUCTIONS, re.MULTILINE)
    assert not re.search(r"OPENAI|API_KEY|SECRET|TOKEN", INSTRUCTIONS, re.IGNORECASE)


def test_runs_as_a_non_root_user() -> None:
    users = re.findall(r"^USER\s+(\S+)", INSTRUCTIONS, re.MULTILINE)
    assert users and users[-1] not in {"root", "0"}


def test_base_image_is_python_313_slim_pinned_by_digest() -> None:
    bases = re.findall(r"^FROM\s+(\S+)", INSTRUCTIONS, re.MULTILINE)
    assert bases and all(
        re.fullmatch(r"python:3\.13\.\d+-slim@sha256:[0-9a-f]{64}", b) for b in bases
    )


def test_installs_exactly_the_lock_file_without_dev_tools() -> None:
    syncs = re.findall(r"uv sync[^\n]*", INSTRUCTIONS)
    assert syncs and all("--locked" in s and "--no-dev" in s for s in syncs)


def test_articles_model_and_index_are_not_baked_in() -> None:
    copies = re.findall(r"^COPY\s+(?:--from=\S+\s+)?(\S+)", INSTRUCTIONS, re.MULTILINE)
    assert not any(src.startswith(("data", "logs", ".env")) for src in copies)
    assert "HF_HOME=/app/data/" in INSTRUCTIONS  # the model downloads into the volume
    assert 'VOLUME ["/app/data"]' in INSTRUCTIONS


def test_healthcheck_and_first_start_command() -> None:
    assert "HEALTHCHECK" in INSTRUCTIONS and "/_stcore/health" in INSTRUCTIONS
    command = re.findall(r"^CMD\s+(.+)$", INSTRUCTIONS, re.MULTILINE)[-1]
    assert '"--address", "0.0.0.0"' in command and '"--ingest-if-missing"' in command
