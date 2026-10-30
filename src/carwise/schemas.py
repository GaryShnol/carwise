"""Pydantic models shared across ingestion, retrieval, the pipeline and the eval.

Why one module: these shapes are the contracts between steps, so keeping them
together makes a change to a contract visible in one place.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from carwise.guardrails import answer_text_problem
from carwise.llm.base import Usage


class Chunk(BaseModel):
    """One retrievable piece of an article.

    `text` is what the generator sees and cites; `embed_text` adds the car and
    section in front, because eight reviews of similar cars use the same words
    ("engine", "price", "range"), and a chunk that names its car retrieves
    better for per-car and cross-car questions.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    chunk_id: str = Field(pattern=r"^[a-z0-9_]+:\d{3,}$")  # "<car id>:<position>", e.g. "mg_s6:007"
    car: str
    car_name: str
    section: str = Field(min_length=1)
    source_url: str
    published: date | None
    text: str = Field(min_length=1)
    embed_text: str = Field(min_length=1)


class RetrievedChunk(BaseModel):
    """A chunk with its cosine similarity to the query (1 is identical, 0 unrelated)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    chunk: Chunk
    score: float = Field(ge=-1.0, le=1.0)


# --- LLM call 1: understanding --------------------------------------------------------
class Intent(StrEnum):
    FACT = "fact"
    COMPARE = "compare"
    RECOMMEND = "recommend"  # also ranking and superlative questions across all cars
    CHITCHAT = "chitchat"
    OUT_OF_SCOPE = "out_of_scope"


class PreferenceField(StrEnum):
    BUDGET = "budget"
    POWERTRAIN = "powertrain"
    PRIMARY_USE = "primary_use"
    PASSENGERS = "passengers"
    PRIORITIES = "priorities"
    DISLIKES = "dislikes"


class PreferenceUpdate(BaseModel):
    """A preference stated in the latest message, as the model reported it.

    `field` parses as a plain string so code can validate it (carwise.preferences):
    one unknown field name drops that update instead of failing the whole call.
    The JSON schema still lists the allowed names, so strict mode keeps OpenAI
    models on them; the code check covers providers without strict mode. (A
    plain string with no enum let the model invent names: seen in the CW-203 run.)
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    field: str = Field(json_schema_extra={"enum": [item.value for item in PreferenceField]})
    value: str


class Preference(BaseModel):
    """One remembered preference and the user message it came from (for /prefs)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    value: str
    source: str


class Preferences(BaseModel):
    """The user's preferences in this conversation only; never stored on disk.

    One value per field: a later statement on the same field replaces the earlier
    one, which is how a user changes their mind ("actually, up to 250 thousand").
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    budget: Preference | None = None
    powertrain: Preference | None = None
    primary_use: Preference | None = None
    passengers: Preference | None = None
    priorities: Preference | None = None
    dislikes: Preference | None = None

    def items(self) -> list[tuple[PreferenceField, Preference]]:
        """The fields that are set, in a fixed order."""
        values = ((field, getattr(self, field.value)) for field in PreferenceField)
        return [(field, value) for field, value in values if value is not None]

    def field_names(self) -> list[str]:
        return [field.value for field, _ in self.items()]


class Understanding(BaseModel):
    """Output of the understand call: one call instead of a router, an extractor and a rewriter.

    Fields are all required and nothing has a default, because OpenAI strict mode
    demands it; empty lists stand for "none".
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    intent: Intent
    cars: list[str]  # canonical registry ids
    unrecognized_cars: list[str]  # raw names of specific cars that match no registry entry
    standalone_question: str  # the question rewritten to stand alone, in Hebrew
    preference_updates: list[PreferenceUpdate]


# --- LLM call 2: generation -------------------------------------------------------------
class Generation(BaseModel):
    """Output of the generate call. The validator turns a malformed answer text into a
    validation error, which the client's single corrective retry then fixes."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    answer: str
    used_chunk_ids: list[str]

    @field_validator("answer")
    @classmethod
    def _answer_is_clean_hebrew(cls, value: str) -> str:
        problem = answer_text_problem(value)
        if problem:
            raise ValueError(problem)
        return value.strip()


# --- pipeline result ----------------------------------------------------------------------
class RefusalReason(StrEnum):
    EMPTY = "empty"
    TOO_LONG = "too_long"
    UNKNOWN_CAR = "unknown_car"  # registry gate: only cars outside the corpus were named
    LOW_RELEVANCE = "low_relevance"  # similarity gate: best score below the threshold
    OUT_OF_SCOPE = "out_of_scope"  # chitchat or off-topic: no retrieval at all
    LLM_ERROR = "llm_error"  # provider unavailable or unusable output
    UNVERIFIED = "unverified"  # post-check failed on the answer and on its one regeneration


class CheckFindings(BaseModel):
    """What the post-check found wrong with one generated answer; empty means clean."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    cars: list[str]  # car names the retrieved chunks and the question cannot back

    @property
    def suspect(self) -> bool:
        return bool(self.cars)

    def problems(self) -> list[str]:
        """English sentences for the regenerate instruction."""
        if not self.cars:
            return []
        return [f"it names cars that the excerpts do not support: {', '.join(self.cars)}"]


class PostCheckOutcome(StrEnum):
    CLEAN = "clean"  # the first answer passed
    REGENERATED = "regenerated"  # the first failed, the one stricter retry passed
    FALLBACK = "fallback"  # both failed (or the retry errored): a code-built reply was shown


class PostCheck(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    outcome: PostCheckOutcome
    attempts: list[CheckFindings]  # one per generated answer, in order


class Citation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    chunk_id: str
    car: str
    car_name: str
    section: str
    source_url: str


class Answer(BaseModel):
    """Everything a caller (CLI, UI, eval) needs to show or grade one turn."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    text: str
    sources: list[Citation]
    refusal: RefusalReason | None
    intent: Intent | None
    cars: list[str]
    not_covered: list[str]  # car names the user asked about that the articles do not cover
    suggested_cars: list[str]  # registry ids a refusal offered instead (CW-201)
    standalone_question: str
    retrieved: list[RetrievedChunk]
    dropped_chunk_ids: list[str]  # cited by the model but not retrieved this turn
    post_check: PostCheck | None  # None when no answer was generated
    preferences: Preferences  # the profile after this turn; the caller keeps it (Session)
    updated_preferences: list[str]  # field names this turn set or changed
    flags: list[str]
    llm_calls: int
    usage: Usage
    cost_usd: float
    latency_ms: dict[str, float]  # per stage, plus "total"
