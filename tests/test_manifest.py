"""Corpus manifest (CW-610): deterministic hashes, warnings only, no article text.

Synthetic documents and chunks only: the repository is public and the articles are not ours.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

import yaml

from carwise.config import load_settings
from carwise.ingest.clean import Block, BlockKind, Document
from carwise.ingest.manifest import (
    build_manifest,
    chunks_sha256,
    compare,
    document_sha256,
    load_manifest,
    manifest_sha256,
    write_manifest,
)
from carwise.registry import load_registry
from carwise.retrieval.embedder import FakeEmbedder
from carwise.retrieval.store import build_index, stored_fingerprint
from carwise.schemas import Chunk
from eval.report import corpus_line, corpus_stamp

HEX64 = re.compile(r"^[0-9a-f]{64}$")
HEBREW = re.compile(r"[֐-׿]")


def _document(car_id: str, paragraph: str = "פסקה סינתטית על הרכב") -> Document:
    return Document(
        car_id=car_id,
        title="כותרת סינתטית",
        published=datetime(2026, 1, 1, tzinfo=UTC),
        source_url=f"https://example.test/{car_id}/",
        blocks=[
            Block(kind=BlockKind.HEADING, text="מה המנוע?", level=2),
            Block(kind=BlockKind.PARAGRAPH, text=paragraph),
        ],
    )


def _chunk(car_id: str, position: int, text: str = "טקסט סינתטי של קטע") -> Chunk:
    return Chunk(
        chunk_id=f"{car_id}:{position:03d}",
        car=car_id,
        car_name="רכב בדיקה",
        section="מה המנוע?",
        source_url=f"https://example.test/{car_id}/",
        published=None,
        text=text,
        embed_text=f"רכב בדיקה — {text}",
    )


def _corpus(paragraph: str = "פסקה סינתטית על הרכב") -> tuple[list[Document], list[Chunk]]:
    docs = [_document("aa1", paragraph), _document("bb2")]
    chunks = [_chunk("aa1", 0), _chunk("aa1", 1, "קטע שני"), _chunk("bb2", 0)]
    return docs, chunks


def test_document_hash_is_deterministic_and_changes_with_one_character() -> None:
    assert document_sha256(_document("aa1")) == document_sha256(_document("aa1"))
    assert document_sha256(_document("aa1")) != document_sha256(
        _document("aa1", "פסקה סינתטית על הרכב!")
    )
    assert HEX64.match(document_sha256(_document("aa1")))


def test_chunk_hash_is_deterministic_and_changes_with_one_character_or_id() -> None:
    chunks = [_chunk("aa1", 0)]
    assert chunks_sha256(chunks) == chunks_sha256([_chunk("aa1", 0)])
    assert chunks_sha256(chunks) != chunks_sha256([_chunk("aa1", 0, "טקסט סינתטי של קטע.")])
    assert chunks_sha256(chunks) != chunks_sha256([_chunk("aa1", 1)])


def test_registry_wording_does_not_change_the_chunk_hash() -> None:
    renamed = _chunk("aa1", 0).model_copy(update={"car_name": "שם אחר", "source_url": "x"})
    assert chunks_sha256([renamed]) == chunks_sha256([_chunk("aa1", 0)])


def test_manifest_round_trips_and_holds_hashes_and_counts_only(tmp_path: Path) -> None:
    docs, chunks = _corpus()
    manifest = build_manifest(docs, chunks)
    path = tmp_path / "corpus.lock.yaml"
    write_manifest(manifest, path)
    assert load_manifest(path) == manifest
    assert manifest_sha256(path) == manifest.sha256() == build_manifest(docs, chunks).sha256()
    assert manifest.articles["aa1"].chunks == 2 and manifest.articles["bb2"].chunks == 1
    text = path.read_text(encoding="utf-8")
    assert not HEBREW.search(text)
    assert "example.test" not in text


def test_committed_manifest_has_no_article_text() -> None:
    path = Path(load_settings().paths.corpus_manifest)
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert not HEBREW.search(path.read_text(encoding="utf-8"))
    assert "http" not in path.read_text(encoding="utf-8")
    assert set(raw) == {"format", "corpus_sha256", "articles"}
    assert HEX64.match(raw["corpus_sha256"])
    assert list(raw["articles"]) == [car.id for car in load_registry().cars]
    for entry in raw["articles"].values():
        assert set(entry) == {"text_sha256", "chunks_sha256", "chunks"}
        assert HEX64.match(entry["text_sha256"]) and HEX64.match(entry["chunks_sha256"])
        assert isinstance(entry["chunks"], int)


def test_compare_names_each_changed_missing_extra_or_rechunked_article() -> None:
    docs, chunks = _corpus()
    pinned = build_manifest(docs, chunks)
    assert compare(pinned, build_manifest(docs, chunks)) == []

    edited_docs, _ = _corpus("פסקה ערוכה")
    edited = compare(pinned, build_manifest(edited_docs, chunks))
    assert len(edited) == 1 and "[aa1] article text differs" in edited[0]

    rechunked = compare(pinned, build_manifest(docs, chunks[1:]))
    assert len(rechunked) == 1 and "[aa1] same article text, but its chunks differ" in rechunked[0]

    partial = compare(pinned, build_manifest(docs[:1], chunks[:2]))
    assert partial == ["[bb2] in the manifest but not ingested this run"]

    extra_docs = [*docs, _document("cc3")]
    extra = compare(pinned, build_manifest(extra_docs, [*chunks, _chunk("cc3", 0)]))
    assert extra == ["[cc3] ingested but not in the manifest"]


def test_invalid_manifest_gives_no_report_hash(tmp_path: Path) -> None:
    path = tmp_path / "corpus.lock.yaml"
    path.write_text("articles: not a mapping\n", encoding="utf-8")
    assert manifest_sha256(path) is None
    assert manifest_sha256(tmp_path / "missing.yaml") is None


def test_report_stamp_names_the_index_fingerprint_and_the_manifest_hash(tmp_path: Path) -> None:
    loaded = load_settings()
    paths = loaded.paths.model_copy(
        update={
            "index_dir": str(tmp_path / "index"),
            "corpus_manifest": str(tmp_path / "corpus.lock.yaml"),
        }
    )
    settings = loaded.model_copy(update={"paths": paths})
    assert corpus_stamp(settings) == (None, None)

    docs, chunks = _corpus()
    manifest = build_manifest(docs, chunks)
    write_manifest(manifest, Path(paths.corpus_manifest))
    build_index(chunks, FakeEmbedder(), settings.chunking, Path(paths.index_dir))
    stamp = corpus_stamp(settings)
    assert stamp.corpus_manifest_sha256 == manifest.sha256()
    assert stamp.index_fingerprint == stored_fingerprint(Path(paths.index_dir))
    assert stamp.index_fingerprint is not None
    line = " ".join(corpus_line(*stamp))
    assert f"manifest sha256 {manifest.sha256()}" in line
    assert f"index fingerprint {stamp.index_fingerprint}" in line
    assert corpus_line(None, None) == []  # reports made before CW-610 render as before
