"""Ingestion entry point used by `python -m app ingest`.

Why it returns data instead of printing: the core package is UI-agnostic, so the
command line decides how to show the report. Cleaned documents are rebuilt from
the HTML cache on every run and never written to disk (the text belongs to the
publisher, and the cache already makes this fast and offline). The vector index
is built only when every article was cleaned, so a partial corpus never
replaces a complete index. The corpus is compared with the committed manifest
(CW-610) on every run; a difference is a warning, never a failure.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path

from carwise.config import Settings, load_settings
from carwise.ingest.chunk import chunk_document
from carwise.ingest.clean import Document, clean_html
from carwise.ingest.fetch import Fetcher, FetchResult, fallback_message
from carwise.ingest.manifest import CorpusManifest, build_manifest, compare, load_manifest
from carwise.registry import Registry, load_registry
from carwise.retrieval.embedder import Embedder, make_embedder
from carwise.retrieval.store import IndexBuild, build_index
from carwise.schemas import Chunk


@dataclass(frozen=True)
class IngestResult:
    fetches: list[FetchResult]
    documents: list[Document]
    errors: dict[str, str] = field(default_factory=dict)  # car id -> why clean or chunk failed
    chunks: list[Chunk] = field(default_factory=list)  # article order, then chunk order
    fallback: str | None = None
    index: IndexBuild | None = None  # None when the corpus was incomplete or the build failed
    index_error: str | None = None
    manifest: CorpusManifest | None = None  # hashes of what was ingested this run
    corpus_warnings: list[str] = field(default_factory=list)  # differences from the manifest

    @property
    def ok(self) -> bool:
        return self.fallback is None and not self.errors and self.index_error is None


def ingest(
    settings: Settings | None = None,
    registry: Registry | None = None,
    *,
    fetcher: Fetcher | None = None,
    embedder: Embedder | None = None,
) -> IngestResult:
    """Fetch, clean and chunk every registry article, then build the index if all succeeded."""
    settings = settings or load_settings()
    registry = registry or load_registry()
    raw_dir = Path(settings.paths.raw_dir)
    fetcher = fetcher or Fetcher(settings.fetch, raw_dir)
    fetches = fetcher.fetch_all(registry.cars)
    documents: list[Document] = []
    chunks: list[Chunk] = []
    errors: dict[str, str] = {}
    for car, result in zip(registry.cars, fetches, strict=True):
        if not result.ok:
            continue
        try:
            html = result.path.read_text(encoding="utf-8")
            document = clean_html(html, car_id=car.id, source_url=car.url)
            chunks += chunk_document(document, car, settings.chunking)
            documents.append(document)
        except (OSError, ValueError) as error:
            errors[car.id] = str(error)
    fallback = fallback_message(fetches, raw_dir)
    manifest = build_manifest(documents, chunks)
    warnings = corpus_warnings(manifest, Path(settings.paths.corpus_manifest))
    outcome = IngestResult(
        fetches, documents, errors, chunks, fallback, manifest=manifest, corpus_warnings=warnings
    )
    if not outcome.ok:
        return outcome
    embedder = embedder or make_embedder(settings.embeddings)
    index_dir = Path(settings.paths.index_dir)
    try:
        index = build_index(chunks, embedder, settings.chunking, index_dir)
    except OSError as error:  # model download or disk failure; Hugging Face errors are OSErrors
        return replace(outcome, index_error=f"index not built: {error}")
    return replace(outcome, index=index)


def corpus_warnings(manifest: CorpusManifest, path: Path) -> list[str]:
    """How this run's corpus differs from the committed manifest (empty when it matches)."""
    try:
        pinned = load_manifest(path)
    except ValueError as error:
        return [str(error)]
    if pinned is None:
        return [f"no corpus manifest at {path}; write one with `ingest --write-manifest`"]
    return compare(pinned, manifest)
