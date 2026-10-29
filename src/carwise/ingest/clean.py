"""Turn a cached auto.co.il article page into a typed, ordered list of text blocks.

Why blocks and not one flat string: chunking (CW-102) splits on structure, so
headings must stay distinguishable from paragraphs, and the spec table and the
pros and cons lists carry most of the hard numbers (price, horsepower, range).
Why a hand-written walk over the DOM: the page mixes the article with menus,
galleries, tooltips and teaser lists, and a generic "readability" extractor
would silently drop the spec table, which is exactly what we need to keep.
"""

from __future__ import annotations

import html
import json
import re
import unicodedata
from collections.abc import Iterator
from datetime import datetime
from enum import StrEnum
from typing import Any

from bs4 import BeautifulSoup
from bs4.element import NavigableString, PageElement, Tag
from pydantic import BaseModel, ConfigDict

# The article body ends where the site's "latest articles" teaser starts.
END_HEADING = "כתבות אחרונות"
# Headings that open a site section (not article content): skip until the next real heading.
BOILERPLATE_SECTIONS = ("תפריט מהיר", "המומחה האובייקטיבי", "כתבות באותם נושאים", "מותגים מתחרים")
# Widgets injected mid-article; the article text after them continues the previous section.
# "סיכום AI" is a collapsible whose summary text is loaded by script, so only its label is here.
INLINE_BOILERPLATE = ("הצטרפו לוואטסאפ", "סיכום AI")
PHOTO_CREDIT = re.compile(r"^(צילום|צילומים)\s*:")
# FAQ questions sit one level below the FAQ section heading.
FAQ_QUESTION_LEVEL = 3

_SKIP_TAGS = frozenset(
    {"script", "style", "noscript", "svg", "img", "picture", "iframe", "nav", "form", "button"}
)
_SKIP_CLASS_PARTS = ("breadcrumbs", "social", "gallery", "tooltip", "tags", "share")
_HEADING_TAGS = {f"h{level}": level for level in range(1, 7)}
# Bidi marks, zero-width characters, BOM and soft hyphen: invisible, but they break matching.
_INVISIBLE = re.compile("[\u00ad\u200b-\u200f\u202a-\u202e\u2060-\u2064\u2066-\u2069\ufeff]")
_WHITESPACE = re.compile(r"\s+")


class BlockKind(StrEnum):
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    LIST_ITEM = "list_item"
    TABLE_ROW = "table_row"


class Block(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: BlockKind
    text: str
    level: int | None = None  # headings only


class Document(BaseModel):
    """One article after cleaning. Not persisted: it is rebuilt from the HTML cache each run."""

    model_config = ConfigDict(frozen=True)

    car_id: str
    title: str
    published: datetime | None
    source_url: str
    blocks: list[Block]

    def count(self, kind: BlockKind) -> int:
        return sum(1 for block in self.blocks if block.kind is kind)


def normalize_text(text: str) -> str:
    """Unescape leftover entities, drop invisible characters, collapse whitespace.

    The parser already decodes entities once; the second pass is a cheap guard
    against CMS text that arrives double-escaped (none of the eight pages does
    today). NFC keeps Hebrew and Latin letters intact while merging decomposed
    characters, so the same word always compares equal.
    """
    text = unicodedata.normalize("NFC", html.unescape(text))
    text = _INVISIBLE.sub("", text)
    return _WHITESPACE.sub(" ", text).strip()


def _text(node: PageElement) -> str:
    return normalize_text(node.get_text(""))


def _is_skipped(node: Tag) -> bool:
    if node.name in _SKIP_TAGS or node.has_attr("hidden"):
        return True
    classes = " ".join(node.get("class") or [])
    return any(part in classes for part in _SKIP_CLASS_PARTS)


def _starts_with_any(text: str, prefixes: tuple[str, ...]) -> bool:
    return any(text.startswith(prefix) for prefix in prefixes)


def _row_text(row: Tag) -> str:
    """A spec row as one line, "label: value | value", so the label stays next to its number."""
    header = row.find(attrs={"role": "rowheader"}) or row.find("th")
    cells = row.find_all(attrs={"role": "cell"}) or row.find_all("td")
    values = [value for value in (_text(cell) for cell in cells) if value]
    label = _text(header) if isinstance(header, Tag) else ""
    if label and values:
        return f"{label}: {' | '.join(values)}"
    return label or " | ".join(values)


def _is_row(node: Tag) -> bool:
    return node.name == "tr" or node.get("role") == "row"


def _is_label_value_item(node: Tag) -> bool:
    """A list item made of a label paragraph and value paragraph(s), as in the long-term stats."""
    return node.name == "li" and len(node.find_all("p")) >= 2 and not node.find("li")


def _label_value_text(node: Tag) -> str:
    texts = [text for text in (_text(p) for p in node.find_all("p")) if text]
    if len(texts) < 2:
        return " ".join(texts)
    return f"{texts[0]}: {' | '.join(texts[1:])}"


def drop_empty_headings(blocks: list[Block]) -> list[Block]:
    """Remove headings with no content under them (widgets whose content loads by script)."""
    kept: list[Block] = []
    for index, block in enumerate(blocks):
        if block.kind is BlockKind.HEADING:
            following = blocks[index + 1] if index + 1 < len(blocks) else None
            level = block.level or 0
            if following is None or (
                following.kind is BlockKind.HEADING and (following.level or 0) <= level
            ):
                continue
        kept.append(block)
    return kept


class _Walker:
    """Depth-first walk that emits blocks in reading order and stops at the end marker."""

    def __init__(self) -> None:
        self.blocks: list[Block] = []
        self.started = False  # nothing before the <h1> title is article content
        self.done = False
        self.in_boilerplate = False

    def emit(self, kind: BlockKind, text: str, level: int | None = None) -> None:
        if not text or not self.started or self.in_boilerplate:
            return
        if _starts_with_any(text, INLINE_BOILERPLATE) or PHOTO_CREDIT.match(text):
            return
        block = Block(kind=kind, text=text, level=level)
        if self.blocks and self.blocks[-1] == block:  # the subtitle is rendered twice
            return
        self.blocks.append(block)

    def heading(self, text: str, level: int) -> None:
        if level == 1:
            self.started = True
        if text.startswith(END_HEADING):
            self.done = True
            return
        if not text or _starts_with_any(text, INLINE_BOILERPLATE):
            return
        self.in_boilerplate = _starts_with_any(text, BOILERPLATE_SECTIONS)
        self.emit(BlockKind.HEADING, text, level)

    def walk(self, node: Tag) -> None:
        for child in node.children:
            if self.done:
                return
            if not isinstance(child, Tag) or _is_skipped(child):
                continue
            self.visit(child)

    def visit(self, node: Tag) -> None:
        name = node.name
        if name in _HEADING_TAGS:
            self.heading(_text(node), _HEADING_TAGS[name])
        elif name == "summary":
            self.heading(_text(node), FAQ_QUESTION_LEVEL)
        elif _is_row(node):
            self.emit(BlockKind.TABLE_ROW, _row_text(node))
        elif _is_label_value_item(node):
            self.emit(BlockKind.TABLE_ROW, _label_value_text(node))
        elif name == "li" and not node.find(["p", "li", "tr", "h2", "h3", "h4"]):
            self.emit(BlockKind.LIST_ITEM, _text(node))
        elif name == "p" and not node.find("p"):
            self.emit(BlockKind.PARAGRAPH, _text(node))
        else:
            self.walk(node)


def _iter_json_ld(value: Any) -> Iterator[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for nested in value.values():
            yield from _iter_json_ld(nested)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_json_ld(item)


def extract_published(soup: BeautifulSoup) -> datetime | None:
    """Publication date from JSON-LD, the only machine-readable date on these pages."""
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.get_text())
        except json.JSONDecodeError:
            continue
        for item in _iter_json_ld(data):
            value = item.get("datePublished")
            if isinstance(value, str):
                try:
                    return datetime.fromisoformat(value.replace("Z", "+00:00"))
                except ValueError:
                    continue
    return None


def _title(soup: BeautifulSoup, main: Tag) -> str:
    h1 = main.find("h1")
    if isinstance(h1, Tag) and _text(h1):
        return _text(h1)
    return normalize_text(soup.title.get_text()) if soup.title else ""


def clean_html(raw_html: str, *, car_id: str, source_url: str) -> Document:
    """Parse one article page. Raises ValueError when the page has no article body."""
    soup = BeautifulSoup(raw_html, "html.parser")
    for br in soup.find_all("br"):
        br.replace_with(NavigableString(" "))
    main = soup.find("main")
    if not isinstance(main, Tag):
        raise ValueError(f"{car_id}: no <main> element, page layout changed or not an article")
    walker = _Walker()
    walker.walk(main)
    if not walker.blocks:
        raise ValueError(f"{car_id}: no <h1> title or no text after it in <main>")
    return Document(
        car_id=car_id,
        title=_title(soup, main),
        published=extract_published(soup),
        source_url=source_url,
        blocks=drop_empty_headings(walker.blocks),
    )
