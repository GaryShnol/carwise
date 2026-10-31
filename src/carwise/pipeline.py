"""The single orchestrator of a conversation turn (CLAUDE.md section 3.2).

Fixed order: validate input, understand (LLM call 1), registry gate, retrieve,
similarity gate, generate (LLM call 2), post-check (one stricter regeneration,
then a safe fallback), check citations. Every refusal happens
before the generation call and is filled in by code, so the cheapest and most
reliable path is also the one taken when the corpus cannot answer; it still
helps, by suggesting the closest of the eight cars. CLI, UI and
the eval runner all call `Pipeline.ask`; none of them holds logic of its own.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from carwise import guardrails
from carwise.config import Settings
from carwise.guardrails import escape_text
from carwise.llm.base import (
    BudgetExceededError,
    LLMClient,
    LLMError,
    LLMOutputError,
    LLMResult,
    LLMUnavailableError,
    Message,
    T,
    Usage,
)
from carwise.preferences import Session, prompt_block
from carwise.preferences import merge as merge_preferences
from carwise.prompts import (
    GENERATE_SYSTEM,
    generate_system,
    generation_input,
    regenerate_instruction,
    understand_system,
)
from carwise.registry import Registry
from carwise.retrieval.retriever import ChunkRetriever
from carwise.schemas import (
    Answer,
    CheckFindings,
    Citation,
    Generation,
    Intent,
    LLMCall,
    PostCheck,
    PostCheckOutcome,
    Preferences,
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
    # The profile the turn started with, updated once the understand step is checked;
    # every reply, refusals included, hands it back so nothing said is lost.
    preferences: Preferences = field(default_factory=Preferences)
    updated_preferences: list[str] = field(default_factory=list)
    rejected_preferences: list[str] = field(default_factory=list)

    calls: list[LLMCall] = field(default_factory=list)

    def charge(self, result: LLMResult[T], stage: str) -> T:
        self.usage += result.usage
        self.cost_usd += result.cost_usd
        self.llm_calls += result.attempts
        self.calls.append(
            _call(
                stage,
                result.model,
                result.attempts,
                result.latency_ms,
                result.usage,
                result.cost_usd,
            )
        )
        if result.attempts > 1:
            self.flags.append(f"{type(result.parsed).__name__.lower()}_retried")
        return result.parsed

    def charge_failure(self, error: LLMError, stage: str) -> None:
        self.usage += error.usage
        self.cost_usd += error.cost_usd
        self.llm_calls += error.attempts
        self.calls.append(_call(stage, None, error.attempts, None, error.usage, error.cost_usd))


def _call(
    stage: str,
    model: str | None,
    attempts: int,
    latency: float | None,
    usage: Usage,
    cost: float,
) -> LLMCall:
    """A successful call has a model and a latency; a failed one has neither."""
    return LLMCall(
        stage=stage,
        model=model,
        ok=model is not None,
        attempts=attempts,
        latency_ms=latency,
        input_tokens=usage.input_tokens,
        cached_tokens=usage.cached_tokens,
        output_tokens=usage.output_tokens,
        cost_usd=cost,
    )


@dataclass
class _Plan:
    """What the understanding step decided, after code checked it against the registry."""

    intent: Intent | None = None
    cars: list[str] = field(default_factory=list)
    not_covered: list[str] = field(default_factory=list)
    question: str = ""
    message: str = ""  # the user's own words, which may state numbers (CW-206)


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
        generate_version: str | None = None,
    ) -> None:
        self._settings = settings
        # The configured generate prompt unless the eval asks for another version.
        self._generate_system = (
            generate_system(generate_version) if generate_version else GENERATE_SYSTEM
        )
        self._registry = registry
        self._retriever = retriever
        self._llm = llm
        self._models = settings.profile(profile)
        self._logger = logger
        self._understand_system = understand_system(registry)

    def greeting(self) -> str:
        """First message of a conversation: says the knowledge is limited to eight cars."""
        return guardrails.greeting(self._registry)

    def answer(self, message: str, session: Session) -> Answer:
        """One turn of a conversation: ask with the session's memory, then update it."""
        answer = self.ask(message, session.history, session.preferences)
        session.record(message, answer)
        return answer

    def ask(
        self, message: str, history: list[Message], preferences: Preferences | None = None
    ) -> Answer:
        """Stateless turn: the caller passes the memory in and keeps what comes back."""
        started = time.perf_counter()
        turn = _Turn(preferences=preferences or Preferences())
        try:
            answer = self._ask(message.strip(), history, turn)
        except BudgetExceededError:
            # The cap is per client (one chat session or one eval run): the refused
            # call never reached the provider (nothing to charge), and every later
            # call would be refused too, so the caller ends the session.
            turn.flags.append("budget_exceeded")
            text = guardrails.budget_reply(self._settings.llm.max_cost_usd)
            answer = self._reply(turn, text, RefusalReason.BUDGET_EXCEEDED)
        latency = {**turn.latency_ms, "total": (time.perf_counter() - started) * 1000}
        answer = answer.model_copy(update={"latency_ms": latency})
        if self._logger:
            self._logger.log(answer, message_chars=len(message), history_messages=len(history))
        return answer

    # --- steps --------------------------------------------------------------------------
    def _ask(self, message: str, history: list[Message], turn: _Turn) -> Answer:
        limit = self._settings.input.max_message_chars
        if not message:
            return self._reply(turn, guardrails.EMPTY_REPLY, RefusalReason.EMPTY)
        if len(message) > limit:
            return self._reply(turn, guardrails.too_long_reply(limit), RefusalReason.TOO_LONG)

        history = self._window(message, history, turn)
        try:
            plan = self._understand(message, history, turn)
        except LLMUnavailableError as error:
            turn.charge_failure(error, "understand")
            turn.flags.append("understand_unavailable")
            return self._reply(turn, guardrails.LLM_ERROR_REPLY, RefusalReason.LLM_ERROR)

        # Registry gate first: only cars outside the corpus were named. Known and
        # unknown together go on, and the answer says what is not covered.
        if plan.not_covered and not plan.cars:
            suggested = self._suggest(message, history, [])
            text = guardrails.unknown_car_reply(plan.not_covered, self._registry, suggested)
            return self._reply(turn, text, RefusalReason.UNKNOWN_CAR, plan, suggested=suggested)
        if plan.intent in NO_RETRIEVAL_INTENTS and not plan.cars:
            text = guardrails.out_of_scope_reply(self._registry)
            return self._reply(turn, text, RefusalReason.OUT_OF_SCOPE, plan)

        started = time.perf_counter()
        hits = self._retrieve(plan)
        turn.latency_ms["retrieve"] = (time.perf_counter() - started) * 1000
        threshold = self._settings.retrieval.relevance_threshold
        if not hits or max(hit.score for hit in hits) < threshold:
            suggested = self._suggest(message, history, hits)
            text = guardrails.low_relevance_reply(self._registry, suggested)
            return self._reply(
                turn, text, RefusalReason.LOW_RELEVANCE, plan, hits, suggested=suggested
            )

        try:
            generation = self._generate(plan, hits, turn)
        except (LLMOutputError, LLMUnavailableError) as error:
            turn.charge_failure(error, "generate")
            turn.flags.append(f"generate_{type(error).__name__}")
            text = guardrails.LLM_ERROR_REPLY
            return self._reply(turn, text, RefusalReason.LLM_ERROR, plan, hits)
        return self._checked(turn, plan, hits, generation)

    def _checked(
        self, turn: _Turn, plan: _Plan, hits: list[RetrievedChunk], generation: Generation
    ) -> Answer:
        """Post-check; a suspect answer gets one stricter retry, then a code-built fallback.

        Why at most one retry: each is a full generation call, and a model that
        failed twice on the same excerpts is unlikely to pass a third time, so the
        bounded path (one extra call, then a safe reply) keeps cost and latency fixed.
        """
        findings = self._post_check(plan, hits, generation, turn)
        if not findings.suspect:
            check = PostCheck(outcome=PostCheckOutcome.CLEAN, attempts=[findings])
            return self._grounded(turn, plan, hits, generation, check)

        turn.flags.append("postcheck_suspect")
        turn.flags += findings.kinds()
        attempts = [findings]
        try:
            retry = self._generate(plan, hits, turn, retry_of=(generation, findings))
        except (LLMOutputError, LLMUnavailableError) as error:
            turn.charge_failure(error, "regenerate")
            turn.flags.append(f"regenerate_{type(error).__name__}")
        else:
            retry_findings = self._post_check(plan, hits, retry, turn)
            attempts.append(retry_findings)
            turn.flags += [kind for kind in retry_findings.kinds() if kind not in turn.flags]
            if not retry_findings.suspect:
                turn.flags.append("postcheck_regenerated")
                check = PostCheck(outcome=PostCheckOutcome.REGENERATED, attempts=attempts)
                return self._grounded(turn, plan, hits, retry, check)

        turn.flags.append("postcheck_fallback")
        check = PostCheck(outcome=PostCheckOutcome.FALLBACK, attempts=attempts)
        limit = self._settings.guardrails.max_suggestions
        text = guardrails.unverified_reply(
            self._registry, hits, limit, self._settings.display.max_section_chars
        )
        return self._reply(turn, text, RefusalReason.UNVERIFIED, plan, hits, post_check=check)

    def _post_check(
        self, plan: _Plan, hits: list[RetrievedChunk], generation: Generation, turn: _Turn
    ) -> CheckFindings:
        config = self._settings.guardrails
        cars = guardrails.unsupported_cars(
            generation.answer, hits, plan.not_covered, self._registry, config.outside_brands
        )
        # The user's words may state numbers: the question as written and as rewritten,
        # and the preference values the generate call received.
        user_texts = [plan.message, plan.question, *(p.value for _, p in turn.preferences.items())]
        numbers = guardrails.unsupported_numbers(
            generation.answer, hits, user_texts, self._registry, config.numbers_always_allowed
        )
        return CheckFindings(cars=cars, numbers=numbers)

    def _window(self, message: str, history: list[Message], turn: _Turn) -> list[Message]:
        """The history the turn may use, bounded like the message itself (CW-205).

        `ask` is stateless, so a caller may pass any history: each user message in
        the window is held to max_message_chars, like the current one, and the
        whole turn input (message plus window) to max_turn_input_chars, dropping the
        oldest messages first. A long history never refuses the turn; it is trimmed.
        """
        limits = self._settings.input
        window = history[-self._settings.llm.history_window :] if history else []
        bounded: list[Message] = []
        for item in window:
            content = item["content"]
            if item["role"] == "user" and len(content) > limits.max_message_chars:
                content = content[: limits.max_message_chars]
                turn.flags.append("history_message_truncated")
            bounded.append({"role": item["role"], "content": content})
        budget = limits.max_turn_input_chars - len(message)
        while bounded and sum(len(item["content"]) for item in bounded) > budget:
            bounded.pop(0)
            if "history_trimmed" not in turn.flags:
                turn.flags.append("history_trimmed")
        return bounded

    def _understand(self, message: str, history: list[Message], turn: _Turn) -> _Plan:
        # History and message are escaped like excerpts: a message cannot fake a turn
        # boundary or a special token (CW-205). Roles are set by code, never by text.
        messages: list[Message] = [
            *({"role": item["role"], "content": escape_text(item["content"])} for item in history),
            {"role": "user", "content": escape_text(message)},
        ]
        started = time.perf_counter()
        try:
            result = self._llm.complete_json(
                self._understand_system,
                messages,
                Understanding,
                model=self._models.understand_model,
            )
            understanding = turn.charge(result, "understand")
        except LLMOutputError as error:
            # Fall back to the raw message: deterministic car matching still works,
            # and retrieval does not need a rewritten question to be useful.
            turn.charge_failure(error, "understand")
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
            merged = merge_preferences(
                turn.preferences,
                understanding.preference_updates,
                message,
                self._settings.preferences.max_value_chars,
            )
            turn.preferences, turn.updated_preferences = merged.preferences, merged.updated
            turn.rejected_preferences = merged.rejected
            turn.flags += merged.flags
        else:
            intent = Intent.COMPARE if len(cars) > 1 else Intent.FACT
        not_covered = guardrails.not_covered(unrecognized, brands)
        return _Plan(intent, cars, not_covered, question, message)

    def _retrieve(self, plan: _Plan) -> list[RetrievedChunk]:
        """One car: filter on it. Several: each car separately. None: all cars, capped.

        A recommendation (or ranking) always searches all cars (CW-306): the cars the
        plan names, often carried over from earlier answers, are only a hint, so a
        car the user never mentioned can still be the best match.
        """
        config = self._settings.retrieval
        if plan.intent is Intent.RECOMMEND:
            hits = self._retriever.search_all(
                plan.question, config.cross_car_top_k, config.cross_car_per_car_cap
            )
            # The hint: each named car's spec box joins the candidates, never filters them.
            return self._with_spec_boxes(plan, hits) if plan.cars else hits
        if len(plan.cars) > 1:
            hits = self._retriever.search_per_car(plan.question, plan.cars, config.per_car_cap)
        elif plan.cars:
            hits = self._retriever.search(plan.question, plan.cars, config.top_k)
        else:
            return self._retriever.search_all(
                plan.question, config.cross_car_top_k, config.cross_car_per_car_cap
            )
        if config.force_spec_box and plan.intent is Intent.COMPARE:
            # Option B: comparisons need each car's price and figures, which sit in its
            # spec box, whatever its similarity to the wording of the question.
            hits = self._with_spec_boxes(plan, hits)
        return hits

    def _with_spec_boxes(self, plan: _Plan, hits: list[RetrievedChunk]) -> list[RetrievedChunk]:
        """The hits, then each named car's spec box that is not among them yet."""
        have = {hit.chunk.chunk_id for hit in hits}
        extra = self._retriever.spec_boxes(plan.question, plan.cars)
        return hits + [hit for hit in extra if hit.chunk.chunk_id not in have]

    def _suggest(
        self, message: str, history: list[Message], hits: list[RetrievedChunk]
    ) -> list[str]:
        """Closest cars for a refusal: the user's own hint words first, then chunk scores.

        Hints are read only from what the user wrote (this message and the user turns
        in the history window), never from the rewritten question: the model may add
        "electric" or "SUV" there from its own knowledge of the unknown car.
        """
        config = self._settings.guardrails
        user_text = [turn["content"] for turn in history if turn["role"] == "user"]
        hinted = guardrails.hinted_cars(
            "\n".join([*user_text, message]),
            self._registry,
            config.body_type_words,
            config.powertrain_words,
            config.max_suggestions,
        )
        return hinted or guardrails.closest_by_score(hits, config.max_suggestions)

    def _generate(
        self,
        plan: _Plan,
        hits: list[RetrievedChunk],
        turn: _Turn,
        *,
        retry_of: tuple[Generation, CheckFindings] | None = None,
    ) -> Generation:
        """One generate call; on a retry the rejected answer and the reasons follow it."""
        # Preferences shape recommendations only; a fact question about one car
        # should not be steered by a budget stated three turns ago.
        wanted = prompt_block(turn.preferences) if plan.intent is Intent.RECOMMEND else ""
        content = generation_input(plan.question, hits, plan.not_covered, wanted)
        messages: list[Message] = [{"role": "user", "content": content}]
        if retry_of:
            rejected, findings = retry_of
            messages += [
                {"role": "assistant", "content": rejected.model_dump_json()},
                {"role": "user", "content": regenerate_instruction(findings.problems())},
            ]
        stage = "regenerate" if retry_of else "generate"
        started = time.perf_counter()
        try:
            result = self._llm.complete_json(
                self._generate_system, messages, Generation, model=self._models.generate_model
            )
            return turn.charge(result, stage)
        finally:
            turn.latency_ms[stage] = (time.perf_counter() - started) * 1000

    def _grounded(
        self,
        turn: _Turn,
        plan: _Plan,
        hits: list[RetrievedChunk],
        generation: Generation,
        check: PostCheck,
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
        return self._reply(
            turn, generation.answer, None, plan, hits, sources, dropped, post_check=check
        )

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
        *,
        suggested: list[str] | None = None,
        post_check: PostCheck | None = None,
    ) -> Answer:
        plan = plan or _Plan()
        return Answer(
            text=text,
            sources=sources or [],
            refusal=refusal,
            intent=plan.intent,
            cars=plan.cars,
            not_covered=plan.not_covered,
            suggested_cars=suggested or [],
            standalone_question=plan.question,
            retrieved=hits or [],
            dropped_chunk_ids=dropped or [],
            post_check=post_check,
            preferences=turn.preferences,
            updated_preferences=list(turn.updated_preferences),
            rejected_preferences=list(turn.rejected_preferences),
            flags=list(turn.flags),
            llm_calls=turn.llm_calls,
            calls=list(turn.calls),
            usage=turn.usage,
            cost_usd=turn.cost_usd,
            latency_ms=dict(turn.latency_ms),
        )
