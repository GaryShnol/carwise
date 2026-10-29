"""Ingestion entry point used by `python -m app ingest`.

Why it returns data instead of printing: the core package is UI-agnostic, so the
command line decides how to show the report. Cleaned documents are rebuilt from
the HTML cache on every run and never written to disk (the text belongs to the
publisher, and the cache already makes this fast and offline).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from carwise.config import Settings, load_settings
from carwise.ingest.clean import Document, clean_html
from carwise.ingest.fetch import Fetcher, FetchResult, fallback_message
from carwise.registry import Registry, load_registry


@dataclass(frozen=True)
class IngestResult:
    fetches: list[FetchResult]
    documents: list[Document]
    errors: dict[str, str] = field(default_factory=dict)  # car id -> why cleaning failed
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
    """Fetch every registry article into the cache, then clean whatever is available."""
    settings = settings or load_settings()
    registry = registry or load_registry()
    raw_dir = Path(settings.paths.raw_dir)
    fetcher = fetcher or Fetcher(settings.fetch, raw_dir)
    fetches = fetcher.fetch_all(registry.cars)
    documents: list[Document] = []
    errors: dict[str, str] = {}
    for car, result in zip(registry.cars, fetches, strict=True):
        if not result.ok:
            continue
        try:
            html = result.path.read_text(encoding="utf-8")
            documents.append(clean_html(html, car_id=car.id, source_url=car.url))
        except (OSError, ValueError) as error:
            errors[car.id] = str(error)
    return IngestResult(fetches, documents, errors, fallback_message(fetches, raw_dir))
