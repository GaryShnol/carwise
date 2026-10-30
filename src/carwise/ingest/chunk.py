"""Split a cleaned article into retrievable chunks along its own structure.

Why structure and not a fixed window: a road test is organized by question-style
headings (engine, driving, interior, price), so a chunk that is one section
answers one kind of question and can be cited as "car, section". Size limits
only correct the extremes: tiny sections (a spec table, a single FAQ answer)
carry too little context to retrieve well, and huge ones dilute the embedding.

Why heading lines stay in the chunk text: once two short sections are merged,
the headings inside the text are what tell the reader (and the model) which
lines are pros and which are cons, or which answer belongs to which question.
It also makes the coverage rule exact: every block of the document appears in
exactly one chunk, in order.

Size rule, in order of precedence: a chunk never exceeds `max_chars`; a chunk
is below `min_chars` only when merging it with either neighbor would exceed
`max_chars` (or the whole article is shorter than `min_chars`).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from carwise.config import ChunkingConfig
from carwise.guardrails import section_label
from carwise.ingest.clean import Block, BlockKind, Document
from carwise.registry import Car
from carwise.schemas import Chunk

SECTION_SEPARATOR = " / "
EMBED_SEPARATOR = " — "
LINE_SEPARATOR = "\n"
# Sentence ends: punctuation, optionally followed by a closing quote, then whitespace.
_SENTENCE_END = re.compile(r"(?<=[.!?…])\s+|(?<=[.!?…][\"”״'])\s+")


@dataclass
class _Section:
    names: list[str]
    blocks: list[Block] = field(default_factory=list)

    @property
    def heading_only(self) -> bool:
        return all(block.kind is BlockKind.HEADING for block in self.blocks)


@dataclass
class _Piece:
    names: list[str]
    lines: list[str]

    @property
    def size(self) -> int:
        return len(LINE_SEPARATOR.join(self.lines))

    def merged(self, other: _Piece) -> _Piece:
        names = self.names + [name for name in other.names if name not in self.names]
        return _Piece(names, self.lines + other.lines)


def build_sections(doc: Document) -> list[_Section]:
    """Group blocks under their heading; text before the first subheading belongs to the title.

    A heading with no text of its own (the FAQ heading, directly followed by its
    first question) is carried into the next section instead of standing alone,
    so its name survives for citation and it never becomes a chunk by itself.
    """
    sections: list[_Section] = []
    current = _Section([doc.title])
    for block in doc.blocks:
        if block.kind is BlockKind.HEADING and block.level != 1:
            if current.heading_only:
                current = _Section([*current.names, block.text], [*current.blocks, block])
                continue
            sections.append(current)
            current = _Section([block.text])
        current.blocks.append(block)
    if current.blocks:
        sections.append(current)
    return sections


def _pack(parts: list[str], separator: str, max_chars: int) -> list[list[str]]:
    """Greedily group consecutive parts while their joined length fits; never reorder or drop."""
    groups: list[list[str]] = []
    size = 0
    for part in parts:
        if groups and size + len(separator) + len(part) <= max_chars:
            groups[-1].append(part)
            size += len(separator) + len(part)
        else:
            groups.append([part])
            size = len(part)
    return groups


def _pack_evenly(parts: list[str], separator: str, max_chars: int) -> list[list[str]]:
    """As many groups as greedy packing needs, but as even as possible.

    Greedy packing fills the first groups to the limit and can leave a tiny
    remainder, which then has no room to merge with a neighbor. Retrying with
    the smallest limit that still yields the same number of groups fixes that.
    Parts are already at most max_chars long, so every group still fits.
    """
    groups = _pack(parts, separator, max_chars)
    if len(groups) < 2:
        return groups
    total = len(separator.join(parts))
    for limit in range(-(-total // len(groups)), max_chars):
        even = _pack(parts, separator, limit)
        if len(even) == len(groups):
            return even
    return groups


def _hard_split(text: str, max_chars: int) -> list[str]:
    """Last resort for a sentence longer than max_chars: split at spaces, then by length."""
    words: list[str] = []
    for word in text.split(" "):
        words += [word[i : i + max_chars] for i in range(0, len(word), max_chars)] or [word]
    return [" ".join(group) for group in _pack(words, " ", max_chars)]


def split_block(text: str, max_chars: int) -> list[str]:
    """A block that fits is returned whole; an oversize one is cut at sentence ends."""
    if len(text) <= max_chars:
        return [text]
    sentences: list[str] = []
    for sentence in _SENTENCE_END.split(text):
        sentences += [sentence] if len(sentence) <= max_chars else _hard_split(sentence, max_chars)
    return [" ".join(group) for group in _pack_evenly(sentences, " ", max_chars)]


def _split_section(section: _Section, max_chars: int) -> list[_Piece]:
    lines = [line for block in section.blocks for line in split_block(block.text, max_chars)]
    groups = _pack_evenly(lines, LINE_SEPARATOR, max_chars)
    return [_Piece(list(section.names), group) for group in groups]


def _merge_short(pieces: list[_Piece], min_chars: int, max_chars: int) -> list[_Piece]:
    """Fold a short piece into the previous one, or the next one when there is no room behind.

    The second condition (`out[-1].size < min_chars`) is what lets a short first
    piece, or one that did not fit behind, absorb the piece after it.
    """
    out: list[_Piece] = []
    for piece in pieces:
        short = piece.size < min_chars or (bool(out) and out[-1].size < min_chars)
        if out and short and out[-1].size + len(LINE_SEPARATOR) + piece.size <= max_chars:
            out[-1] = out[-1].merged(piece)
        else:
            out.append(piece)
    return out


def chunk_document(doc: Document, registry_car: Car, limits: ChunkingConfig) -> list[Chunk]:
    """Turn one cleaned article into ordered chunks with citation metadata."""
    if doc.car_id != registry_car.id:
        raise ValueError(f"document {doc.car_id} chunked with registry car {registry_car.id}")
    if not 0 < limits.min_chars <= limits.max_chars:
        raise ValueError("chunking limits must satisfy 0 < min_chars <= max_chars")
    pieces = [
        piece
        for section in build_sections(doc)
        for piece in _split_section(section, limits.max_chars)
    ]
    chunks: list[Chunk] = []
    for index, piece in enumerate(_merge_short(pieces, limits.min_chars, limits.max_chars)):
        section = SECTION_SEPARATOR.join(piece.names)
        text = LINE_SEPARATOR.join(piece.lines)
        # The full section stays in the metadata for citations; the embedded header uses the
        # short label, so a long merged heading does not push the text out of the window.
        header = section_label(section, limits.embed_section_chars)
        chunks.append(
            Chunk(
                chunk_id=f"{registry_car.id}:{index:03d}",
                car=registry_car.id,
                car_name=registry_car.display_name,
                section=section,
                source_url=doc.source_url,
                published=doc.published.date() if doc.published else None,
                text=text,
                embed_text=f"{registry_car.display_name}{EMBED_SEPARATOR}{header}\n{text}",
            )
        )
    return chunks


def _squeeze(text: str) -> str:
    return "".join(text.split())


def covers_document(doc: Document, chunks: list[Chunk]) -> bool:
    """True when the chunk texts, in order, are exactly the document's blocks, in order.

    Whitespace is ignored because a block split at sentence ends loses the
    space between its parts; everything else must match, so nothing was lost,
    duplicated or reordered.
    """
    expected = "".join(_squeeze(block.text) for block in doc.blocks)
    return "".join(_squeeze(chunk.text) for chunk in chunks) == expected
