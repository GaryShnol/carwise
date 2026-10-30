"""Section names as the user sees them; Citation keeps the full name (CW-203)."""

from pathlib import Path

from app.chat import format_answer
from carwise.config import load_settings
from carwise.guardrails import ELLIPSIS, MERGED_SECTION_SEPARATOR, section_label, unverified_reply
from carwise.ingest.chunk import SECTION_SEPARATOR
from carwise.schemas import Citation
from carwise.telemetry import TurnLogger
from tests.test_pipeline import REGISTRY, generation, make, understanding
from tests.test_postcheck import hit

MAX = load_settings().display.max_section_chars
# Shaped like the real merged FAQ sections (mg_s6:011 is 287 characters long).
LONG = (
    "מה הטווח האמיתי של MG S6 בנסיעה יומיומית? / כמה זמן לוקח להטעין את הסוללה? / "
    "כמה עולה הרכב ומה כולל האבזור?"
)


def test_separator_matches_the_chunker() -> None:
    assert MERGED_SECTION_SEPARATOR == SECTION_SEPARATOR


def test_short_section_is_unchanged() -> None:
    assert section_label("מחיר", MAX) == "מחיר"


def test_merged_headings_read_as_a_list() -> None:
    assert section_label("יתרונות / חסרונות", MAX) == "יתרונות, חסרונות"


def test_long_section_is_cut_at_a_word_boundary_with_an_ellipsis() -> None:
    label = section_label(LONG, MAX)
    assert len(label) <= MAX and label.endswith(ELLIPSIS)
    assert " / " not in label
    kept = label.removesuffix(ELLIPSIS)
    full = LONG.replace(" / ", ", ")
    assert full.startswith(kept) and full[len(kept)] in " ,"  # never a broken word
    assert not kept.endswith(",")


def test_label_of_exactly_the_limit_is_not_cut() -> None:
    exact = "א" * (MAX - 6) + " בבבבב"
    assert section_label(exact, MAX) == exact


def test_one_long_word_is_hard_cut() -> None:
    label = section_label("א" * (MAX + 20), MAX)
    assert len(label) == MAX and label.endswith(ELLIPSIS)


def test_cli_shows_the_short_label_and_citation_keeps_the_full_name(tmp_path: Path) -> None:
    logger = TurnLogger(tmp_path, profile="dev", models={"understand": "a", "generate": "b"})
    pipeline, _, _ = make([understanding(cars=["mg_s6"]), generation()], logger=logger)
    answer = pipeline.ask("מה הטווח בפועל של MG S6?", [])
    long_source = answer.sources[0].model_copy(update={"section": LONG})
    answer = answer.model_copy(update={"sources": [long_source]})

    printed = format_answer(answer, show_cost=False, max_section_chars=MAX)
    assert section_label(LONG, MAX) in printed and LONG not in printed
    assert isinstance(answer.sources[0], Citation) and answer.sources[0].section == LONG


def test_fallback_reply_uses_short_labels() -> None:
    long_hit = hit("mg_s6", "טקסט")
    long_hit = long_hit.model_copy(
        update={"chunk": long_hit.chunk.model_copy(update={"section": LONG})}
    )
    text = unverified_reply(REGISTRY, [long_hit], 3, MAX)
    assert section_label(LONG, MAX) in text and " / " not in text
