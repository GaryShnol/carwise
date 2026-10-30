"""Typed access to config/settings.yaml.

Why a validated model and not a plain dict: a typo in a threshold or a model
name should fail at startup with a clear message, not three calls into a run.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict

from carwise.registry import BodyType, Powertrain

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "settings.yaml"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProfileConfig(_Strict):
    base_url: str | None
    understand_model: str
    generate_model: str


class LLMConfig(_Strict):
    temperature: float | None
    reasoning_effort: Literal["none", "minimal", "low", "medium", "high"] | None
    seed: int | None
    timeout_s: int
    retries: int
    history_window: int
    max_cost_usd: float


class Price(_Strict):
    input: float
    cached_input: float
    output: float


class EmbeddingsConfig(_Strict):
    provider: Literal["sentence_transformers", "fake"]
    model: str
    revision: str | None
    query_prefix: str
    passage_prefix: str
    device: str
    batch_size: int


class ChunkingConfig(_Strict):
    min_chars: int
    max_chars: int


class RetrievalConfig(_Strict):
    top_k: int
    per_car_cap: int
    cross_car_top_k: int
    cross_car_per_car_cap: int
    relevance_threshold: float


class GuardrailsConfig(_Strict):
    outside_brands: list[str]
    max_suggestions: int
    body_type_words: dict[BodyType, list[str]]
    powertrain_words: dict[Powertrain, list[str]]


class InputConfig(_Strict):
    max_message_chars: int


class FetchConfig(_Strict):
    user_agent: str
    delay_s: float
    timeout_s: int
    retries: int


class PathsConfig(_Strict):
    raw_dir: str
    index_dir: str
    log_dir: str


class Settings(_Strict):
    default_profile: str
    profiles: dict[str, ProfileConfig]
    llm: LLMConfig
    prices: dict[str, Price]
    embeddings: EmbeddingsConfig
    chunking: ChunkingConfig
    retrieval: RetrievalConfig
    input: InputConfig
    guardrails: GuardrailsConfig
    fetch: FetchConfig
    paths: PathsConfig

    def profile(self, name: str | None = None) -> ProfileConfig:
        """Resolve a profile: explicit name, then CARWISE_PROFILE, then the default."""
        chosen = name or os.environ.get("CARWISE_PROFILE") or self.default_profile
        if chosen not in self.profiles:
            known = ", ".join(sorted(self.profiles))
            raise ValueError(f"Unknown profile '{chosen}'. Known profiles: {known}.")
        return self.profiles[chosen]


def load_settings(path: Path | None = None) -> Settings:
    """Read and validate the settings file (CARWISE_CONFIG overrides the path)."""
    config_path = path or Path(os.environ.get("CARWISE_CONFIG", DEFAULT_CONFIG_PATH))
    raw: Any = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    return Settings.model_validate(raw)
