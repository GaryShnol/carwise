"""The single orchestrator of a conversation turn (CLAUDE.md section 3.2).

Fixed order: validate input, understand (LLM call 1), registry gate, retrieve,
similarity gate, generate (LLM call 2), check citations. Every refusal happens
before the generation call and is filled in by code, so the cheapest and most
reliable path is also the one taken when the corpus cannot answer. CLI, UI and
the eval runner all call `Pipeline.ask`; none of them holds logic of its own.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from carwise import guardrails
from carwise.config import Settings
from carwise.llm.base import (
    LLMClient,
    LLMError,
    LLMOutputError,
    LLMResult,
    LLMUnavailableError,
    Message,
    T,
    Usage,
)
from carwise.prompts import GENERATE_SYSTEM, generation_input, understand_system
from carwise.registry import Registry
from carwise.retrieval.retriever import ChunkRetriever
from carwise.schemas import (
    Answer,
    Citation,
    Generation,
    Intent,
    RefusalReason,
    RetrievedChunk,
    Understanding,
)
from carwise.telemetry import TurnLogger

NO_RETRIEVAL_INTENTS = (Intent.CHITCHAT, Intent.OUT_OF_SCOPE)


@dataclass
class _Turn:
    """Accumulates what one turn spent, across however many steps it reached."""

    usage: Usage = field(default_factory=Usage)
    cost_usd: float = 0.0
    llm_calls: int = 0
    latency_ms: dict[str, float] = field(default_factory=dict)
    flags: list[str] = field(default_factory=list)

    def charge(self, result: LLMResult[T]) -> T:
        self.usage += result.usage
        self.cost_usd += result.cost_usd
        self.llm_calls += result.attempts
        if result.attempts > 1:
            self.flags.append(f"{type(result.parsed).__name__.lower()}_retried")
        return result.parsed

    def charge_failure(self, error: LLMError) -> None:
        self.usage += error.usage
        self.cost_usd += error.cost_usd
        self.llm_calls += error.attempts


@dataclass
class _Plan:
    """What the understanding step decided, after code checked it against the registry."""

    intent: Intent | None = None
    cars: list[str] = field(default_factory=list)
    not_covered: list[str] = field(default_factory=list)
    question: str = ""


class Pipeline:
    def __init__(
        self,
        settings: Settings,
        registry: Registry,
        retriever: ChunkRetriever,
        llm: LLMClient,
        *,
        profile: str | None = None,
        logger: TurnLogger | None = None,
    ) -> None:
        self._settings = settings
        self._registry = registry
        self._retriever = retriever
        self._llm = llm
        self._models = settings.profile(profile)
        self._logger = logger
        self._understand_system = understand_system(registry)

    def greeting(self) -> str:
        """First message of a conversation: says the knowledge is limited to eight cars."""
        return guardrails.greeting(self._registry)

    def ask(self, message: str, history: list[Message]) -> Answer:
        started = time.perf_counter()
        turn = _Turn()
        answer = self._ask(message.strip(), history, turn)
        latency = {**turn.latency_ms, "total": (time.perf_counter() - started) * 1000}
        answer = answer.model_copy(update={"latency_ms": latency})
        if self._logger:
            self._logger.log(answer, message_chars=len(message))
        return answer

    # --- steps --------------------------------------------------------------------------
    def _ask(self, message: str, history: list[Message], turn: _Turn) -> Answer:
        limit = self._settings.input.max_message_chars
        if not message:
            return self._reply(turn, guardrails.EMPTY_REPLY, RefusalReason.EMPTY)
        if len(message) > limit:
            return self._reply(turn, guardrails.too_long_reply(limit), RefusalReason.TOO_LONG)

        try:
            plan = self._understand(message, history, turn)
        except LLMUnavailableError as error:
            turn.charge_failure(error)
            turn.flags.append("understand_unavailable")
            return self._reply(turn, guardrails.LLM_ERROR_REPLY, RefusalReason.LLM_ERROR)

        # Registry gate first: only cars outside the corpus were named. Known and
        # unknown together go on, and the answer says what is not covered.
        if plan.not_covered and not plan.cars:
            text = guardrails.unknown_car_reply(plan.not_covered, self._registry)
            return self._reply(turn, text, RefusalReason.UNKNOWN_CAR, plan)
        if plan.intent in NO_RETRIEVAL_INTENTS and not plan.cars:
            text = guardrails.out_of_scope_reply(self._registry)
            return self._reply(turn, text, RefusalReason.OUT_OF_SCOPE, plan)

        started = time.perf_counter()
        hits = self._retrieve(plan)
        turn.latency_ms["retrieve"] = (time.perf_counter() - started) * 1000
        threshold = self._settings.retrieval.relevance_threshold
        if not hits or max(hit.score for hit in hits) < threshold:
            text = guardrails.low_relevance_reply(self._registry)
            return self._reply(turn, text, RefusalReason.LOW_RELEVANCE, plan, hits)

        try:
            generation = self._generate(plan, hits, turn)
        except (LLMOutputError, LLMUnavailableError) as error:
            turn.charge_failure(error)
            turn.flags.append(f"generate_{type(error).__name__}")
            text = guardrails.LLM_ERROR_REPLY
            return self._reply(turn, text, RefusalReason.LLM_ERROR, plan, hits)
        return self._grounded(turn, plan, hits, generation)

    def _understand(self, message: str, history: list[Message], turn: _Turn) -> _Plan:
        window = history[-self._settings.llm.history_window :] if history else []
        messages: list[Message] = [*window, {"role": "user", "content": message}]
        started = time.perf_counter()
        try:
            result = self._llm.complete_json(
                self._understand_system,
                messages,
                Understanding,
                model=self._models.understand_model,
            )
            understanding = turn.charge(result)
        except LLMOutputError as error:
            # Fall back to the raw message: deterministic car matching still works,
            # and retrieval does not need a rewritten question to be useful.
            turn.charge_failure(error)
            turn.flags.append("understand_fallback")
            understanding = None
        finally:
            turn.latency_ms["understand"] = (time.perf_counter() - started) * 1000
        return self._plan(message, understanding, turn)

    def _plan(self, message: str, understanding: Understanding | None, turn: _Turn) -> _Plan:
        """Trust the model's car ids only when the registry knows them; add name matches."""
        known = {car.id for car in self._registry.cars}
        question = understanding.standalone_question.strip() if understanding else ""
        question = question or message
        llm_cars = understanding.cars if understanding else []
        invented = [car for car in llm_cars if car not in known]
        if invented:
            turn.flags.append("understand_unknown_ids")
        matched = guardrails.cars_in_text(f"{message}\n{question}", self._registry)
        cars = list(dict.fromkeys([*(c for c in llm_cars if c in known), *matched]))
        brands = guardrails.outside_brands_in_text(
            message, self._settings.guardrails.outside_brands
        )
        unrecognized = understanding.unrecognized_cars if understanding else []
        if understanding:
            intent = understanding.intent
        else:
            intent = Intent.COMPARE if len(cars) > 1 else Intent.FACT
        return _Plan(intent, cars, guardrails.not_covered(unrecognized, brands), question)

    def _retrieve(self, plan: _Plan) -> list[RetrievedChunk]:
        """One car: filter on it. Several: each car separately. None: all cars, capped."""
        config = self._settings.retrieval
        if len(plan.cars) > 1:
            return self._retriever.search_per_car(plan.question, plan.cars, config.per_car_cap)
        if plan.cars:
            return self._retriever.search(plan.question, plan.cars, config.top_k)
        return self._retriever.search_all(
            plan.question, config.cross_car_top_k, config.cross_car_per_car_cap
        )

    def _generate(self, plan: _Plan, hits: list[RetrievedChunk], turn: _Turn) -> Generation:
        content = generation_input(plan.question, hits, plan.not_covered)
        started = time.perf_counter()
        try:
            result = self._llm.complete_json(
                GENERATE_SYSTEM,
                [{"role": "user", "content": content}],
                Generation,
                model=self._models.generate_model,
            )
            return turn.charge(result)
        finally:
            turn.latency_ms["generate"] = (time.perf_counter() - started) * 1000

    def _grounded(
        self, turn: _Turn, plan: _Plan, hits: list[RetrievedChunk], generation: Generation
    ) -> Answer:
        """Citations are checked in code: an id the model did not receive is dropped."""
        by_id = {hit.chunk.chunk_id: hit.chunk for hit in hits}
        cited = list(dict.fromkeys(generation.used_chunk_ids))
        dropped = [chunk_id for chunk_id in cited if chunk_id not in by_id]
        if dropped:
            turn.flags.append("dropped_unretrieved_ids")
        sources = [
            Citation(
                chunk_id=chunk.chunk_id,
                car=chunk.car,
                car_name=chunk.car_name,
                section=chunk.section,
                source_url=chunk.source_url,
            )
            for chunk in (by_id[chunk_id] for chunk_id in cited if chunk_id in by_id)
        ]
        return self._reply(turn, generation.answer, None, plan, hits, sources, dropped)

    # --- helpers ------------------------------------------------------------------------
    @staticmethod
    def _reply(
        turn: _Turn,
        text: str,
        refusal: RefusalReason | None,
        plan: _Plan | None = None,
        hits: list[RetrievedChunk] | None = None,
        sources: list[Citation] | None = None,
        dropped: list[str] | None = None,
    ) -> Answer:
        plan = plan or _Plan()
        return Answer(
            text=text,
            sources=sources or [],
            refusal=refusal,
            intent=plan.intent,
            cars=plan.cars,
            not_covered=plan.not_covered,
            standalone_question=plan.question,
            retrieved=hits or [],
            dropped_chunk_ids=dropped or [],
            flags=list(turn.flags),
            llm_calls=turn.llm_calls,
            usage=turn.usage,
            cost_usd=turn.cost_usd,
            latency_ms=dict(turn.latency_ms),
        )
