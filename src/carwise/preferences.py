"""Preference memory for one conversation: merging, validation, display, session.

Why validated in code: the understand call reports preferences, but the model
also sees earlier assistant turns, and a value it lifts from there (or invents)
must not become something the user "said". So an update is kept only when its
field is known and its value is grounded in the user's current message. Article
text never reaches the understand call, and the generate call has no preference
field, so neither can set a preference.

Why the session lives in memory only: preferences last for one conversation
(confirmed by the interviewer); there is no cross-session store to leak from.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import NamedTuple

from carwise.guardrails import HEBREW_PREFIXES, normalize, one_line
from carwise.llm.base import Message
from carwise.numbers import readings_of
from carwise.schemas import (
    Answer,
    Preference,
    PreferenceField,
    Preferences,
    PreferenceUpdate,
)

# A digit run with inner "," or "." groups ("150,000", "1,5") is one token, so a
# thousands comma does not split it; any other \w+ run is a word ("gv80" stays one).
_TOKEN = re.compile(r"\d+(?:[.,]\d+)*|\w+")
# Short function words carry no preference on their own ("עד", "לא", "של").
_MIN_CONTENT_CHARS = 3

# --- spoken numbers (CW-405) -----------------------------------------------------------
# Why here and not in carwise.numbers: the numeric post-check reads digits only, on
# purpose (an answer's number must match the article's digits). Grounding asks
# "did the user say this?", and a user writes "חמישה" where the understand call
# writes "5". So number words are read for grounding only.
_UNITS = {
    "אחד": 1, "אחת": 1,
    "שניים": 2, "שתיים": 2, "שני": 2, "שתי": 2,
    "שלוש": 3, "שלושה": 3, "שלושת": 3,
    "ארבע": 4, "ארבעה": 4, "ארבעת": 4,
    "חמש": 5, "חמישה": 5, "חמשת": 5,
    "שש": 6, "שישה": 6, "ששת": 6,
    "שבע": 7, "שבעה": 7, "שבעת": 7,
    "שמונה": 8, "שמונת": 8,
    "תשע": 9, "תשעה": 9, "תשעת": 9,
    "עשר": 10, "עשרה": 10, "עשרת": 10,
    "עשרים": 20, "שלושים": 30, "ארבעים": 40, "חמישים": 50,
    "שישים": 60, "שבעים": 70, "שמונים": 80, "תשעים": 90,
    "מאה": 100, "מאתיים": 200,
}  # fmt: skip
# "שנים" is left out: it means "years" far more often than "two".
_HUNDREDS_OF = "מאות"  # "שלוש מאות" is 300
_SCALES = {"אלף": 1000, "אלפים": 1000, "מיליון": 1_000_000}
_TWO_THOUSAND = "אלפיים"
_NUMBER_WORDS = {*_UNITS, _HUNDREDS_OF, *_SCALES, _TWO_THOUSAND}
_MAX_NUMBER_PREFIXES = 2


def _number_word(token: str, *, inside: bool) -> str | None:
    """The number word in a token, past its Hebrew prefixes ("לחמישה", "וחמישים").

    Inside a number only the conjunction "ו" joins the next word ("מאה וחמישים");
    a word that starts a number may carry up to two prefixes ("בשלושה", "ולשלושה")."""
    allowed = "ו" if inside else HEBREW_PREFIXES
    for cut in range(1 if inside else _MAX_NUMBER_PREFIXES, -1, -1):
        head, rest = token[:cut], token[cut:]
        if rest in _NUMBER_WORDS and all(c in allowed for c in head):
            return rest
    return None


class _Number:
    """One number read word by word: "מאה וחמישים אלף" is 150000.

    Additive words must fall in order of magnitude (hundreds, tens, units), so
    "חמישה שבעה" is two numbers. Digits start a number and only a scale word may
    follow them ("150 אלף"); "חמש עשרה" is 15."""

    _DIGITS = Decimal(0)  # the "last order" after digits: no additive word fits below it

    def __init__(self, digits: Decimal | None = None) -> None:
        self.total = Decimal(0)  # groups already closed by a scale word
        self.group = digits or Decimal(0)
        self.last = self._DIGITS if digits is not None else Decimal(10**12)

    def add(self, word: str) -> bool:
        """Take one more number word; False when it cannot continue this number."""
        if word in _SCALES:
            self.total += (self.group or 1) * _SCALES[word]  # "אלף" alone is 1000
            self.group, self.last = Decimal(0), Decimal(_SCALES[word])
        elif word == _TWO_THOUSAND:
            if self.group or self.total:
                return False
            self.total, self.last = Decimal(2000), Decimal(1000)
        elif word == _HUNDREDS_OF:
            if self.last != 1 or not 0 < self.group < 10:
                return False
            self.group, self.last = self.group * 100, Decimal(100)
        else:
            value = Decimal(_UNITS[word])
            if value == 10 and self.last == 1 and 0 < self.group % 100 < 10:
                self.group, self.last = self.group + 10, Decimal(10)  # "חמש עשרה"
            else:
                order = Decimal(100 if value >= 100 else 10 if value >= 10 else 1)
                if order >= self.last:
                    return False
                self.group, self.last = self.group + value, order
        return True

    def canonical(self) -> str:
        """One spelling per value: "150000", "1.5"."""
        return format((self.total + self.group).normalize(), "f")


def _read_tokens(text: str) -> list[str]:
    """Normalized tokens, with each number (digits or words, scale included) as one
    canonical token.

    Why on both sides: "5" in a value and "חמישה" in the message, or "150 אלף" and
    "150,000", become the same token, and a number is matched as a whole value."""
    out: list[str] = []
    number: _Number | None = None
    for token in _TOKEN.findall(normalize(text)):
        if token[0].isdigit():
            if number is not None:
                out.append(number.canonical())
            # A decimal comma ("1,5") or a thousands group ("150,000"): the first reading.
            number = _Number(readings_of(token)[0][0])
            continue
        if number is not None:
            word = _number_word(token, inside=True)
            if word is not None and number.add(word):
                continue
            out.append(number.canonical())
            number = None
        word = _number_word(token, inside=False)
        fresh = _Number() if word is not None else None
        if fresh is not None and word is not None and fresh.add(word):
            number = fresh
        else:
            out.append(token)
    if number is not None:
        out.append(number.canonical())
    return out


def _is_number(token: str) -> bool:
    return token[0].isdigit()


def _content_tokens(text: str) -> list[str]:
    return [t for t in _read_tokens(text) if _is_number(t) or len(t) >= _MIN_CONTENT_CHARS]


def _stems(token: str) -> list[str]:
    """The token, then the token without up to three Hebrew one-letter prefixes."""
    stems = [token]
    for _ in range(3):
        last = stems[-1]
        if last[0] not in HEBREW_PREFIXES or len(last) <= _MIN_CONTENT_CHARS:
            break
        stems.append(last[1:])
    return stems


def grounded_in(value: str, message: str) -> bool:
    """True when at least half of the value's content words occur in the message.

    Why this test: the understand prompt asks for "a short value in the user's
    words", so a real update shares words with the message, while a value taken
    from an assistant turn or made up usually does not. Substring matching on
    normalized text tolerates Hebrew prefixes and suffixes ("חשמלי" in "חשמלית").
    Numbers are compared by value and as whole numbers, in digits or in words
    ("5" and "חמישה", "150 אלף" and "150,000"), so "5" is not found in "150".
    """
    tokens = _content_tokens(value)
    if not tokens:
        return False
    message_tokens = _read_tokens(message)
    numbers = {token for token in message_tokens if _is_number(token)}
    haystack = " ".join(token for token in message_tokens if not _is_number(token))
    found = sum(
        token in numbers if _is_number(token) else any(s in haystack for s in _stems(token))
        for token in tokens
    )
    return found * 2 >= len(tokens)


class Merged(NamedTuple):
    preferences: Preferences
    updated: list[str]  # field names set or changed this turn
    flags: list[str]
    # Field names whose value was not grounded in the user's message. Names only:
    # the values are the model's guess at the user's words, so they stay out of logs.
    rejected: list[str]


def merge(
    current: Preferences, updates: list[PreferenceUpdate], message: str, max_chars: int
) -> Merged:
    """Apply this turn's updates; return the new profile, the fields set, flags and
    the fields rejected as not grounded.

    A later update on the same field replaces the earlier one, including within
    the same turn. Rejected updates leave the profile untouched and add a flag.
    An update equal to the stored value is a repeat, not a change: it is skipped
    without a flag and is not reported as updated.
    """
    known = {item.value for item in PreferenceField}
    changes: dict[str, Preference] = {}
    flags: list[str] = []
    rejected: list[str] = []
    for update in updates:
        name = update.field.strip()
        value = " ".join(update.value.split())
        if name not in known:
            flags.append("preference_unknown_field")
            continue
        if not value:
            continue
        stored = getattr(current, name)
        if stored is not None and normalize(stored.value) == normalize(value):
            # The model re-sent an earlier preference from the history window: it is
            # already grounded in the message it came from, so keep that source.
            continue
        if not grounded_in(value, message):
            flags.append("preference_not_from_user")
            rejected.append(name)
            continue
        if len(value) > max_chars:
            value = value[:max_chars].rstrip()
            flags.append("preference_value_truncated")
        changes[name] = Preference(value=value, source=message)
    updated = list(changes)
    return Merged(
        current.model_copy(update=changes),
        updated,
        list(dict.fromkeys(flags)),
        list(dict.fromkeys(rejected)),
    )


# --- display (Hebrew, gender-neutral) -------------------------------------------------
FIELD_LABELS = {
    PreferenceField.BUDGET: "תקציב",
    PreferenceField.POWERTRAIN: "הנעה",
    PreferenceField.PRIMARY_USE: "שימוש עיקרי",
    PreferenceField.PASSENGERS: "נוסעים",
    PreferenceField.PRIORITIES: "מה חשוב",
    PreferenceField.DISLIKES: "מה לא מתאים",
}
EMPTY_PREFERENCES = (
    "עדיין לא נאמרו העדפות בשיחה הזאת. אפשר לספר על תקציב, סוג הנעה, שימוש עיקרי, "
    "מספר נוסעים, מה חשוב ומה לא מתאים."
)
RESET_REPLY = "השיחה וההעדפות נמחקו. אפשר להתחיל מחדש."


def describe(preferences: Preferences) -> str:
    """The /prefs text: each preference with the message it came from."""
    if not preferences.items():
        return EMPTY_PREFERENCES
    lines = ["ההעדפות בשיחה הזאת:"]
    for name, pref in preferences.items():
        lines.append(f'- {FIELD_LABELS[name]}: {pref.value} (מתוך: "{pref.source}")')
    return "\n".join(lines)


def prompt_block(preferences: Preferences) -> str:
    """Preferences for the generate call, labelled so the model can name them.

    Each value is the user's words, so it is kept to one escaped line (CW-205)."""
    return "\n".join(
        f"- {name.value}: {one_line(pref.value)}" for name, pref in preferences.items()
    )


# --- session ---------------------------------------------------------------------------
@dataclass
class Session:
    """One conversation's memory: the history window and the preference profile.

    The pipeline itself is stateless; callers (CLI, UI, eval) hold a Session, so a
    new Session is a new conversation with nothing carried over.
    """

    history_window: int
    history: list[Message] = field(default_factory=list)
    preferences: Preferences = field(default_factory=Preferences)

    def record(self, message: str, answer: Answer) -> None:
        self.history += [
            {"role": "user", "content": message},
            {"role": "assistant", "content": answer.text},
        ]
        self.history = self.history[-self.history_window :]
        self.preferences = answer.preferences

    def reset(self) -> None:
        self.history = []
        self.preferences = Preferences()
