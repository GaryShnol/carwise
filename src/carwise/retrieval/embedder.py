"""Text embeddings behind a two-method interface.

Why a protocol: CW-305 compares embedding models on the retrieval eval, and a
later deployment may use a hosted model (for example Bedrock); either must be
a config change plus at most one new class, with no change in the store or the
retriever. Why queries and passages are embedded by separate methods: e5-style
models are trained with different prefixes for the two, and mixing them up
silently costs retrieval quality.
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import TYPE_CHECKING, Protocol

from carwise.config import EmbeddingsConfig

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

Vector = list[float]


class Embedder(Protocol):
    @property
    def identity(self) -> dict[str, str | None]:
        """Everything that changes the vectors; part of the index fingerprint."""
        ...

    def embed_documents(self, texts: list[str]) -> list[Vector]: ...

    def embed_query(self, text: str) -> Vector: ...

    def warm_up(self) -> None:
        """Load whatever is slow to load, so the first user question does not pay for it."""
        ...


class SentenceTransformerEmbedder:
    """A local sentence-transformers model on CPU: no API key, no per-call cost.

    The model is loaded on first use, so `ingest` on an up-to-date index never
    pays the load time.
    """

    def __init__(self, config: EmbeddingsConfig) -> None:
        self._config = config
        self._model: SentenceTransformer | None = None

    @property
    def identity(self) -> dict[str, str | None]:
        return {
            "provider": "sentence_transformers",
            "model": self._config.model,
            "revision": self._config.revision,
            "query_prefix": self._config.query_prefix,
            "passage_prefix": self._config.passage_prefix,
        }

    def _load(self) -> SentenceTransformer:
        if self._model is None:
            from sentence_transformers import SentenceTransformer  # heavy import, only when used
            from transformers.utils import logging as transformers_logging

            transformers_logging.disable_progress_bar()  # type: ignore[no-untyped-call]  # quiet CLI
            config = self._config

            def load(local_only: bool) -> SentenceTransformer:
                return SentenceTransformer(
                    config.model,
                    revision=config.revision,
                    device=config.device,
                    local_files_only=local_only,
                )

            try:  # the pinned revision is usually cached: no network, works offline
                self._model = load(local_only=True)
            except OSError:  # first run: download once into the Hugging Face cache
                self._model = load(local_only=False)
        return self._model

    def warm_up(self) -> None:
        self._load()

    def _encode(self, texts: list[str]) -> list[Vector]:
        vectors = self._load().encode(
            texts,
            batch_size=self._config.batch_size,
            normalize_embeddings=True,  # cosine similarity becomes a dot product
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return [[float(value) for value in vector] for vector in vectors]

    def embed_documents(self, texts: list[str]) -> list[Vector]:
        return self._encode([self._config.passage_prefix + text for text in texts])

    def embed_query(self, text: str) -> Vector:
        return self._encode([self._config.query_prefix + text])[0]


class FakeEmbedder:
    """Deterministic hashed bag of words: texts sharing words score higher.

    For unit tests and offline CI: no download, no model, same vector on every
    machine. It knows nothing about meaning, so it never stands in for the eval.
    """

    _TOKEN = re.compile(r"\w+")

    def __init__(self, dimension: int = 256) -> None:
        self.dimension = dimension

    @property
    def identity(self) -> dict[str, str | None]:
        return {"provider": "fake", "dimension": str(self.dimension)}

    def _vector(self, text: str) -> Vector:
        vector = [0.0] * self.dimension
        vector[0] = 1e-3  # keeps a text without words from becoming a zero vector
        for token in self._TOKEN.findall(text.casefold()):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            vector[1 + int.from_bytes(digest[:4], "big") % (self.dimension - 1)] += 1.0
        norm = math.sqrt(sum(value * value for value in vector))
        return [value / norm for value in vector]

    def embed_documents(self, texts: list[str]) -> list[Vector]:
        return [self._vector(text) for text in texts]

    def embed_query(self, text: str) -> Vector:
        return self._vector(text)

    def warm_up(self) -> None:
        """Nothing to load."""


def make_embedder(config: EmbeddingsConfig) -> Embedder:
    """The single place that maps the `embeddings.provider` setting to a class."""
    if config.provider == "fake":
        return FakeEmbedder()
    return SentenceTransformerEmbedder(config)
