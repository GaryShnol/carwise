"""`python -m app ingest`: fetch, clean, chunk and index the eight articles, then report.

Why the report shows counts and headings only: the repository and its CI logs
are public, and the article body belongs to the publisher.
"""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
from statistics import median

from carwise.config import load_settings
from carwise.ingest.clean import BlockKind, Document
from carwise.ingest.manifest import write_manifest
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


def format_corpus(result: IngestResult) -> str:
    if not result.corpus_warnings:
        return "corpus matches the manifest"
    lines = ["WARNING: the corpus differs from the manifest; published numbers may not reproduce"]
    return "\n".join(lines + [f"  {warning}" for warning in result.corpus_warnings])


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
    lines += ["", format_corpus(result)]
    return "\n".join(lines)


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--write-manifest",
        action="store_true",
        help="pin the current corpus: rewrite the committed hash manifest (CW-610)",
    )


def run(args: argparse.Namespace) -> int:
    settings = load_settings()
    result = ingest(settings)
    print(format_report(result))
    if getattr(args, "write_manifest", False):
        if result.manifest is None or result.fallback or result.errors:
            print("manifest not written: every article must be cleaned first")
            return 1
        path = Path(settings.paths.corpus_manifest)
        write_manifest(result.manifest, path)
        print(f"manifest written: {path} ({len(result.manifest.articles)} articles)")
    return 0 if result.ok else 1
