"""Chunk the real cached articles; skipped when data/raw/ is not populated.

Assertions reduce everything to counts and booleans and name car ids only, so
a failure never prints article text: the repository and CI logs are public.
"""

from pathlib import Path

import pytest

from carwise.config import load_settings
from carwise.ingest.chunk import chunk_document, covers_document
from carwise.ingest.clean import clean_html
from carwise.ingest.fetch import cache_path
from carwise.registry import Car, load_registry
from carwise.schemas import Chunk

SETTINGS = load_settings()
LIMITS = SETTINGS.chunking
RAW_DIR = Path(SETTINGS.paths.raw_dir)
CARS = load_registry().cars
LONG_TERM_REPORT = "kia_ev9"

pytestmark = pytest.mark.skipif(
    not all(cache_path(RAW_DIR, car).exists() for car in CARS),
    reason="data/raw/ is not populated; run `python -m app ingest` first",
)


def _short_with_room(chunks: list[Chunk], index: int) -> bool:
    """A chunk below min_chars that a neighbor could have absorbed (the documented exception
    is a short chunk whose neighbors are both too full)."""
    size = len(chunks[index].text)
    if size >= LIMITS.min_chars or len(chunks) == 1:
        return False
    neighbors = chunks[max(index - 1, 0) : index] + chunks[index + 1 : index + 2]
    return any(len(n.text) + 1 + size <= LIMITS.max_chars for n in neighbors)


@pytest.mark.parametrize("car", CARS, ids=lambda car: car.id)
def test_article_chunks_cover_the_text_within_limits(car: Car) -> None:
    html = cache_path(RAW_DIR, car).read_text(encoding="utf-8")
    doc = clean_html(html, car_id=car.id, source_url=car.url)
    chunks = chunk_document(doc, car, LIMITS)

    covered = covers_document(doc, chunks)
    oversize = sum(1 for c in chunks if len(c.text) > LIMITS.max_chars)
    avoidably_short = sum(1 for i in range(len(chunks)) if _short_with_room(chunks, i))
    ids_in_order = [c.chunk_id for c in chunks] == [f"{car.id}:{i:03d}" for i in range(len(chunks))]
    metadata_ok = all(
        c.car == car.id
        and c.car_name == car.display_name
        and c.source_url == car.url
        and c.published is not None
        and bool(c.section)
        for c in chunks
    )
    assert len(chunks) >= 2, car.id
    assert covered, f"{car.id}: chunk texts do not reproduce the document blocks"
    assert oversize == 0, f"{car.id}: {oversize} chunks above max_chars"
    assert avoidably_short == 0, f"{car.id}: {avoidably_short} short chunks could have merged"
    assert ids_in_order and metadata_ok, car.id
    if car.id == LONG_TERM_REPORT:
        title_only = all(c.section == doc.title for c in chunks)
        assert title_only, car.id
