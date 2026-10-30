"""Deterministic checks around the two LLM calls, and the fixed replies they lead to.

Why code and not prompt instructions: a prompt asks, code enforces (CLAUDE.md
section 2, "do not trust the model, bound it"). Everything here is plain
string work: no model, no network, cheap enough to run on every turn.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable

from carwise.registry import Registry

# Hebrew attaches up to a few one-letter prefixes to a name: "לאודי", "ובטויוטה".
_HEBREW_PREFIXES = "והבכלמש"
_MAX_PREFIXES = 3
# Geresh and gershayim have look-alikes (׳ ’ ` and ״ ”); one form makes names comparable.
_APOSTROPHES = str.maketrans({"׳": "'", "’": "'", "`": "'", "״": '"', "“": '"', "”": '"'})

# --- answer text guard (used by schemas.Generation) -------------------------------
# A snake_case key followed by "=" or ":" ("mentioned_in_context=false", seen once in
# the CW-104 spike), the reply's own field names, or an internal chunk id ("mg_s6:007").
_FIELD_ASSIGNMENT = re.compile(r"\b[a-z]+(?:_[a-z]+)+\s*[=:]")
_OWN_FIELD_NAMES = re.compile(r"\b(?:used_chunk_ids|answer)\b")
_CHUNK_ID = re.compile(r"\b[a-z0-9]+(?:_[a-z0-9]+)*:\d{3}\b")
_HEBREW_LETTER = re.compile("[א-ת]")


def answer_text_problem(text: str) -> str | None:
    """Why an answer text is unfit to show, or None when it is fine.

    The message is sent back to the model on the corrective retry, so it says
    what to do, not only what went wrong.
    """
    if not text.strip():
        return "The answer is empty; write the answer in Hebrew."
    if not _HEBREW_LETTER.search(text):
        return "The answer must be written in Hebrew."
    if _FIELD_ASSIGNMENT.search(text) or _OWN_FIELD_NAMES.search(text):
        return (
            "The answer text repeats JSON field names; write plain Hebrew prose only and "
            "put structured values in their own fields."
        )
    if _CHUNK_ID.search(text):
        return (
            "The answer text contains internal chunk ids; cite the car name and section "
            "in words instead, and list the ids only in used_chunk_ids."
        )
    return None


# --- name matching -------------------------------------------------------------------
def normalize(text: str) -> str:
    """Case-folded, NFC, one apostrophe and quote form, single spaces."""
    text = unicodedata.normalize("NFC", text).translate(_APOSTROPHES)
    return " ".join(text.casefold().split())


def _name_pattern(name: str) -> re.Pattern[str]:
    words = r"\s+".join(re.escape(word) for word in normalize(name).split())
    prefixes = f"[{_HEBREW_PREFIXES}]{{0,{_MAX_PREFIXES}}}"
    return re.compile(rf"(?<!\w){prefixes}{words}(?!\w)")


def mentioned(text: str, names: Iterable[str]) -> list[str]:
    """The names that occur in the text as whole words, allowing Hebrew prefixes."""
    haystack = normalize(text)
    return [name for name in names if _name_pattern(name).search(haystack)]


def cars_in_text(text: str, registry: Registry) -> list[str]:
    """Registry car ids named in the text by any alias, in registry order."""
    return [car.id for car in registry.cars if mentioned(text, car.aliases)]


def outside_brands_in_text(text: str, brands: Iterable[str]) -> list[str]:
    return mentioned(text, brands)


def not_covered(llm_names: list[str], brand_hits: list[str]) -> list[str]:
    """Unknown car names for the reply: the model's raw names, plus brands it missed."""
    names = [name.strip() for name in llm_names if name.strip()]
    for brand in brand_hits:
        if not any(normalize(brand) in normalize(name) for name in names):
            names.append(brand)
    return list(dict.fromkeys(names))


# --- fixed replies (Hebrew, gender-neutral address) -----------------------------------
def _car_list(registry: Registry) -> str:
    return ", ".join(car.display_name for car in registry.cars)


def greeting(registry: Registry) -> str:
    return (
        "שלום! אני עונה על שאלות על רכבים, רק לפי כתבות המבחן של שמונה רכבים מאתר "
        f"auto.co.il: {_car_list(registry)}. אפשר לשאול על נתונים, להשוות בין רכבים "
        "או לבקש המלצה."
    )


def unknown_car_reply(names: list[str], registry: Registry) -> str:
    return (
        f"אין לי מידע על {', '.join(names)}: הכתבות שאני מכיר עוסקות רק בשמונה רכבים - "
        f"{_car_list(registry)}. אפשר לשאול על כל אחד מהם, או לבקש המלצה מתוכם."
    )


def low_relevance_reply(registry: Registry) -> str:
    return (
        "לא מצאתי בכתבות מידע שעונה על השאלה הזאת. אפשר לשאול על שמונה הרכבים שנבחנו: "
        f"{_car_list(registry)}."
    )


def out_of_scope_reply(registry: Registry) -> str:
    return (
        "אני עוזר רק בשאלות על רכבים, לפי כתבות המבחן של שמונה רכבים: "
        f"{_car_list(registry)}. אפשר לשאול על נתונים, השוואות או המלצות."
    )


def too_long_reply(limit: int) -> str:
    return f"ההודעה ארוכה מדי (יותר מ-{limit} תווים). אפשר לקצר ולשאול שוב?"


EMPTY_REPLY = "לא התקבלה שאלה. על איזה רכב אפשר לעזור?"
LLM_ERROR_REPLY = "משהו השתבש ביצירת התשובה. אפשר לנסות שוב בעוד רגע?"
