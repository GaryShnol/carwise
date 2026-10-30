import random
import re
from datetime import UTC, date, datetime

import pytest

from carwise.config import ChunkingConfig
from carwise.guardrails import section_label
from carwise.ingest.chunk import chunk_document, covers_document, split_block
from carwise.ingest.clean import Block, BlockKind, Document
from carwise.registry import Car
from carwise.schemas import Chunk

# Synthetic documents only: the repository is public and the articles are not ours.
CAR = Car(
    id="xr5",
    display_name="רכב בדיקה XR5",
    aliases_he=[],
    aliases_latin=["XR5"],
    body_type=None,
    body_type_quote=None,
    powertrain=None,
    powertrain_quote=None,
    url="https://example.test/articles/xr5/",
    slug="xr5",
)
LIMITS = ChunkingConfig(min_chars=60, max_chars=200, embed_section_chars=60, spec_header=False)
TITLE = "כותרת המבחן"


def h(text: str, level: int = 2) -> Block:
    return Block(kind=BlockKind.HEADING, text=text, level=level)


def p(text: str) -> Block:
    return Block(kind=BlockKind.PARAGRAPH, text=text)


def li(text: str) -> Block:
    return Block(kind=BlockKind.LIST_ITEM, text=text)


def tr(text: str) -> Block:
    return Block(kind=BlockKind.TABLE_ROW, text=text)


def para(tag: str, length: int) -> str:
    """A paragraph of exactly `length` characters that is easy to find again."""
    return (f"{tag} " + "מילה " * length)[:length].strip().ljust(length, "א")


def doc(*blocks: Block, title: str = TITLE) -> Document:
    return Document(
        car_id=CAR.id,
        title=title,
        published=datetime(2026, 1, 13, 11, 0, tzinfo=UTC),
        source_url=CAR.url,
        blocks=[h(title, 1), *blocks],
    )


def chunk(document: Document, limits: ChunkingConfig = LIMITS) -> list[Chunk]:
    return chunk_document(document, CAR, limits)


def test_sections_follow_headings_in_order() -> None:
    chunks = chunk(
        doc(p(para("פתיחה", 80)), h("מנוע"), p(para("מנוע", 90)), h("מחיר"), p(para("מחיר", 90)))
    )
    assert [c.section for c in chunks] == [TITLE, "מנוע", "מחיר"]
    assert chunks[0].text.startswith(TITLE)  # text before the first subheading
    assert chunks[1].text.startswith("מנוע\nמנוע ")  # heading line, then its body


def test_every_chunk_has_all_metadata() -> None:
    chunks = chunk(doc(p(para("א", 100)), h("ב"), p(para("ב", 100))))
    for index, c in enumerate(chunks):
        assert c.chunk_id == f"xr5:{index:03d}"
        assert c.car == "xr5"
        assert c.car_name == CAR.display_name
        assert c.source_url == CAR.url
        assert c.published == date(2026, 1, 13)
        assert c.section and c.text and c.embed_text


def test_published_may_be_missing() -> None:
    document = doc(p(para("א", 100))).model_copy(update={"published": None})
    assert chunk(document)[0].published is None


def test_embed_text_names_car_and_section_but_text_does_not() -> None:
    c = chunk(doc(h("מנוע"), p(para("מנוע", 100))))[0]
    label = section_label(c.section, LIMITS.embed_section_chars)  # " / " reads as ", "
    assert c.embed_text == f"{CAR.display_name} — {label}\n{c.text}"
    assert CAR.display_name not in c.text


def test_embedded_header_uses_the_short_label_and_metadata_keeps_the_full_section() -> None:
    long_heading = "שאלה ארוכה מאוד על הטווח " * 6
    c = chunk(doc(h(long_heading.strip()), p(para("טווח", 100))))[0]
    header = c.embed_text.split("\n", 1)[0]
    assert c.section.endswith(long_heading.strip())  # the full name stays for citations
    assert len(header) <= len(CAR.display_name) + len(" — ") + LIMITS.embed_section_chars
    assert header.endswith("…")


def test_short_section_merges_into_previous_with_both_names() -> None:
    chunks = chunk(doc(p(para("פתיחה", 100)), h("מפרט"), tr("מחיר: 100"), tr("כוח: 200")))
    assert len(chunks) == 1
    assert chunks[0].section == f"{TITLE} / מפרט"
    assert chunks[0].text.endswith("מחיר: 100\nכוח: 200")


def test_short_first_section_merges_into_next() -> None:
    chunks = chunk(doc(p("קצר"), h("מנוע"), p(para("מנוע", 120)), h("מחיר"), p(para("מחיר", 150))))
    assert [c.section for c in chunks] == [f"{TITLE} / מנוע", "מחיר"]


def test_short_section_stays_alone_when_no_neighbor_has_room() -> None:
    chunks = chunk(
        doc(p(para("א", 180)), h("קצר"), p("שורה"), h("ג"), p(para("ג", 190))),
        ChunkingConfig(min_chars=60, max_chars=200, embed_section_chars=60, spec_header=False),
    )
    assert [c.section for c in chunks] == [TITLE, "קצר", "ג"]


def test_long_section_splits_at_block_boundaries() -> None:
    blocks = [p(para(f"פסקה{i}", 70)) for i in range(6)]
    chunks = chunk(doc(h("נהיגה"), *blocks))
    texts = [b.text for b in blocks]
    assert len(chunks) > 1
    assert all(len(c.text) <= LIMITS.max_chars for c in chunks)
    assert {c.section for c in chunks} == {f"{TITLE} / נהיגה"}  # heading-only title carried on
    for c in chunks:  # every line is a whole block
        assert all(line in texts or line in (TITLE, "נהיגה") for line in c.text.split("\n"))


def test_split_is_even_rather_than_leaving_a_tiny_tail() -> None:
    blocks = [p(para(f"פסקה{i}", 95)) for i in range(3)]  # greedy would give 191 + 95
    sizes = [len(c.text) for c in chunk(doc(*blocks))]
    assert all(size >= LIMITS.min_chars for size in sizes)


def test_oversize_block_splits_at_sentence_ends() -> None:
    sentences = [f"משפט מספר {i} שיש בו כמה מילים בעברית." for i in range(12)]
    parts = split_block(" ".join(sentences), 120)
    assert len(parts) > 1
    assert all(len(part) <= 120 and part.endswith(".") for part in parts)
    assert " ".join(parts) == " ".join(sentences)


def test_sentence_longer_than_the_limit_is_cut_at_spaces() -> None:
    parts = split_block(" ".join(["מילה"] * 100), 120)
    assert len(parts) > 1
    assert all(len(part) <= 120 for part in parts)
    assert " ".join(parts) == " ".join(["מילה"] * 100)


def test_faq_question_and_answer_stay_together() -> None:
    faq = [h("שאלות נפוצות"), h("מה הטווח?", 3), p("הטווח הוא 400 ק״מ."), h("מה המחיר?", 3)]
    chunks = chunk(doc(p(para("פתיחה", 190)), *faq, p("המחיר 150 אלף.")))
    for question, answer in (("מה הטווח?", "הטווח הוא"), ("מה המחיר?", "המחיר 150")):
        holding = [c for c in chunks if question in c.text]
        assert len(holding) == 1 and answer in holding[0].text
    assert chunks[-1].section.startswith("שאלות נפוצות / מה הטווח?")


def test_pros_and_cons_stay_with_their_headings() -> None:
    pros_cons = [h("יתרונות", 3), li("שקט"), li("חסכוני"), h("חסרונות", 3), li("יקר")]
    chunks = chunk(doc(p(para("סיכום", 180)), *pros_cons))  # no room behind
    assert chunks[-1].text.split("\n")[-5:] == [b.text for b in pros_cons]
    assert chunks[-1].section == "יתרונות / חסרונות"


def test_report_without_subheadings_uses_the_title_as_section() -> None:
    chunks = chunk(doc(*[p(para(f"דוח{i}", 90)) for i in range(8)], title="דוח ארוך טווח"))
    assert len(chunks) > 1
    assert {c.section for c in chunks} == {"דוח ארוך טווח"}


def test_no_empty_chunks() -> None:
    chunks = chunk(doc(h("ריק"), h("גם ריק", 3), p("x"), h("סוף"), p(para("סוף", 50))))
    assert chunks and all(c.text.strip() for c in chunks)


def test_ids_are_deterministic() -> None:
    document = doc(*[p(para(f"פ{i}", 70)) for i in range(10)])
    first, second = chunk(document), chunk(document)
    assert first == second
    assert len({c.chunk_id for c in first}) == len(first)


def test_rejects_a_document_from_another_car() -> None:
    other = doc(p("טקסט")).model_copy(update={"car_id": "other"})
    with pytest.raises(ValueError, match="registry car"):
        chunk(other)


def _random_document(rng: random.Random) -> Document:
    words = ["מנוע", "טווח", "מחיר", "נוחות", "XR5", "200", "כ״ס", "קמ״ש"]
    blocks: list[Block] = []
    for index in range(rng.randint(0, 40)):
        roll = rng.random()
        if roll < 0.2:
            blocks.append(h(f"כותרת {index}", rng.choice([2, 2, 3])))
            continue
        sentences = [
            " ".join(rng.choice(words) for _ in range(rng.randint(1, 30))) + rng.choice(".!?")
            for _ in range(rng.randint(1, 12))
        ]
        kind = rng.choice([p, p, p, li, tr])
        blocks.append(kind(f"{index} " + " ".join(sentences)))
    return doc(*blocks)


@pytest.mark.parametrize("seed", range(200))
def test_property_nothing_lost_duplicated_or_oversize(seed: int) -> None:
    rng = random.Random(seed)
    limits = ChunkingConfig(
        min_chars=rng.randint(20, 120),
        max_chars=rng.randint(120, 400),
        embed_section_chars=60,
        spec_header=rng.random() < 0.5,  # the header never changes what the text covers
    )
    document = _random_document(rng)
    chunks = chunk(document, limits)
    assert covers_document(document, chunks)
    assert all(0 < len(c.text) <= limits.max_chars for c in chunks)
    assert all(re.fullmatch(r"xr5:\d{3}", c.chunk_id) for c in chunks)
    for index, c in enumerate(chunks):  # short only when no neighbor has room
        if len(c.text) < limits.min_chars and len(chunks) > 1:
            neighbors = chunks[max(index - 1, 0) : index] + chunks[index + 1 : index + 2]
            assert all(len(n.text) + 1 + len(c.text) > limits.max_chars for n in neighbors)
