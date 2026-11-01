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
import yaml

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


@pytest.mark.parametrize("doc", ["README.md", "docs/docker.md", "Dockerfile"])
def test_documented_run_command_publishes_on_loopback_only(doc: str) -> None:
    """CW-605: a bare -p 8501:8501 publishes the unauthenticated UI on every interface."""
    text = (ROOT / doc).read_text(encoding="utf-8")
    runs = [line for line in text.splitlines() if "docker run" in line]
    assert runs and all("-p 127.0.0.1:8501:8501" in line for line in runs), runs


# --- compose.yaml (CW-621): the same loopback, key and volume rules as docker run ---


def _compose_service() -> dict[str, object]:
    compose = yaml.safe_load((ROOT / "compose.yaml").read_text(encoding="utf-8"))
    service = compose["services"]["carwise"]
    assert isinstance(service, dict)
    return service


def test_compose_publishes_on_loopback_only() -> None:
    ports = _compose_service()["ports"]
    assert isinstance(ports, list) and ports
    assert all(str(port).startswith("127.0.0.1:") for port in ports), ports


def test_compose_takes_the_key_from_the_shell_or_env_file_never_a_literal() -> None:
    environment = _compose_service()["environment"]
    assert isinstance(environment, dict)
    assert re.fullmatch(r"\$\{OPENAI_API_KEY:\?[^}]+\}", str(environment["OPENAI_API_KEY"]))
    assert not any("sk-" in str(value) for value in environment.values())
    assert "sk-" not in (ROOT / "compose.yaml").read_text(encoding="utf-8")


def test_compose_uses_the_same_named_volume_as_docker_run() -> None:
    compose = yaml.safe_load((ROOT / "compose.yaml").read_text(encoding="utf-8"))
    assert compose["volumes"]["carwise-data"]["name"] == "carwise-data"
    assert "carwise-data:/app/data" in _compose_service()["volumes"]  # type: ignore[operator]


def test_compose_builds_the_repo_image_and_keeps_its_healthcheck() -> None:
    service = _compose_service()
    assert service["build"] == "."
    assert service["image"] == "carwise"
    assert service.get("restart", "no") == "no"
    assert "healthcheck" not in service
    # host networking would bypass the loopback-only port mapping
    assert "network_mode" not in service


def test_makefile_has_a_compose_target() -> None:
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    assert re.search(r"^docker-up:\n\tdocker compose up --build$", makefile, re.MULTILINE)
    assert re.search(r"^\.PHONY:.*\bdocker-up\b", makefile, re.MULTILINE)


@pytest.mark.parametrize("doc", ["README.md", "docs/docker.md"])
def test_every_documented_port_mapping_is_loopback(doc: str) -> None:
    """CW-621: covers compose and prose too, not only docker run lines."""
    text = (ROOT / doc).read_text(encoding="utf-8")
    lines = [line for line in text.splitlines() if "8501:8501" in line]
    assert all("127.0.0.1:8501:8501" in line for line in lines), lines
