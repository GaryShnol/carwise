"""Local persistent Chroma collection holding the chunk vectors.

Why Chroma: an embedded store with metadata filters and on-disk persistence,
no server to run, which is all 75 chunks need. Why a fingerprint: embedding the
corpus takes a while on CPU, so `ingest` should be a no-op when nothing that
affects the vectors changed, and must rebuild when anything did (model,
revision, prefixes, chunk limits, chunk ids or chunk text).
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Literal

import chromadb
from chromadb.api import ClientAPI
from chromadb.api.models.Collection import Collection
from chromadb.api.types import Where
from chromadb.config import Settings as ChromaSettings

from carwise.config import ChunkingConfig
from carwise.retrieval.embedder import Embedder, Vector
from carwise.schemas import Chunk

COLLECTION = "chunks"
FINGERPRINT_KEY = "fingerprint"
EMBEDDER_KEY = "embedder"  # lets a reader refuse an index built by another model
# Chroma returns float32 distances; rounding keeps equal scores equal across runs,
# so the chunk-id tie-break decides and the ranking stays deterministic.
SCORE_DECIMALS = 6


class IndexNotReadyError(RuntimeError):
    """The index is missing or was built with different settings; run ingest."""


@dataclass(frozen=True)
class IndexBuild:
    rebuilt: bool
    chunks: int
    seconds: float


def fingerprint(chunks: list[Chunk], embedder: Embedder, limits: ChunkingConfig) -> str:
    text_hash = hashlib.sha256("\x1e".join(c.embed_text for c in chunks).encode("utf-8"))
    payload = {
        "embedder": embedder.identity,
        "chunking": limits.model_dump(),
        "chunk_ids": [c.chunk_id for c in chunks],
        "text_sha256": text_hash.hexdigest(),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def _client(index_dir: Path) -> ClientAPI:
    index_dir.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(
        path=str(index_dir), settings=ChromaSettings(anonymized_telemetry=False)
    )


def _metadata(chunk: Chunk) -> dict[str, str]:
    # Chroma metadata cannot hold None, so a missing date is a missing key.
    meta = {
        "chunk_id": chunk.chunk_id,
        "car": chunk.car,
        "car_name": chunk.car_name,
        "section": chunk.section,
        "source_url": chunk.source_url,
        "embed_text": chunk.embed_text,
    }
    if chunk.published:
        meta["published"] = chunk.published.isoformat()
    return meta


def _chunk(text: str, meta: dict[str, Any]) -> Chunk:
    published = meta.get("published")
    return Chunk(
        chunk_id=str(meta["chunk_id"]),
        car=str(meta["car"]),
        car_name=str(meta["car_name"]),
        section=str(meta["section"]),
        source_url=str(meta["source_url"]),
        published=date.fromisoformat(str(published)) if published else None,
        text=text,
        embed_text=str(meta["embed_text"]),
    )


def _identity(embedder: Embedder) -> str:
    return json.dumps(embedder.identity, sort_keys=True)


def _stored_metadata(index_dir: Path) -> dict[str, Any] | None:
    if not index_dir.exists():
        return None
    client = _client(index_dir)
    if COLLECTION not in {collection.name for collection in client.list_collections()}:
        return None
    return dict(client.get_collection(COLLECTION).metadata or {})


def stored_fingerprint(index_dir: Path) -> str | None:
    value = (_stored_metadata(index_dir) or {}).get(FINGERPRINT_KEY)
    return str(value) if value is not None else None


def build_index(
    chunks: list[Chunk], embedder: Embedder, limits: ChunkingConfig, index_dir: Path
) -> IndexBuild:
    """(Re)build the collection unless the stored fingerprint already matches."""
    started = time.perf_counter()
    expected = fingerprint(chunks, embedder, limits)
    if stored_fingerprint(index_dir) == expected:
        return IndexBuild(rebuilt=False, chunks=len(chunks), seconds=time.perf_counter() - started)
    vectors = embedder.embed_documents([c.embed_text for c in chunks])
    client = _client(index_dir)
    if COLLECTION in {collection.name for collection in client.list_collections()}:
        client.delete_collection(COLLECTION)
    collection = client.create_collection(
        COLLECTION,
        configuration={"hnsw": {"space": "cosine"}},
        metadata={FINGERPRINT_KEY: expected, EMBEDDER_KEY: _identity(embedder)},
    )
    if chunks:
        collection.add(
            ids=[c.chunk_id for c in chunks],
            embeddings=vectors,
            documents=[c.text for c in chunks],
            metadatas=[_metadata(c) for c in chunks],
        )
    return IndexBuild(rebuilt=True, chunks=len(chunks), seconds=time.perf_counter() - started)


class ChunkStore:
    """Read side of the index: exact cosine scores for every candidate chunk."""

    def __init__(self, index_dir: Path, embedder: Embedder | None = None) -> None:
        stored = _stored_metadata(index_dir)
        if stored is None:
            raise IndexNotReadyError(f"No index in {index_dir}; run `python -m app ingest`.")
        if embedder is not None and stored.get(EMBEDDER_KEY) != _identity(embedder):
            raise IndexNotReadyError(
                "The index was built with other embedding settings; run `python -m app ingest`."
            )
        self._collection: Collection = _client(index_dir).get_collection(COLLECTION)

    def count(self) -> int:
        return self._collection.count()

    def chunks(self) -> list[Chunk]:
        """Every stored chunk, in id order: the corpus the lexical index is built on."""
        result = self._collection.get(include=["documents", "metadatas"])
        documents = result["documents"] or []
        metadatas = result["metadatas"] or []
        pairs = zip(documents, metadatas, strict=True)
        return sorted((_chunk(t, dict(m)) for t, m in pairs), key=lambda c: c.chunk_id)

    def candidates(self, vector: Vector, car_ids: list[str] | None) -> list[tuple[Chunk, float]]:
        """Every chunk (of the given cars), with cosine similarity, unsorted.

        Asking for all of them, not top-k, keeps the ranking exact: with 75
        chunks the approximate HNSW search has nothing to approximate, and the
        caller sorts and cuts deterministically.
        """
        total = self.count()
        if total == 0:
            return []
        where: Where | None = None
        if car_ids is not None:
            in_cars: dict[Literal["$in", "$nin"], list[str | int | float | bool]]
            in_cars = {"$in": list(car_ids)}
            where = {"car": in_cars}
        result = self._collection.query(
            query_embeddings=[vector],
            n_results=total,
            where=where,
            include=["documents", "metadatas", "distances"],
        )
        documents = (result["documents"] or [[]])[0]
        metadatas = (result["metadatas"] or [[]])[0]
        distances = (result["distances"] or [[]])[0]
        return [
            (_chunk(text, dict(meta)), round(1.0 - distance, SCORE_DECIMALS))
            for text, meta, distance in zip(documents, metadatas, distances, strict=True)
        ]
