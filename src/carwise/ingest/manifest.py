"""Corpus manifest: SHA-256 hashes that pin the eight articles without holding their text.

Why: the published eval numbers and the chunk ids in the committed reports depend on
what the publisher served on the day of ingestion. If an article is edited later, a
fresh `ingest` yields different chunks, and the reports would silently stop
matching. The manifest (committed, `paths.corpus_manifest`) records one hash per
article plus one over the whole chunk list, so `ingest` can say which article
changed, and every eval report names the manifest it was checked against.

Why the cleaned text and not the raw HTML: the page around the article (ads,
tracking ids, script and cache tokens, "latest articles" boxes) changes on every
fetch while the article itself does not, so a raw-HTML hash would warn on every
download. The cleaned document is exactly what feeds the chunks.

What is hashed, exactly (deterministic; SHA-256 over UTF-8 bytes of compact JSON,
`ensure_ascii=False`, keys sorted, separators "," and ":"; text is already NFC and
whitespace-collapsed by `clean.normalize_text`):
- `text_sha256`: {"title", "published" (ISO 8601 or null), "blocks": [[kind, level,
  text], ...]} of the cleaned document, in document order.
- `chunks_sha256`: the article's chunks as [[chunk_id, section, text, table_labels],
  ...] in chunk order. Registry-derived fields (display name, URL, embed text) are
  left out, so a cars.yaml wording change is not reported as an article change.
- `corpus_sha256`: the same chunk serialization over every chunk, article order of
  the registry, then chunk order.
The manifest holds hex digests and counts only: no article text, no URLs.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from carwise.ingest.clean import Document
from carwise.schemas import Chunk

FORMAT = 1
_HEX64 = r"^[0-9a-f]{64}$"
HEADER = (
    "# Corpus manifest (CW-610): SHA-256 of each article's cleaned text and chunks.\n"
    "# Hashes and counts only, no article text. Written by\n"
    "# `python -m app ingest --write-manifest`; see src/carwise/ingest/manifest.py.\n"
)


class ArticleHashes(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    text_sha256: str = Field(pattern=_HEX64)
    chunks_sha256: str = Field(pattern=_HEX64)
    chunks: int = Field(ge=0)


class CorpusManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    format: int = FORMAT
    corpus_sha256: str = Field(pattern=_HEX64)
    articles: dict[str, ArticleHashes]  # car id -> hashes, registry order

    def sha256(self) -> str:
        """One hash of the whole manifest, written into eval report headers."""
        return _sha256(self.model_dump(mode="json"))


def _sha256(value: Any) -> str:
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def document_sha256(document: Document) -> str:
    published = document.published.isoformat() if document.published else None
    blocks = [[block.kind.value, block.level, block.text] for block in document.blocks]
    return _sha256({"title": document.title, "published": published, "blocks": blocks})


def _chunk_rows(chunks: list[Chunk]) -> list[list[Any]]:
    return [[c.chunk_id, c.section, c.text, c.table_labels] for c in chunks]


def chunks_sha256(chunks: list[Chunk]) -> str:
    return _sha256(_chunk_rows(chunks))


def build_manifest(documents: list[Document], chunks: list[Chunk]) -> CorpusManifest:
    """Hashes for the given documents; `chunks` in ingest order (article, then chunk)."""
    articles: dict[str, ArticleHashes] = {}
    for document in documents:
        own = [chunk for chunk in chunks if chunk.car == document.car_id]
        articles[document.car_id] = ArticleHashes(
            text_sha256=document_sha256(document),
            chunks_sha256=chunks_sha256(own),
            chunks=len(own),
        )
    return CorpusManifest(corpus_sha256=chunks_sha256(chunks), articles=articles)


def load_manifest(path: Path) -> CorpusManifest | None:
    """The committed manifest, or None when the file does not exist.

    Raises ValueError when the file exists but cannot be read as a manifest.
    """
    if not path.exists():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:  # a directory, no permission, binary junk
        raise ValueError(f"corpus manifest {path} cannot be read: {error}") from error
    try:
        return CorpusManifest.model_validate(yaml.safe_load(text))
    except (yaml.YAMLError, ValidationError) as error:
        raise ValueError(f"corpus manifest {path} is not valid: {error}") from error


def manifest_sha256(path: Path) -> str | None:
    """Hash of the committed manifest for report headers; None if it is missing or invalid."""
    try:
        manifest = load_manifest(path)
    except ValueError:
        return None
    return manifest.sha256() if manifest else None


def write_manifest(manifest: CorpusManifest, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = yaml.safe_dump(manifest.model_dump(mode="json"), sort_keys=False)
    path.write_text(HEADER + body, encoding="utf-8", newline="\n")


def compare(expected: CorpusManifest, actual: CorpusManifest) -> list[str]:
    """One warning per difference; empty when the local corpus matches the manifest.

    Warnings only: the publisher may legitimately edit an article, and ingest must
    still work. The warning tells the reader that published numbers may not reproduce.
    """
    warnings: list[str] = []
    for car_id, pinned in expected.articles.items():
        local = actual.articles.get(car_id)
        if local is None:
            warnings.append(f"[{car_id}] in the manifest but not ingested this run")
        elif local.text_sha256 != pinned.text_sha256:
            warnings.append(
                f"[{car_id}] article text differs from the manifest "
                "(the publisher may have edited it)"
            )
        elif local != pinned:
            warnings.append(
                f"[{car_id}] same article text, but its chunks differ from the manifest "
                f"({local.chunks} chunks, manifest {pinned.chunks}; chunking settings or code?)"
            )
    warnings += [
        f"[{car_id}] ingested but not in the manifest"
        for car_id in actual.articles
        if car_id not in expected.articles
    ]
    if not warnings and actual.corpus_sha256 != expected.corpus_sha256:
        warnings.append("the chunk list differs from the manifest (article order?)")
    return warnings
