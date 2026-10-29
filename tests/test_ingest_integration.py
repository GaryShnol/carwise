"""Checks against the real cached articles; skipped when data/raw/ is not populated.

Assertions compare plain counts and booleans and their messages name car ids
only, so a failure never prints article text: the repository and CI logs are public.
"""

from pathlib import Path

import pytest

from carwise.config import load_settings
from carwise.ingest.clean import BlockKind, Document, clean_html
from carwise.ingest.fetch import cache_path
from carwise.registry import Car, load_registry

RAW_DIR = Path(load_settings().paths.raw_dir)
CARS = load_registry().cars
LONG_TERM_REPORT = "kia_ev9"

pytestmark = pytest.mark.skipif(
    not all(cache_path(RAW_DIR, car).exists() for car in CARS),
    reason="data/raw/ is not populated; run `python -m app ingest` first",
)


def _document(car: Car) -> Document:
    html = cache_path(RAW_DIR, car).read_text(encoding="utf-8")
    return clean_html(html, car_id=car.id, source_url=car.url)


@pytest.mark.parametrize("car", CARS, ids=lambda car: car.id)
def test_article_is_cleaned_into_structured_blocks(car: Car) -> None:
    doc = _document(car)
    has_title = bool(doc.title)
    has_date = doc.published is not None
    starts_with_title = doc.blocks[0].kind is BlockKind.HEADING and doc.blocks[0].level == 1
    paragraphs = doc.count(BlockKind.PARAGRAPH)
    table_rows = doc.count(BlockKind.TABLE_ROW)
    subheadings = sum(1 for b in doc.blocks if b.kind is BlockKind.HEADING and b.level != 1)
    assert has_title and has_date and starts_with_title, car.id
    assert paragraphs >= 10, car.id
    if car.id == LONG_TERM_REPORT:
        assert subheadings == 0, car.id  # paragraph structure, title as the section
    else:
        assert subheadings >= 5, car.id
        assert table_rows >= 4, car.id  # the spec table survives


@pytest.mark.parametrize("car", CARS, ids=lambda car: car.id)
def test_no_site_boilerplate_survives(car: Car) -> None:
    text = " ".join(block.text for block in _document(car).blocks)
    for marker in ("כתבות אחרונות", "הצטרפו לוואטסאפ", "מותגים מתחרים", "סיכום AI", "צילום:"):
        found = marker in text
        assert not found, f"{car.id}: boilerplate marker {marker!r} found"


@pytest.mark.parametrize("car", CARS, ids=lambda car: car.id)
def test_registry_quotes_come_from_the_article(car: Car) -> None:
    text = " ".join(block.text for block in _document(car).blocks)
    for field in ("body_type_quote", "powertrain_quote"):
        quote = getattr(car, field)
        if quote is None:
            continue
        for fragment in (part.strip() for part in quote.split("…")):
            found = fragment in text
            assert found, f"{car.id}: {field} not found in the article"


@pytest.mark.parametrize("car", CARS, ids=lambda car: car.id)
def test_registry_aliases_appear_in_the_article(car: Car) -> None:
    text = " ".join(block.text for block in _document(car).blocks)
    for alias in [*car.aliases_he, *car.aliases_latin]:
        found = alias in text
        assert found, f"{car.id}: alias not found in the article"
