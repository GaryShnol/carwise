"""The UI server's spend cap over every browser session (CW-605).

Each UI session has its own OpenAIClient and llm.max_cost_usd; a refresh opens a new
one. These tests run real clients over the stub SDK (tests.test_llm) with one
SharedBudget between them, as app/ui_support.new_llm wires them.
"""

from __future__ import annotations

import threading
from typing import Any, cast

import pytest
from openai import OpenAI

from carwise.config import Settings, load_settings
from carwise.llm.base import (
    BudgetExceededError,
    SharedBudgetExceededError,
    Usage,
    cost_usd,
)
from carwise.llm.budget import SharedBudget
from carwise.llm.openai_client import OpenAIClient
from carwise.pipeline import Pipeline
from carwise.registry import load_registry
from carwise.schemas import RefusalReason
from tests.test_concurrency import run_together
from tests.test_llm import MODEL, VALID, StubSDK, _ask, _completion
from tests.test_pipeline import SpyRetriever

REGISTRY = load_registry()
PROMPT, OUT = 10_000, 100  # one stub call; its cost is CALL below
CALL = cost_usd(Usage(PROMPT, 0, OUT), load_settings().prices[MODEL])


def _settings(session_cap: float = 2.0, total: float = 5.0) -> Settings:
    settings = load_settings()
    llm = settings.llm.model_copy(update={"max_cost_usd": session_cap, "max_total_cost_usd": total})
    retrieval = settings.retrieval.model_copy(update={"relevance_threshold": 0.0})
    return settings.model_copy(update={"llm": llm, "retrieval": retrieval})


def _client(stub: StubSDK, budget: SharedBudget | None, settings: Settings) -> OpenAIClient:
    return OpenAIClient(settings, sdk=cast(OpenAI, stub), shared_budget=budget)


def _calls(count: int, content: str = VALID) -> StubSDK:
    return StubSDK(*(_completion(content, prompt=PROMPT, out=OUT) for _ in range(count)))


def test_configured_total_is_above_the_session_cap() -> None:
    llm = load_settings().llm
    assert llm.max_cost_usd == 2.0  # the session cap is unchanged (CW-605)
    assert llm.max_total_cost_usd > llm.max_cost_usd


def test_two_sessions_charge_one_shared_total() -> None:
    budget = SharedBudget(5.0)
    first, second = _calls(2), _calls(1)
    a, b = _client(first, budget, _settings()), _client(second, budget, _settings())
    _ask(a), _ask(a), _ask(b)
    assert budget.spent_usd == pytest.approx(3 * CALL)
    assert budget.spent_usd == pytest.approx(a.total_cost_usd + b.total_cost_usd)


def test_reaching_the_total_blocks_every_session_and_a_new_one() -> None:
    budget = SharedBudget(1.5 * CALL)  # the second call crosses it
    first, second = _calls(1), _calls(1)
    a, b = _client(first, budget, _settings()), _client(second, budget, _settings())
    _ask(a), _ask(b)
    assert budget.exhausted
    fresh = _calls(1)  # a refresh: a new client, its own session cap untouched
    for client in (a, b, _client(fresh, budget, _settings())):
        with pytest.raises(SharedBudgetExceededError, match="max_total_cost_usd"):
            _ask(client)
    assert len(first.requests) == len(second.requests) == 1 and fresh.requests == []


def test_session_cap_still_stops_a_session_before_the_total() -> None:
    budget = SharedBudget(5.0)
    stub = _calls(2)
    client = _client(stub, budget, _settings(session_cap=CALL / 2))
    _ask(client)
    with pytest.raises(BudgetExceededError, match="llm.max_cost_usd") as raised:
        _ask(client)
    assert not isinstance(raised.value, SharedBudgetExceededError)
    assert not budget.exhausted and len(stub.requests) == 1


def test_client_without_a_shared_budget_is_unchanged() -> None:
    client = _client(_calls(1), None, _settings())
    _ask(client)
    assert client.total_cost_usd == pytest.approx(CALL)


def test_pipeline_reply_for_the_total_does_not_suggest_a_refresh() -> None:
    settings = _settings(total=3.7)  # not the config default: the reply reads the setting
    budget = SharedBudget(0.0)  # already spent by other sessions
    stub = _calls(0)
    client = _client(stub, budget, settings)
    pipeline = Pipeline(settings, REGISTRY, SpyRetriever(settings), client)
    answer = pipeline.ask("כמה טווח יש ל-MG S6?", [])
    assert answer.refusal is RefusalReason.BUDGET_EXCEEDED
    assert {"budget_exceeded", "server_budget_exceeded"} <= set(answer.flags)
    assert (
        answer.text.startswith("הגעתי למגבלת העלות הכוללת")
        and "$3.7" in answer.text
        and "$5" not in answer.text
    )
    assert "רענ" not in answer.text and stub.requests == [] and answer.llm_calls == 0


def test_session_cap_reply_is_unchanged() -> None:
    settings = _settings(session_cap=0.0)
    client = _client(_calls(0), SharedBudget(5.0), settings)
    answer = Pipeline(settings, REGISTRY, SpyRetriever(settings), client).ask("שאלה", [])
    assert answer.refusal is RefusalReason.BUDGET_EXCEEDED
    assert "server_budget_exceeded" not in answer.flags
    assert answer.text.startswith("הגעתי למגבלת העלות שהוגדרה לשיחה הזאת")


# --- threads: Streamlit runs each browser session on its own thread ---------------------
def test_concurrent_charges_are_all_counted() -> None:
    budget = SharedBudget(1_000.0)
    run_together(lambda _: [budget.add(0.001) for _ in range(2_000)])
    assert budget.spent_usd == pytest.approx(4.0)


class _InFlight(StubSDK):
    """Holds every request at a barrier, so both sessions' calls are in flight together."""

    def __init__(self, barrier: threading.Barrier, *replies: Any) -> None:
        super().__init__(*replies)
        self._barrier = barrier

    def create(self, **kwargs: Any) -> Any:
        self._barrier.wait(timeout=10)
        return super().create(**kwargs)


def test_in_flight_overspend_is_at_most_one_call_per_session() -> None:
    """Both sessions pass the check while the total is just under the cap; both calls
    finish. The documented bound: one call per session active at that moment."""
    budget = SharedBudget(CALL / 2)
    in_flight = threading.Barrier(2)
    stubs = [_InFlight(in_flight, _completion(VALID, prompt=PROMPT, out=OUT)) for _ in "ab"]
    clients = [_client(stub, budget, _settings()) for stub in stubs]
    run_together(lambda index: _ask(clients[index]))
    assert budget.spent_usd == pytest.approx(2 * CALL)  # cap passed by in-flight calls only
    assert budget.spent_usd <= budget.max_cost_usd + 2 * CALL
    for client in clients:
        with pytest.raises(SharedBudgetExceededError):
            _ask(client)
