"""Reading numbers out of Hebrew car-review text, for the numeric post-check (CW-206).

Why a reading has a unit: an answer may round what the article says ("כ-179 אלף"
for "₪178,888", "3.8" for "3.79"), but must not add precision the article does
not have. So every number is read as a value plus the smallest unit the writer
expressed (1 for "400", 0.1 for "3.8", 1000 for "178 אלף"), and a source backs
an answer number when rounding or truncating it to that unit gives the answer's
value: 178,888 backs "178 אלף" and "179 אלף", never "180 אלף".

Why some readings are ambiguous: "1.234" may be a decimal or a thousands group,
and the text does not say which. Such a number gets every plausible reading;
the check accepts it when any reading is backed, which errs toward not flagging.

Only digits are read. Number words ("שלושה", "אלף" alone) and ordinal words
("השלישי") are not numbers here, so they are never checked.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal

# A digit run with inner "," or "." groups ("178,888", "3.8", "1,234.5"). No
# Latin letter or digit right before it: "GV80", "S6", "RS3", "i20" are model
# codes. A range ("420-440", "420–440") or a tyre size ("265/30-19") is read
# as its separate numbers, because "-" and "/" are not part of a number here.
_NUMBER = re.compile(r"(?<![A-Za-z\d])\d+(?:[.,]\d+)*")
# Hebrew scale words right after the number: "178 אלף", "1.5 מיליון".
_SCALE = re.compile(r"\s*(אלף|אלפים|מיליון)(?![א-ת])")
_SCALES = {"אלף": Decimal(1000), "אלפים": Decimal(1000), "מיליון": Decimal(1_000_000)}
# "1." or "2)" opening a line is a list marker, not a claim.
_LIST_MARKER = re.compile(r"^[ \t]*\d{1,2}[.)]\s", re.MULTILINE)


@dataclass(frozen=True)
class Reading:
    value: Decimal
    unit: Decimal  # the precision the writer expressed

    def backed_by(self, source: Decimal) -> bool:
        """Rounding (half up) or truncating the source to this unit gives this value."""
        return self.value - self.unit / 2 <= source < self.value + self.unit


@dataclass(frozen=True)
class Number:
    """One number as written, with every reading the text allows."""

    text: str  # as written in the text, scale word included ("178 אלף")
    token: str  # the digits alone ("178")
    readings: tuple[Reading, ...]


def _plain(digits: str) -> tuple[Decimal, Decimal]:
    """A value and its unit from digits with at most one "." decimal point."""
    whole, _, fraction = digits.partition(".")
    return Decimal(digits), Decimal(1).scaleb(-len(fraction)) if fraction else Decimal(1)


def readings_of(token: str) -> list[tuple[Decimal, Decimal]]:
    """Every plausible (value, unit) of one digit token, before any scale word."""
    commas, dots = token.count(","), token.count(".")
    groups = re.split(r"[.,]", token)
    thousands = len(groups) > 1 and all(len(group) == 3 for group in groups[1:])
    if commas and dots:  # "1,234.5": comma thousands, point decimal
        return [_plain(token.replace(",", ""))]
    if commas:
        if thousands:  # "178,888", "1,060"
            return [_plain(token.replace(",", ""))]
        if commas == 1:  # "3,8", "545,00": a decimal comma, never a thousands group
            return [_plain(token.replace(",", "."))]
        return [_plain(group) for group in groups]
    if dots == 1:  # "3.8"; "1.234" may also be a thousands group
        found = [_plain(token)]
        if thousands:
            found.append(_plain(token.replace(".", "")))
        return found
    if dots:  # "1.234.567" thousands, or something like a version: each part
        return [_plain(token.replace(".", ""))] if thousands else [_plain(g) for g in groups]
    return [_plain(token)]


def find_numbers(text: str, *, list_markers: bool = False) -> list[Number]:
    """The numbers in a text, in order, skipping model codes and (unless asked) list markers."""
    markers = set() if list_markers else {m.start() for m in _LIST_MARKER.finditer(text)}
    found: list[Number] = []
    for match in _NUMBER.finditer(text):
        token = match.group()
        line_start = text.rfind("\n", 0, match.start()) + 1
        if line_start in markers and not text[line_start : match.start()].strip():
            continue
        if len(token) > 1 and token.startswith("0") and token.isdigit():
            continue  # "01" is a model name (Lynk & Co 01), never a quantity
        scale_match = _SCALE.match(text, match.end())
        scale = _SCALES[scale_match.group(1)] if scale_match else Decimal(1)
        written = text[match.start() : scale_match.end()] if scale_match else token
        readings = tuple(Reading(value * scale, unit * scale) for value, unit in readings_of(token))
        found.append(Number(written.strip(), token, readings))
    return found


def source_values(texts: Iterable[str]) -> set[Decimal]:
    """Every value the sources state, under every reading, plus the bare number
    before a scale word ("178" of "178 אלף"): generous on purpose, so a source
    number the parser reads one way can still back an answer that wrote it another.
    List markers count too: an answer may quote a numbered heading ("3. מה הטווח?")."""
    values: set[Decimal] = set()
    for text in texts:
        for number in find_numbers(text, list_markers=True):
            values.update(reading.value for reading in number.readings)
            values.update(value for value, _ in readings_of(number.token))
    return values
