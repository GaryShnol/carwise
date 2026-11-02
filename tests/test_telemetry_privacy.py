"""The turn log holds no user words, and the CLI labels it with the profile it runs (CW-613)."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from app import chat
from app.__main__ import main
from carwise.config import Settings, load_settings
from carwise.llm.fake import FakeLLMClient
from carwise.schemas import RefusalReason
from carwise.telemetry import TurnLogger
from tests.test_pipeline import SpyRetriever, generation, make, understanding

PLANTED = "Zorblax"  # a word no registry, config or chunk holds


def _line(logger: TurnLogger) -> str:
    return logger.path.read_text(encoding="utf-8").strip().split("\n")[-1]


def _logger(tmp_path: Path) -> TurnLogger:
    return TurnLogger(tmp_path, profile="dev", models={"understand": "a", "generate": "b"})


def test_unknown_car_names_are_counted_never_logged(tmp_path: Path) -> None:
    logger = _logger(tmp_path)
    named = [f"{PLANTED} Q7", f"{PLANTED}-טורבו"]
    message = f"מה דעתך על {PLANTED} Q7 ועל {PLANTED}-טורבו?"
    reply = understanding(unrecognized=named, question=message)
    pipeline, _, _ = make([reply], logger=logger)
    answer = pipeline.ask(message, [])
    assert answer.refusal is RefusalReason.UNKNOWN_CAR and answer.not_covered == named
    line = _line(logger)
    assert PLANTED not in line  # not in the names, not from the message
    record = json.loads(line)
    assert record["not_covered_count"] == 2 and "not_covered" not in record


def test_model_written_ids_that_are_not_chunk_ids_are_counted_never_logged(
    tmp_path: Path,
) -> None:
    # A cited id is the model's free text; a prompt injection can make it the user's words.
    logger = _logger(tmp_path)
    ids = ["mg_s6:000", "audi_rs3:099", f"{PLANTED} is here"]
    pipeline, _, _ = make([understanding(cars=["mg_s6"]), generation(ids=ids)], logger=logger)
    answer = pipeline.ask("כמה טווח יש ל-MG S6?", [])
    assert answer.dropped_chunk_ids == ["audi_rs3:099", f"{PLANTED} is here"]
    line = _line(logger)
    assert PLANTED not in line
    record = json.loads(line)
    assert record["dropped_chunk_ids"] == ["audi_rs3:099"]  # well-formed ids stay useful
    assert record["dropped_other_ids"] == 1


# --- the CLI's profile label -----------------------------------------------------------------
@pytest.fixture
def cli(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[dict[str, Any]]:
    """`python -m app chat` with one question, a fake model and a fake index."""
    seen: dict[str, Any] = {}
    settings = load_settings()
    retrieval = settings.retrieval.model_copy(update={"relevance_threshold": 0.0})
    paths = settings.paths.model_copy(update={"log_dir": str(tmp_path)})
    patched: Settings = settings.model_copy(update={"retrieval": retrieval, "paths": paths})

    def client(_settings: Settings, profile: Any) -> FakeLLMClient:
        seen["profile"] = profile
        return FakeLLMClient([understanding(cars=["mg_s6"]), generation()])

    lines = iter(["כמה טווח יש ל-MG S6?"])

    def ask(_prompt: str) -> str:
        try:
            return next(lines)
        except StopIteration:
            raise EOFError from None

    monkeypatch.setattr(chat, "load_settings", lambda: patched)
    monkeypatch.setattr(chat, "open_retriever", lambda s: SpyRetriever(s))
    monkeypatch.setattr(chat, "OpenAIClient", client)
    monkeypatch.setattr("builtins.input", ask)
    seen["log"] = tmp_path / "turns.jsonl"
    yield seen


def _logged(seen: dict[str, Any]) -> dict[str, Any]:
    line = seen["log"].read_text(encoding="utf-8").strip().split("\n")[-1]
    record: dict[str, Any] = json.loads(line)
    return record


def test_cli_logs_the_profile_from_the_environment(
    cli: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CARWISE_PROFILE", "final")  # as `.env` sets it, without --profile
    assert main(["chat"]) == 0
    final = load_settings().profiles["final"]
    record = _logged(cli)
    assert record["profile"] == "final" and cli["profile"] == final
    assert record["models"] == {
        "understand": final.understand_model,
        "generate": final.generate_model,
    }


def test_cli_profile_flag_overrides_the_environment(
    cli: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CARWISE_PROFILE", "final")
    assert main(["chat", "--profile", "dev"]) == 0
    dev = load_settings().profiles["dev"]
    record = _logged(cli)
    assert record["profile"] == "dev" and cli["profile"] == dev
    assert record["models"]["generate"] == dev.generate_model


def test_profile_name_is_resolved_flag_then_environment_then_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = load_settings()
    monkeypatch.delenv("CARWISE_PROFILE", raising=False)
    assert settings.profile_name() == settings.default_profile
    monkeypatch.setenv("CARWISE_PROFILE", "final")
    assert settings.profile_name() == "final"
    assert settings.profile_name("dev") == "dev"
    assert settings.profile() == settings.profiles["final"]
    monkeypatch.setenv("CARWISE_PROFILE", "nope")
    with pytest.raises(ValueError, match="Unknown profile"):
        settings.profile_name()
