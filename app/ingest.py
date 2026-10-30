"""`python -m app ingest`: fetch, clean, chunk and index the eight articles, then report.

Why the report shows counts and headings only: the repository and its CI logs
are public, and the article body belongs to the publisher.
"""

from __future__ import annotations

import argparse
from collections import Counter
from statistics import median

from carwise.ingest.clean import BlockKind, Document
from carwise.ingest.run import IngestResult, ingest
from carwise.schemas import Chunk

HEADINGS_SHOWN = 3


def format_document(doc: Document) -> str:
    date = doc.published.date().isoformat() if doc.published else "unknown"
    chars = sum(len(block.text) for block in doc.blocks)
    sections = [b.text for b in doc.blocks if b.kind is BlockKind.HEADING and b.level != 1]
    first = " / ".join(sections[:HEADINGS_SHOWN]) or "(none: paragraphs only, title is the section)"
    return "\n".join(
        [
            f"[{doc.car_id}] {doc.title}",
            f"  date {date} | headings {doc.count(BlockKind.HEADING)}"
            f" | paragraphs {doc.count(BlockKind.PARAGRAPH)}"
            f" | list items {doc.count(BlockKind.LIST_ITEM)}"
            f" | table rows {doc.count(BlockKind.TABLE_ROW)} | chars {chars:,}",
            f"  first headings: {first}",
        ]
    )


def _length_stats(chunks: list[Chunk]) -> str:
    sizes = [len(chunk.text) for chunk in chunks]
    return f"{min(sizes):>5} / {median(sizes):>7.1f} / {max(sizes):>5}"


def format_chunk_stats(chunks: list[Chunk]) -> str:
    """Chunk count and length spread per car: enough to spot a bad split, no article text."""
    if not chunks:
        return "chunks: none"
    by_car: dict[str, list[Chunk]] = {}
    for chunk in chunks:
        by_car.setdefault(chunk.car, []).append(chunk)
    width = max(len(car) for car in by_car)
    lines = ["chunks per car (length in chars: min / median / max)"]
    lines += [
        f"  {car:<{width}}  {len(group):>3} chunks  {_length_stats(group)}"
        for car, group in by_car.items()
    ]
    lines.append(f"  {'total':<{width}}  {len(chunks):>3} chunks  {_length_stats(chunks)}")
    return "\n".join(lines)


def format_index(result: IngestResult) -> str:
    if result.index_error:
        return result.index_error
    if result.index is None:
        return "index not built: some articles are missing or could not be processed"
    index = result.index
    if not index.rebuilt:
        return f"index up to date ({index.chunks} chunks, checked in {index.seconds:.1f}s)"
    return f"index built: {index.chunks} chunks in {index.seconds:.1f}s"


def format_report(result: IngestResult) -> str:
    statuses = Counter(fetch.status.value for fetch in result.fetches)
    summary = ", ".join(f"{count} {status}" for status, count in sorted(statuses.items()))
    lines = [f"fetch: {summary}", ""]
    lines += [format_document(doc) + "\n" for doc in result.documents]
    lines += [f"[{car_id}] could not be processed: {why}" for car_id, why in result.errors.items()]
    if result.fallback:
        lines += ["", result.fallback]
    lines.append(f"cleaned {len(result.documents)} of {len(result.fetches)} articles")
    lines += ["", format_chunk_stats(result.chunks), "", format_index(result)]
    return "\n".join(lines)


def run(args: argparse.Namespace) -> int:
    result = ingest()
    print(format_report(result))
    return 0 if result.ok else 1
