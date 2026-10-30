from datetime import UTC, datetime
from pathlib import Path

import pytest

from carwise.ingest.clean import (
    Block,
    BlockKind,
    clean_html,
    drop_empty_headings,
    normalize_text,
)

# Synthetic page that mimics the site's structure; no real article text.
FIXTURE = Path(__file__).parent / "fixtures" / "article.html"
URL = "https://example.test/articles/xr5/"

H, P, LI, TR = BlockKind.HEADING, BlockKind.PARAGRAPH, BlockKind.LIST_ITEM, BlockKind.TABLE_ROW


@pytest.fixture(scope="module")
def blocks() -> list[Block]:
    return clean_html(FIXTURE.read_text(encoding="utf-8"), car_id="xr5", source_url=URL).blocks


def test_document_metadata() -> None:
    doc = clean_html(FIXTURE.read_text(encoding="utf-8"), car_id="xr5", source_url=URL)
    assert doc.car_id == "xr5"
    assert doc.source_url == URL
    assert doc.title == "רכב בדיקה XR5 – מבחן דרכים"
    assert doc.published == datetime(2026, 1, 13, 11, 13, 55, tzinfo=UTC)


def test_blocks_in_reading_order(blocks: list[Block]) -> None:
    assert [(b.kind, b.text) for b in blocks] == [
        (H, "רכב בדיקה XR5 – מבחן דרכים"),
        (P, "שורת משנה סינתטית על רכב הבדיקה"),
        (P, 'פסקת פתיחה עם שם XR5 ו"מרכאות".'),
        (H, "הרכב הנבחן"),
        (TR, "מחיר: ₪123,456"),
        (TR, 'טווח בפועל (ק"מ): 400'),
        (H, "מה המנוע?"),
        (P, 'מנוע בדיקה עם 200 כ"ס ושורה שנייה.'),
        (TR, "תאוצה: 7.5 | שניות"),
        (H, "יתרונות"),
        (LI, "יתרון ראשון"),
        (LI, "יתרון שני"),
        (TR, 'מרחק חודשי: 1,234 ק"מ'),
        (H, "שאלות ותשובות"),
        (H, "מה המחיר?"),
        (P, "תשובה סינתטית."),
    ]


def test_heading_levels_are_kept(blocks: list[Block]) -> None:
    levels = {b.text: b.level for b in blocks if b.kind is H}
    assert levels["רכב בדיקה XR5 – מבחן דרכים"] == 1
    assert levels["הרכב הנבחן"] == 2
    assert levels["יתרונות"] == 3
    assert levels["מה המחיר?"] == 3  # FAQ question under its h2
    assert all(b.level is None for b in blocks if b.kind is not H)


def test_boilerplate_and_page_chrome_are_dropped(blocks: list[Block]) -> None:
    text = " ".join(b.text for b in blocks)
    for unwanted in (
        "תפריט ראשי",  # site navigation
        "בית",  # breadcrumbs
        "שתף",  # share buttons
        "סיכום AI",  # script-loaded widget
        "הצטרפו לוואטסאפ",  # inline prompt, heading and paragraph
        "צילום:",  # photo credits and gallery
        "הסבר שלא אמור להופיע",  # tooltip
        "מותגים מתחרים",
        "טקסט פרסומי",  # content under a boilerplate section heading
        "השוואת מתחרים",  # heading with nothing under it
        "תגית",
        "כתבות אחרונות",
        "כתבה אחרת",
        "טקסט אחרי סוף הכתבה",
        "כותרת תחתונה",
    ):
        assert unwanted not in text, unwanted


def test_no_empty_or_duplicate_neighbour_blocks(blocks: list[Block]) -> None:
    assert all(b.text for b in blocks)
    assert all(a != b for a, b in zip(blocks, blocks[1:], strict=False))


def test_normalize_text() -> None:
    assert normalize_text("  שלום\u200b\u200f\u00a0 עולם\n\t") == "שלום עולם"
    assert normalize_text("&quot;GV80&quot; &amp;") == '"GV80" &'
    assert normalize_text("Link & Co 01") == "Link & Co 01"


def test_drop_empty_headings_keeps_parents_of_subheadings() -> None:
    blocks = [
        Block(kind=H, text="parent", level=2),
        Block(kind=H, text="child", level=3),
        Block(kind=P, text="body"),
        Block(kind=H, text="empty", level=2),
        Block(kind=H, text="next", level=2),
        Block(kind=P, text="body"),
        Block(kind=H, text="trailing", level=2),
    ]
    assert [b.text for b in drop_empty_headings(blocks)] == [
        "parent",
        "child",
        "body",
        "next",
        "body",
    ]


def test_missing_published_date_is_none() -> None:
    page = "<main><h1>כותרת</h1><p>טקסט</p></main>"
    assert clean_html(page, car_id="x", source_url=URL).published is None


def test_page_without_main_is_rejected() -> None:
    with pytest.raises(ValueError, match="<main>"):
        clean_html("<html><body><p>טקסט</p></body></html>", car_id="x", source_url=URL)


def test_page_without_title_is_rejected() -> None:
    with pytest.raises(ValueError, match="h1"):
        clean_html("<main><p>טקסט</p></main>", car_id="x", source_url=URL)
