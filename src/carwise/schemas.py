"""Pydantic models shared across ingestion, retrieval, the pipeline and the eval.

Why one module: these shapes are the contracts between steps, so keeping them
together makes a change to a contract visible in one place.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field


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
