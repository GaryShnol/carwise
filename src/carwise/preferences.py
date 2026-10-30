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

from carwise.guardrails import HEBREW_PREFIXES, normalize
from carwise.llm.base import Message
from carwise.schemas import (
    Answer,
    Preference,
    PreferenceField,
    Preferences,
    PreferenceUpdate,
)

_TOKEN = re.compile(r"\w+")
# Short function words carry no preference on their own ("עד", "לא", "של").
_MIN_CONTENT_CHARS = 3


def _content_tokens(text: str) -> list[str]:
    tokens = _TOKEN.findall(normalize(text))
    return [t for t in tokens if any(c.isdigit() for c in t) or len(t) >= _MIN_CONTENT_CHARS]


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
    """
    tokens = _content_tokens(value)
    if not tokens:
        return False
    haystack = normalize(message)
    found = sum(any(stem in haystack for stem in _stems(token)) for token in tokens)
    return found * 2 >= len(tokens)


def merge(
    current: Preferences, updates: list[PreferenceUpdate], message: str, max_chars: int
) -> tuple[Preferences, list[str], list[str]]:
    """Apply this turn's updates; return the new profile, the fields set, and flags.

    A later update on the same field replaces the earlier one, including within
    the same turn. Rejected updates leave the profile untouched and add a flag.
    An update equal to the stored value is a repeat, not a change: it is skipped
    without a flag and is not reported as updated.
    """
    known = {item.value for item in PreferenceField}
    changes: dict[str, Preference] = {}
    flags: list[str] = []
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
            continue
        if len(value) > max_chars:
            value = value[:max_chars].rstrip()
            flags.append("preference_value_truncated")
        changes[name] = Preference(value=value, source=message)
    updated = list(changes)
    return current.model_copy(update=changes), updated, list(dict.fromkeys(flags))


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
    """Preferences for the generate call, labelled so the model can name them."""
    return "\n".join(f"- {name.value}: {pref.value}" for name, pref in preferences.items())


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
