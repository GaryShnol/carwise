"""False-positive suite for the numeric check, over the real article chunks (CW-206).

Answers are built at test time from the cached articles: each sentence that has
a number is quoted as an answer, and each number is rewritten the ways an answer
writes it (no thousands commas, "N אלף", decimal comma). The source is only the
chunk the sentence came from, which is stricter than a real turn (five or more
chunks). Skipped when data/raw/ is not populated; no network.

Failures report chunk ids and number tokens only, never article text: the
repository and CI logs are public.
"""

import re
from decimal import Decimal
from pathlib import Path

import pytest

from carwise.config import load_settings
from carwise.guardrails import unsupported_numbers
from carwise.ingest.chunk import chunk_document
from carwise.ingest.clean import clean_html
from carwise.ingest.fetch import cache_path
from carwise.numbers import find_numbers, source_values
from carwise.registry import load_registry
from carwise.schemas import Chunk, RetrievedChunk

SETTINGS = load_settings()
REGISTRY = load_registry()
RAW_DIR = Path(SETTINGS.paths.raw_dir)
ALLOWED = SETTINGS.guardrails.numbers_always_allowed
_SENTENCE = re.compile(r"(?<=[.!?…])\s+|\n+")

pytestmark = pytest.mark.skipif(
    not all(cache_path(RAW_DIR, car).exists() for car in REGISTRY.cars),
    reason="data/raw/ is not populated; run `python -m app ingest` first",
)


def _chunks() -> list[Chunk]:
    chunks: list[Chunk] = []
    for car in REGISTRY.cars:
        html = cache_path(RAW_DIR, car).read_text(encoding="utf-8")
        doc = clean_html(html, car_id=car.id, source_url=car.url)
        chunks += chunk_document(doc, car, SETTINGS.chunking)
    return chunks


CHUNKS = _chunks() if all(cache_path(RAW_DIR, car).exists() for car in REGISTRY.cars) else []


def _flags(answer: str, chunk: Chunk) -> list[str]:
    hits = [RetrievedChunk(chunk=chunk, score=0.9)]
    return unsupported_numbers(answer, hits, [], REGISTRY, ALLOWED)


def _rewrites(token: str, value: Decimal) -> list[str]:
    """Ways an answer writes the same number."""
    found = []
    if "," in token and value == value.to_integral() and value >= 1000:
        found.append(str(int(value)))  # 178,888 -> 178888
        thousands = value / 1000
        found += [f"{int(thousands)} אלף", f"{int(thousands.quantize(Decimal(1)))} אלף"]
    if "." in token and "," not in token and len(token.split(".")[1]) < 3:
        found.append(token.replace(".", ","))  # 3.8 -> 3,8
    return found


def test_quoted_sentences_are_never_flagged() -> None:
    flagged: list[tuple[str, list[str]]] = []
    checked = 0
    for chunk in CHUNKS:
        for sentence in _SENTENCE.split(chunk.text):
            if not find_numbers(sentence):
                continue
            checked += 1
            problems = _flags(f"לפי הכתבה על {chunk.car_name}: {sentence}", chunk)
            if problems:
                flagged.append((chunk.chunk_id, problems))
    assert checked > 150  # the suite is not vacuous
    assert flagged == []


def test_rewritten_numbers_are_never_flagged() -> None:
    flagged: list[tuple[str, str]] = []
    checked = 0
    for chunk in CHUNKS:
        for number in find_numbers(chunk.text):
            for written in _rewrites(number.token, number.readings[0].value):
                checked += 1
                if _flags(f"הנתון ב{chunk.car_name} הוא {written}.", chunk):
                    flagged.append((chunk.chunk_id, written))
    assert checked > 50
    assert flagged == []


def test_a_nudged_number_is_caught_in_real_text() -> None:
    """The other side of the suite: change one integer by one and the check sees it."""
    missed: list[tuple[str, str]] = []
    checked = 0
    for chunk in CHUNKS:
        values = source_values([f"{chunk.car_name}\n{chunk.section}\n{chunk.text}"])
        for number in find_numbers(chunk.text):
            value = number.readings[0].value
            if value != value.to_integral() or value < 10 or len(number.readings) > 1:
                continue
            nudged = value + 1
            if any(abs(v - nudged) < 1 for v in values):
                continue  # the nudged value happens to be in the chunk too
            checked += 1
            if not _flags(f"הנתון ב{chunk.car_name} הוא {nudged}.", chunk):
                missed.append((chunk.chunk_id, str(nudged)))
    assert checked > 100
    assert missed == []
