"""`python -m app ingest`: fetch, clean and report on the eight articles.

Why the report shows counts and headings only: the repository and its CI logs
are public, and the article body belongs to the publisher.
"""

from __future__ import annotations

from collections import Counter

from carwise.ingest.clean import BlockKind, Document
from carwise.ingest.run import IngestResult, ingest

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


def format_report(result: IngestResult) -> str:
    statuses = Counter(fetch.status.value for fetch in result.fetches)
    summary = ", ".join(f"{count} {status}" for status, count in sorted(statuses.items()))
    lines = [f"fetch: {summary}", ""]
    lines += [format_document(doc) + "\n" for doc in result.documents]
    lines += [f"[{car_id}] could not be cleaned: {why}" for car_id, why in result.errors.items()]
    if result.fallback:
        lines += ["", result.fallback]
    lines.append(f"cleaned {len(result.documents)} of {len(result.fetches)} articles")
    return "\n".join(lines)


def run() -> int:
    result = ingest()
    print(format_report(result))
    return 0 if result.ok else 1
