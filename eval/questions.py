"""Typed loader for the eval question set.

Why a schema for a YAML file: the question set is the specification of "good"
for the whole project, so a typo in a car id or a malformed expectation must
fail loudly here and not silently turn into a question that always passes.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

QUESTIONS_PATH = Path(__file__).with_name("questions.yaml")


class Category(StrEnum):
    SINGLE_FACT = "single_fact"
    COMPARISON = "comparison"
    RECOMMENDATION = "recommendation"
    RANKING = "ranking"
    FOLLOW_UP = "follow_up"
    TRAP = "trap"


class Behavior(StrEnum):
    ANSWER = "answer"  # a grounded answer from the articles (may say a detail is missing)
    REFUSAL = "refusal"  # the relevance gate answers with the fixed template, no generation call
    OUT_OF_SCOPE = "out_of_scope"  # chitchat or off-topic: no retrieval at all


class Source(BaseModel):
    """A chunk that retrieval must return: the car and a substring of its section name."""

    model_config = ConfigDict(extra="forbid")

    car: str
    section: str


class Expect(BaseModel):
    model_config = ConfigDict(extra="forbid")

    behavior: Behavior
    # Retrieval eval (no LLM): every `sources` entry must appear among the retrieved
    # chunks, and at least one `sources_any` entry must.
    sources: list[Source] = Field(default_factory=list)
    sources_any: list[Source] = Field(default_factory=list)
    # Answer eval: every group must match; any alternative inside a group is enough.
    must_include: list[list[str]] = Field(default_factory=list)
    must_not_include: list[str] = Field(default_factory=list)
    must_not_match: list[str] = Field(default_factory=list)  # regular expressions
    # Preference inference, checked on the session after the last turn.
    preferences: dict[str, Any] | None = None


class Question(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    category: Category
    turns: list[str] = Field(min_length=1)  # user messages; the last answer is graded
    expect: Expect
    why: str  # what this question is designed to catch

    @model_validator(mode="after")
    def _shape_matches_behavior(self) -> Question:
        no_retrieval = self.expect.behavior is not Behavior.ANSWER
        if no_retrieval and (self.expect.sources or self.expect.sources_any):
            raise ValueError(f"{self.id}: refusals and off-topic replies expect no sources")
        if not no_retrieval and not (self.expect.sources or self.expect.sources_any):
            raise ValueError(f"{self.id}: an answer question must name its expected sources")
        return self


class QuestionSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int
    # Named phrase groups reused through YAML anchors (for example the "not mentioned" wording).
    shared: dict[str, list[str]] = Field(default_factory=dict)
    questions: list[Question]

    @model_validator(mode="after")
    def _unique_ids(self) -> QuestionSet:
        ids = [question.id for question in self.questions]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate question ids")
        return self


def load_questions(path: Path = QUESTIONS_PATH) -> QuestionSet:
    raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    return QuestionSet.model_validate(raw)
