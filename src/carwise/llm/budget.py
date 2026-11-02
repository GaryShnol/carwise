"""A spend cap shared by every LLM client in one process (CW-605).

Why: the UI gives each browser session its own client, so llm.max_cost_usd bounds
one conversation, and a refresh opens a new one. This counter is the same object
for all of them, so the process as a whole stops at llm.max_total_cost_usd.

Over-spend is bounded, not zero: the check comes before a call and its cost is
added after it, so calls already in flight when the total is reached still finish.
The total can pass the cap by at most one call per session active at that moment
(one call is a request plus, at most, its one corrective retry). The bound is on
tracked cost: like the session cap, it counts the usage a response reports, and an
SDK transport retry of a failed request returns none, so it is not charged.
Holding the lock across the call would remove the over-spend, but would also
serialize every session's calls.
"""

from __future__ import annotations

import threading

from carwise.llm.base import SharedBudgetExceededError


class SharedBudget:
    """Thread-safe running total; Streamlit runs each browser session on its own thread."""

    def __init__(self, max_cost_usd: float) -> None:
        self.max_cost_usd = max_cost_usd
        self._spent_usd = 0.0
        self._lock = threading.Lock()

    @property
    def spent_usd(self) -> float:
        with self._lock:
            return self._spent_usd

    @property
    def exhausted(self) -> bool:
        with self._lock:
            return self._spent_usd >= self.max_cost_usd

    def check(self) -> None:
        """Raise before a call once the shared total is reached."""
        with self._lock:
            spent = self._spent_usd
        if spent >= self.max_cost_usd:
            raise SharedBudgetExceededError(
                f"Spent ${spent:.4f} of the ${self.max_cost_usd:.2f} shared budget "
                "(llm.max_total_cost_usd); stopping."
            )

    def add(self, cost_usd: float) -> None:
        with self._lock:
            self._spent_usd += cost_usd
