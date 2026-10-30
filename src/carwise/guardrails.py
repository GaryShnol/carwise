"""Deterministic checks around the two LLM calls, and the fixed replies they lead to.

Why code and not prompt instructions: a prompt asks, code enforces (CLAUDE.md
section 2, "do not trust the model, bound it"). Everything here is plain
string work: no model, no network, cheap enough to run on every turn.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING, TypeVar

from carwise.registry import BodyType, Car, Powertrain, Registry

if TYPE_CHECKING:  # schemas imports this module for the answer guard
    from carwise.schemas import RetrievedChunk

_K = TypeVar("_K", BodyType, Powertrain)

# Hebrew attaches up to a few one-letter prefixes to a name: "לאודי", "ובטויוטה".
HEBREW_PREFIXES = "והבכלמש"
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
    prefixes = f"[{HEBREW_PREFIXES}]{{0,{_MAX_PREFIXES}}}"
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


# --- post-check of the generated answer (CW-202) -------------------------------------
def unsupported_cars(
    answer: str,
    hits: Iterable[RetrievedChunk],
    not_covered: Iterable[str],
    registry: Registry,
    outside_brands: Iterable[str],
) -> list[str]:
    """Car names in the answer that this turn's sources cannot back.

    A corpus car is backed when it was retrieved, or when a retrieved chunk names
    it (a review may compare against a rival). An outside brand is backed only by
    a retrieved chunk that names it, or by the user's own question (`not_covered`,
    where the answer is expected to say the articles do not cover it). Anything
    else came from the model's own knowledge, which is what this check exists for.
    Limit: a model name with no registry alias and no listed brand is not caught.
    """
    hits = list(hits)
    sources = "\n".join(hit.chunk.text for hit in hits)
    retrieved = {hit.chunk.car for hit in hits}
    asked = "\n".join(not_covered)
    problems = [
        car.display_name
        for car in registry.cars
        if car.id not in retrieved
        and mentioned(answer, car.aliases)
        and not mentioned(sources, car.aliases)
    ]
    problems += [
        brand
        for brand in mentioned(answer, outside_brands)
        if not mentioned(sources, [brand]) and not mentioned(asked, [brand])
    ]
    return problems


# --- suggestions inside the corpus (CW-201) -------------------------------------------
def hinted_cars(
    text: str,
    registry: Registry,
    body_type_words: Mapping[BodyType, Iterable[str]],
    powertrain_words: Mapping[Powertrain, Iterable[str]],
    limit: int,
) -> list[str]:
    """Cars that fit the body type or powertrain the user's own words point at.

    Why only the user's words: the unknown car itself must not be classified from
    the model's knowledge, so "an electric SUV like X" is the only grounded signal.
    A car scores one point per matching dimension; only the best score is kept, so
    "electric SUV" suggests electric SUVs before any electric or any SUV.
    """
    bodies = _most_specific(text, body_type_words)
    powertrains = _most_specific(text, powertrain_words)
    scores = {
        car.id: (car.body_type in bodies) + (car.powertrain in powertrains) for car in registry.cars
    }
    best = max(scores.values(), default=0)
    if best == 0:
        return []
    return [car_id for car_id, score in scores.items() if score == best][:limit]


def _most_specific(text: str, words_by_kind: Mapping[_K, Iterable[str]]) -> set[_K]:
    """The kinds with the most hint words in the text: "היברידי נטען" is a plug-in
    hybrid only, while a bare "היברידי" fits both hybrid kinds."""
    counts = {kind: len(mentioned(text, words)) for kind, words in words_by_kind.items()}
    best = max(counts.values(), default=0)
    return {kind for kind, count in counts.items() if count == best} if best else set()


def closest_by_score(hits: Iterable[RetrievedChunk], limit: int) -> list[str]:
    """Cars of the best-scoring chunks, best first, each car once."""
    ranked = sorted(hits, key=lambda hit: (-hit.score, hit.chunk.chunk_id))
    return list(dict.fromkeys(hit.chunk.car for hit in ranked))[:limit]


# --- fixed replies (Hebrew, gender-neutral address) -----------------------------------
_BODY_TYPE_HE = {
    BodyType.SUPERMINI: "סופרמיני",
    BodyType.HATCHBACK: "האצ'בק",
    BodyType.SEDAN: "סדאן",
    BodyType.SUV: "רכב פנאי",
    BodyType.SUV_COUPE: "פנאי-קופה",
}
_POWERTRAIN_HE = {
    Powertrain.ELECTRIC: "חשמלי",
    Powertrain.PLUG_IN_HYBRID: "היברידי נטען",
    Powertrain.MILD_HYBRID: "היברידי מתון",
    Powertrain.PETROL: "בנזין",
}
FOLLOW_UP = "אפשר לשאול על כל אחד מהם, להשוות ביניהם או לבקש המלצה."


def _car_list(registry: Registry) -> str:
    return ", ".join(car.display_name for car in registry.cars)


def describe(car: Car) -> str:
    """'MG S6 (רכב פנאי, חשמלי)': name plus what the registry says, nothing more."""
    facts = [
        _BODY_TYPE_HE[car.body_type] if car.body_type else "",
        _POWERTRAIN_HE[car.powertrain] if car.powertrain else "",
    ]
    facts = [fact for fact in facts if fact]
    return f"{car.display_name} ({', '.join(facts)})" if facts else car.display_name


def corpus_overview(registry: Registry) -> str:
    """The eight cars grouped by powertrain, each with its body type when the article says it."""
    groups: list[str] = []
    for kind, label in _POWERTRAIN_HE.items():
        cars = [car for car in registry.cars if car.powertrain is kind]
        if cars:
            names = ", ".join(
                f"{car.display_name} ({_BODY_TYPE_HE[car.body_type]})"
                if car.body_type
                else car.display_name
                for car in cars
            )
            groups.append(f"{label}: {names}")
    rest = [car.display_name for car in registry.cars if car.powertrain is None]
    if rest:
        groups.append(", ".join(rest))
    return "; ".join(groups)


def _suggestion_text(registry: Registry, suggested: list[str]) -> str:
    if suggested:
        cars = ", ".join(describe(registry.get(car_id)) for car_id in suggested)
        return f"מבין שמונה הרכבים שנבחנו, הכי קרובים לשאלה: {cars}. {FOLLOW_UP}"
    return f"אלה שמונה הרכבים שנבחנו - {corpus_overview(registry)}. {FOLLOW_UP}"


def greeting(registry: Registry) -> str:
    return (
        "שלום! אני עונה על שאלות על רכבים, רק לפי כתבות המבחן של שמונה רכבים מאתר "
        f"auto.co.il: {_car_list(registry)}. אפשר לשאול על נתונים, להשוות בין רכבים "
        "או לבקש המלצה."
    )


def unknown_car_reply(names: list[str], registry: Registry, suggested: list[str]) -> str:
    """Says what is not covered, then helps within the corpus; never describes the unknown car."""
    return (
        f"אין לי מידע על {', '.join(names)}: הכתבות שאני מכיר עוסקות רק בשמונה רכבים. "
        + _suggestion_text(registry, suggested)
    )


def low_relevance_reply(registry: Registry, suggested: list[str]) -> str:
    return "לא מצאתי בכתבות מידע שעונה על השאלה הזאת. " + _suggestion_text(registry, suggested)


def out_of_scope_reply(registry: Registry) -> str:
    return (
        "אני עוזר רק בשאלות על רכבים, לפי כתבות המבחן של שמונה רכבים - "
        f"{corpus_overview(registry)}. אפשר לשאול על נתונים, השוואות או המלצות."
    )


def unverified_reply(registry: Registry, hits: list[RetrievedChunk], limit: int) -> str:
    """Safe fallback when two answers failed the post-check: no model text at all,
    only where in the articles the closest information is."""
    places = []
    for car_id in closest_by_score(hits, limit):
        sections = [hit.chunk.section for hit in hits if hit.chunk.car == car_id]
        places.append(f"{registry.get(car_id).display_name} ({', '.join(dict.fromkeys(sections))})")
    where = f" המידע הקרוב ביותר נמצא בכתבות על {'; '.join(places)}." if places else ""
    return (
        "לא הצלחתי לנסח תשובה שנשענת רק על הכתבות, ולכן לא אציג אותה."
        + where
        + " אפשר לנסח את השאלה מחדש, או לשאול על רכב אחד בכל פעם."
    )


def too_long_reply(limit: int) -> str:
    return f"ההודעה ארוכה מדי (יותר מ-{limit} תווים). אפשר לקצר ולשאול שוב?"


EMPTY_REPLY = "לא התקבלה שאלה. על איזה רכב אפשר לעזור?"
LLM_ERROR_REPLY = "משהו השתבש ביצירת התשובה. אפשר לנסות שוב בעוד רגע?"
