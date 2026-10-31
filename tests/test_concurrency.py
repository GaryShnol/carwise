"""What the UI shares across browser sessions is safe under threads (CW-401 review).

Streamlit runs each browser session on its own thread, and the UI shares one
retriever and one TurnLogger between them. Each test runs two threads that
start together at a barrier.
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from carwise import telemetry
from carwise.llm.fake import FakeLLMClient
from carwise.pipeline import Pipeline
from carwise.retrieval.retriever import SerializedRetriever
from carwise.schemas import RetrievedChunk
from carwise.telemetry import TurnLogger
from tests.test_pipeline import REGISTRY, SpyRetriever, _settings, generation, make, understanding

THREADS = 2
TURNS = 25


def run_together(work: Callable[[int], None]) -> None:
    """Run work(0) and work(1) on two threads released at the same moment."""
    barrier = threading.Barrier(THREADS)
    errors: list[BaseException] = []

    def target(index: int) -> None:
        try:
            barrier.wait()
            work(index)
        except BaseException as error:  # surfaced in the main thread below
            errors.append(error)

    threads = [threading.Thread(target=target, args=(i,)) for i in range(THREADS)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert not errors, errors


def test_logger_writes_whole_lines_with_unique_turn_numbers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pipeline, _, _ = make([understanding(cars=["mg_s6"]), generation()])
    answer = pipeline.ask("כמה טווח יש ל-MG S6?", [])
    logger = TurnLogger(tmp_path, profile="dev", models={"understand": "a", "generate": "b"})
    record = telemetry.turn_record
    probe = {"active": 0, "most": 0}
    count = threading.Lock()

    def probed(*args: Any, **kwargs: Any) -> dict[str, object]:
        # Counts log calls inside the critical section at once, and holds each one
        # open a moment so that, without the lock, the two threads would overlap.
        with count:
            probe["active"] += 1
            probe["most"] = max(probe["most"], probe["active"])
        time.sleep(0.002)
        with count:
            probe["active"] -= 1
        return record(*args, **kwargs)

    monkeypatch.setattr(telemetry, "turn_record", probed)
    run_together(lambda _: [logger.log(answer, message_chars=10) for _ in range(TURNS)])
    assert probe["most"] == 1
    lines = logger.path.read_text(encoding="utf-8").splitlines()
    turns = [json.loads(line)["process_turn"] for line in lines]  # every line is whole JSON
    assert sorted(turns) == list(range(1, THREADS * TURNS + 1))


class _Overlap:
    """A retriever that records how many calls run at the same time."""

    def __init__(self) -> None:
        self.active = 0
        self.most = 0
        self._count = threading.Lock()

    def _call(self) -> list[RetrievedChunk]:
        with self._count:
            self.active += 1
            self.most = max(self.most, self.active)
        time.sleep(0.005)
        with self._count:
            self.active -= 1
        return []

    def search(self, query: str, car_ids: Any = None, top_k: Any = None) -> list[RetrievedChunk]:
        return self._call()

    def search_per_car(self, query: str, car_ids: Any, top_k_per_car: Any = None) -> Any:
        return self._call()

    def search_all(self, query: str, top_k: Any = None, per_car_cap: Any = None) -> Any:
        return self._call()

    def spec_boxes(self, query: str, car_ids: Any) -> list[RetrievedChunk]:
        return self._call()


def test_the_overlap_probe_sees_concurrent_calls_without_the_lock() -> None:
    inner = _Overlap()
    run_together(lambda _: [inner.search("q") for _ in range(10)])
    assert inner.most == THREADS  # the probe works: unwrapped calls do overlap


def test_serialized_retriever_runs_one_call_at_a_time() -> None:
    inner = _Overlap()
    shared = SerializedRetriever(inner)

    def work(_: int) -> None:
        for _ in range(10):
            shared.search("q")
            shared.search_per_car("q", ["mg_s6"])
            shared.search_all("q")
            shared.spec_boxes("q", ["mg_s6"])

    run_together(work)
    assert inner.most == 1


def test_two_sessions_share_retriever_and_logger(tmp_path: Path) -> None:
    settings = _settings()
    shared = SerializedRetriever(SpyRetriever(settings))
    logger = TurnLogger(tmp_path, profile="dev", models={"understand": "a", "generate": "b"})
    answers: dict[int, list[str]] = {0: [], 1: []}

    def work(index: int) -> None:
        replies: list[Any] = []
        for _ in range(TURNS):
            replies += [understanding(cars=["mg_s6"]), generation()]
        pipeline = Pipeline(settings, REGISTRY, shared, FakeLLMClient(replies), logger=logger)
        for _ in range(TURNS):
            answer = pipeline.ask("כמה טווח יש ל-MG S6?", [])
            answers[index].append(answer.text)
            assert answer.refusal is None and answer.sources

    run_together(work)
    assert len(answers[0]) == len(answers[1]) == TURNS
    assert len(logger.path.read_text(encoding="utf-8").splitlines()) == THREADS * TURNS
