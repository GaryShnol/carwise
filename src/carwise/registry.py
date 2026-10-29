"""Typed access to config/cars.yaml, the car registry.

Why one validated registry: ingestion, the understand prompt, the relevance gate
and the post-check all need to agree on which cars exist and how they are
spelled. A duplicate alias would silently route a question to the wrong car,
so the loader rejects it at startup instead.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Any, Self
from urllib.parse import urlparse

import yaml
from pydantic import BaseModel, ConfigDict, model_validator

DEFAULT_REGISTRY_PATH = Path(__file__).resolve().parents[2] / "config" / "cars.yaml"


class BodyType(StrEnum):
    SUPERMINI = "supermini"
    HATCHBACK = "hatchback"
    SEDAN = "sedan"
    SUV = "suv"
    SUV_COUPE = "suv_coupe"


class Powertrain(StrEnum):
    PETROL = "petrol"
    MILD_HYBRID = "mild_hybrid"
    PLUG_IN_HYBRID = "plug_in_hybrid"
    ELECTRIC = "electric"


def url_slug(url: str) -> str:
    """The last path segment, which names the cache file in data/raw/."""
    return urlparse(url).path.rstrip("/").rsplit("/", 1)[-1]


def normalize_alias(alias: str) -> str:
    """Case-folded, whitespace-collapsed form used to compare aliases."""
    return " ".join(alias.casefold().split())


class Car(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    display_name: str
    aliases_he: list[str]
    aliases_latin: list[str]
    body_type: BodyType | None
    body_type_quote: str | None
    powertrain: Powertrain | None
    powertrain_quote: str | None
    url: str
    slug: str

    @property
    def aliases(self) -> list[str]:
        """Every spelling that refers to this car, display name first."""
        return [self.display_name, *self.aliases_he, *self.aliases_latin]

    @model_validator(mode="after")
    def _check(self) -> Self:
        if not self.id.isidentifier() or self.id != self.id.lower():
            raise ValueError(f"car id '{self.id}' must be lowercase snake_case")
        if not self.url.startswith("https://"):
            raise ValueError(f"{self.id}: url must be an https URL")
        if self.slug != url_slug(self.url):
            raise ValueError(f"{self.id}: slug '{self.slug}' does not match its URL")
        # A value without a quote would be unverifiable against the article.
        if (self.body_type is None) != (self.body_type_quote is None):
            raise ValueError(f"{self.id}: body_type and body_type_quote go together")
        if (self.powertrain is None) != (self.powertrain_quote is None):
            raise ValueError(f"{self.id}: powertrain and powertrain_quote go together")
        return self


class Registry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    cars: list[Car]

    @model_validator(mode="after")
    def _unique(self) -> Self:
        for field in ("id", "slug", "url"):
            values = [getattr(car, field) for car in self.cars]
            duplicates = sorted({value for value in values if values.count(value) > 1})
            if duplicates:
                raise ValueError(f"duplicate car {field}: {', '.join(duplicates)}")
        owner: dict[str, str] = {}
        for car in self.cars:
            for alias in {normalize_alias(alias) for alias in car.aliases}:
                if alias in owner:
                    raise ValueError(f"alias '{alias}' used by {owner[alias]} and {car.id}")
                owner[alias] = car.id
        return self

    def get(self, car_id: str) -> Car:
        for car in self.cars:
            if car.id == car_id:
                return car
        raise KeyError(f"unknown car id '{car_id}'")


def load_registry(path: Path | None = None) -> Registry:
    """Read and validate the car registry."""
    raw: Any = yaml.safe_load((path or DEFAULT_REGISTRY_PATH).read_text(encoding="utf-8"))
    return Registry.model_validate(raw)
