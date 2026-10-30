"""Ingestion entry point used by `python -m app ingest`.

Why it returns data instead of printing: the core package is UI-agnostic, so the
command line decides how to show the report. Cleaned documents are rebuilt from
the HTML cache on every run and never written to disk (the text belongs to the
publisher, and the cache already makes this fast and offline). Chunks are kept
in memory the same way until CW-103 writes them to the vector index.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from carwise.config import Settings, load_settings
from carwise.ingest.chunk import chunk_document
from carwise.ingest.clean import Document, clean_html
from carwise.ingest.fetch import Fetcher, FetchResult, fallback_message
from carwise.registry import Registry, load_registry
from carwise.schemas import Chunk


@dataclass(frozen=True)
class IngestResult:
    fetches: list[FetchResult]
    documents: list[Document]
    errors: dict[str, str] = field(default_factory=dict)  # car id -> why clean or chunk failed
    chunks: list[Chunk] = field(default_factory=list)  # article order, then chunk order
    fallback: str | None = None

    @property
    def ok(self) -> bool:
        return self.fallback is None and not self.errors


def ingest(
    settings: Settings | None = None,
    registry: Registry | None = None,
    *,
    fetcher: Fetcher | None = None,
) -> IngestResult:
    """Fetch every registry article into the cache, then clean and chunk what is available."""
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
    return IngestResult(fetches, documents, errors, chunks, fallback)
