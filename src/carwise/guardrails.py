"""Deterministic checks around the two LLM calls, and the fixed replies they lead to.

Why code and not prompt instructions: a prompt asks, code enforces (CLAUDE.md
section 2, "do not trust the model, bound it"). Everything here is plain
string work: no model, no network, cheap enough to run on every turn.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from functools import lru_cache
from itertools import combinations, product
from typing import TYPE_CHECKING, TypeVar

from carwise import numbers
from carwise.registry import BodyType, Car, Powertrain, Registry

if TYPE_CHECKING:  # schemas imports this module for the answer guard
    from carwise.schemas import RetrievedChunk

_K = TypeVar("_K", BodyType, Powertrain)

# Hebrew attaches up to a few one-letter prefixes to a name: "לאודי", "ובטויוטה".
HEBREW_PREFIXES = "והבכלמש"
_MAX_PREFIXES = 3
# A brand with fewer Hebrew letters than this is "short" (CW-602): it takes at most one
# prefix, and only one of _SHORT_BRAND_PREFIXES. With ש, כ, מ or stacked prefixes a short
# brand forms ordinary words: "שמרנו", "הכרנו", "מכרנו", "שברנו" all end in "רנו".
_MIN_LETTERS_FOR_PREFIXES = 4
_SHORT_BRAND_PREFIXES = "בלהו"
# What may stand between a name and the brand before it or the model word after it.
_JOIN = r"[\s\-־]+"
# Geresh and gershayim have look-alikes (׳ ’ ` and ״ ”); one form makes names comparable.
_APOSTROPHES = str.maketrans({"׳": "'", "’": "'", "`": "'", "״": '"', "“": '"', "”": '"'})

# --- answer text guard (used by schemas.Generation) -------------------------------
# A snake_case key followed by "=" or ":" ("mentioned_in_context=false", seen once in
# the CW-104 spike), the reply's own field names, or an internal chunk id ("mg_s6:007").
_FIELD_ASSIGNMENT = re.compile(r"\b[a-z]+(?:_[a-z]+)+\s*[=:]")
_OWN_FIELD_NAMES = re.compile(r"\b(?:used_chunk_ids|answer)\b")
_CHUNK_ID = re.compile(r"\b[a-z0-9]+(?:_[a-z0-9]+)*:\d{3}\b")
_HEBREW_LETTER = re.compile("[א-ת]")
# Links and images (CW-401, CW-611): the UI renders answers as markdown, so a link
# the model wrote would be clickable; the only links shown come from the registry.
# Caught: a URL or "www." (GFM links both bare); "](" and "][" (inline, full and
# collapsed reference links and images, nested brackets included); a reference
# definition ("[1]: //host"), also inside a quote or list item, which a shortcut
# reference "[1]" needs; an autolink "<scheme:...>"; an e-mail address (GFM links
# it bare). Brackets alone ("[לפי הכתבה]") and "[x]: y" mid-line still pass.
_LINK = re.compile(
    r"https?://|\bwww\.|\]\(|\]\["
    r"|^(?:[ \t]*(?:>|[-*+](?=[ \t])|\d{1,9}[.)](?=[ \t])))*[ \t]*\[(?:[^\]\\]|\\.)+\]:"
    r"|<[a-z][a-z0-9+.\-]{1,31}:[^\s<>]*>"
    r"|[\w.+\-]+@[\w\-]+\.[\w.\-]+",
    re.IGNORECASE | re.MULTILINE,
)


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
    if _LINK.search(text):
        return (
            "The answer text contains a link or an image; write plain Hebrew prose with no "
            "URLs and no markdown links or images. Name the car and section instead."
        )
    if _CHUNK_ID.search(text):
        return (
            "The answer text contains internal chunk ids; cite the car name and section "
            "in words instead, and list the ids only in used_chunk_ids."
        )
    return None


# --- prompt hygiene (CW-205) -----------------------------------------------------------
# Line-start role labels a model may read as a turn boundary ("System: ...").
_ROLE_MARKER = re.compile(
    r"^([ \t]*(?:system|assistant|user|developer|tool|מערכת|עוזר|משתמש))[ \t]*:",
    re.IGNORECASE | re.MULTILINE,
)


def escape_text(text: str) -> str:
    """Text from outside the code (chunks, the user, the history) as inert prompt data.

    "<" and ">" become "&lt;" and "&gt;", so no text can close or open an
    <excerpts> or <excerpt> tag, or write a special token such as "<|im_start|>".
    The change is reversible (html.unescape) and leaves Hebrew untouched: the
    articles contain neither character. "&" is kept as is, because escaping it
    would show the model "לינק &amp; קו" and invite it to copy that. A role label
    at the start of a line loses its colon ("System:" -> "System -"), so it no
    longer looks like a turn boundary; the words stay readable.
    """
    text = text.replace("<", "&lt;").replace(">", "&gt;")
    return _ROLE_MARKER.sub(r"\1 -", text)


def one_line(text: str) -> str:
    """A field that must stay on its own prompt line: newlines cannot start a fake
    header such as "User preferences" or "Cars the articles do not cover"."""
    return " ".join(escape_text(text).split())


def escape_attribute(text: str) -> str:
    """A value inside an excerpt attribute (car="...", section="..."). An ASCII quote
    would end the attribute, so it becomes gershayim, which reads the same in Hebrew."""
    return one_line(text).replace('"', "״")


# --- name matching -------------------------------------------------------------------
def normalize(text: str) -> str:
    """Case-folded, NFC, one apostrophe and quote form, single spaces."""
    text = unicodedata.normalize("NFC", text).translate(_APOSTROPHES)
    return " ".join(text.casefold().split())


def _words(name: str) -> str:
    return r"\s+".join(re.escape(word) for word in normalize(name).split())


@lru_cache(maxsize=1024)
def _name_pattern(
    name: str, letters: str = HEBREW_PREFIXES, max_prefixes: int = _MAX_PREFIXES
) -> re.Pattern[str]:
    prefixes = f"[{letters}]{{0,{max_prefixes}}}"
    return re.compile(rf"(?<!\w){prefixes}{_words(name)}(?!\w)")


def _brand_pattern(brand: str) -> re.Pattern[str]:
    """A brand as a whole word, with fewer prefixes allowed on a short Hebrew brand.

    A brand with fewer than _MIN_LETTERS_FOR_PREFIXES Hebrew letters ("רנו", "צ'רי",
    "ב.מ.ו", "קיה") takes at most one prefix, from ב, ל, ה, ו: "לרנו", "ברנו", "הרנו",
    "ורנו" match; "שמרנו", "הכרנו", "מכרנו", "שהרנו", "ולרנו" do not. Given up: the
    short brand after ש, כ or מ, or after two prefixes ("שרנו" as "that Renault",
    "מרנו", "ולרנו"). The gate then relies on the understand call's unrecognized_cars;
    the post-check does not catch those forms. Every other brand, Hebrew or Latin,
    keeps up to _MAX_PREFIXES of any prefix letter, so a longer Hebrew brand can still
    match an ordinary word ("באופל", "in the dark").
    """
    hebrew = len(_HEBREW_LETTER.findall(brand))
    if 0 < hebrew < _MIN_LETTERS_FOR_PREFIXES:
        return _name_pattern(brand, _SHORT_BRAND_PREFIXES, 1)
    return _name_pattern(brand)


@lru_cache(maxsize=1024)
def _before_pattern(brand: str) -> re.Pattern[str]:
    """The brand as the last word before a name: "אאודי S6", "לאאודי S6"."""
    return re.compile(rf"{_brand_pattern(brand).pattern}{_JOIN}$")


@lru_cache(maxsize=1024)
def _after_pattern(word: str) -> re.Pattern[str]:
    """A model word right after a name, without a prefix: "C3 איירקרוס", "Aion-Y".
    A prefix would make it a second car ("C3 והאיירקרוס" is "C3 and the Aircross")."""
    return re.compile(rf"^{_JOIN}{_words(word)}(?!\w)")


def mentioned(text: str, names: Iterable[str]) -> list[str]:
    """The names that occur in the text as whole words, allowing Hebrew prefixes."""
    haystack = normalize(text)
    return [name for name in names if _name_pattern(name).search(haystack)]


@dataclass(frozen=True)
class _Mention:
    start: int
    end: int
    car_id: str
    other_model: str | None  # set when the alias names another model, not this car


def _first(text: str, words: Iterable[str], pattern: Callable[[str], re.Pattern[str]]) -> str:
    return next((word for word in words if pattern(word).search(text)), "")


def _scan(text: str, registry: Registry, outside_brands: Iterable[str]) -> list[_Mention]:
    """Every car name in a normalized text, in text order; of two overlapping, the longer wins.

    Why the context check (CW-601): short aliases ("S6", "C3", "Aion", "אלנטרה")
    are also parts of other models' names. A name is the corpus car only when no
    other brand (another car's `brand_names`, or an outside brand) stands right
    before it ("אאודי S6"), and none of the car's `other_models` words follows it
    ("C3 איירקרוס"). Otherwise it names another model, which callers treat as a
    car the articles do not cover. Ordinary words after it ("C3 החדשה") do not block.
    """
    found: list[tuple[int, int, Car, str]] = []
    for car in registry.cars:
        for name in car.aliases:
            found += [(m.start(), m.end(), car, name) for m in _name_pattern(name).finditer(text)]
    brands = list(outside_brands)
    mentions: list[_Mention] = []
    for start, end, car, name in sorted(found, key=lambda item: (item[0], -item[1])):
        if mentions and start < mentions[-1].end:
            continue
        others = [brand for c in registry.cars if c is not car for brand in c.brand_names]
        before = _first(text[:start], [*others, *brands], _before_pattern)
        after = _first(text[end:], car.other_models, _after_pattern)
        other = None
        if before or after:
            brand = before or _first(text[:start], car.brand_names, _before_pattern)
            other = " ".join(part for part in (brand, name, after) if part)
        mentions.append(_Mention(start, end, car.id, other))
    return mentions


def car_mentions(
    text: str, registry: Registry, outside_brands: Iterable[str] = ()
) -> list[tuple[int, int, str]]:
    """Every corpus car name in an already normalized text: (start, end, car id), in text order.

    Where two names overlap ("GAC איון HT" and "איון HT"), the longer one wins. A
    name of another model ("אאודי S6", "Aion Y") is left out.
    """
    return [
        (m.start, m.end, m.car_id)
        for m in _scan(text, registry, outside_brands)
        if m.other_model is None
    ]


def cars_in_text(text: str, registry: Registry, outside_brands: Iterable[str] = ()) -> list[str]:
    """Registry car ids named in the text by any alias, in registry order."""
    named = {car_id for _, _, car_id in car_mentions(normalize(text), registry, outside_brands)}
    return [car.id for car in registry.cars if car.id in named]


def other_models_in_text(
    text: str, registry: Registry, outside_brands: Iterable[str] = ()
) -> list[str]:
    """Names built on a corpus alias that name another model ("אאודי S6", "C3 איירקרוס").

    Spelled from the config (brand, alias, model word), because matching sees the
    text case-folded.
    """
    names = [m.other_model for m in _scan(normalize(text), registry, outside_brands)]
    return list(dict.fromkeys(name for name in names if name))


def _other_model_cars(text: str, registry: Registry, outside_brands: list[str]) -> set[str]:
    """The corpus cars whose aliases the text uses for another model."""
    return {m.car_id for m in _scan(normalize(text), registry, outside_brands) if m.other_model}


def outside_brands_in_text(text: str, brands: Iterable[str]) -> list[str]:
    """The brands that occur in the text, under the short-brand rule of `_brand_pattern`."""
    haystack = normalize(text)
    return [brand for brand in brands if _brand_pattern(brand).search(haystack)]


def not_covered(llm_names: list[str], code_hits: list[str]) -> list[str]:
    """Unknown car names for the reply: the model's raw names, plus names code found
    that the model missed (other models on a corpus alias, then outside brands)."""
    names = [name.strip() for name in llm_names if name.strip()]
    for brand in code_hits:
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
    Another model named on a corpus alias ("Aion Y", "אאודי S6") is not the corpus
    car; it is backed like an outside car, by a chunk or the question naming another
    model on that alias (in any spelling: "Audi S6" asked backs "אאודי S6" answered).
    Limit: a model name with no registry alias and no listed brand is not caught.
    """
    hits = list(hits)
    sources = "\n".join(hit.chunk.text for hit in hits)
    retrieved = {hit.chunk.car for hit in hits}
    asked = "\n".join(not_covered)
    outside_brands = list(outside_brands)
    in_sources = cars_in_text(sources, registry, outside_brands)
    problems = [
        registry.get(car_id).display_name
        for car_id in cars_in_text(answer, registry, outside_brands)
        if car_id not in retrieved and car_id not in in_sources
    ]
    backed = _other_model_cars(f"{sources}\n{asked}", registry, outside_brands)
    problems += [
        name
        for name in other_models_in_text(answer, registry, outside_brands)
        if not _other_model_cars(name, registry, outside_brands) <= backed
    ]
    problems += [
        brand
        for brand in outside_brands_in_text(answer, outside_brands)
        if not outside_brands_in_text(sources, [brand])
        and not outside_brands_in_text(asked, [brand])
    ]
    return problems


def unsupported_numbers(
    answer: str,
    hits: Iterable[RetrievedChunk],
    user_texts: Iterable[str],
    registry: Registry,
    always_allowed: Iterable[float],
) -> list[str]:
    """Numbers in the answer, as written, that neither the sources nor the user stated.

    Backed: a retrieved chunk (its text, car name or section, all of which the model
    saw) or the user's own words state the number, to the precision the answer
    wrote it in (`carwise.numbers`). Derived: a difference or sum of two numbers
    is allowed only when both operands are chunk numbers that the answer itself
    states, so the reader can verify the arithmetic. Numbers inside car names
    ("MG S6", "GV80", "לינק אנד קו 01") are not claims and are skipped.
    Limit: numbers written as words are not checked.
    """
    hits = list(hits)
    text = "\n".join(normalize(line) for line in answer.splitlines())  # keeps list markers
    for car in registry.cars:
        for name in (car.display_name, *car.aliases):
            text = _name_pattern(name).sub(" ", text)
    from_chunks = numbers.source_values(
        f"{hit.chunk.car_name}\n{hit.chunk.section}\n{hit.chunk.text}" for hit in hits
    )
    from_user = numbers.source_values(user_texts)
    allowed = {Decimal(str(value)) for value in always_allowed}
    found = numbers.find_numbers(text)
    operands = [number for number in found if _backed(number, from_chunks)]
    problems = [
        number.text
        for number in found
        if not _backed(number, from_chunks | from_user | allowed)
        and not derived(number, [other for other in operands if other is not number])
    ]
    return list(dict.fromkeys(problems))


def _backed(number: numbers.Number, values: set[Decimal]) -> bool:
    return any(reading.backed_by(value) for reading in number.readings for value in values)


def derived(number: numbers.Number, operands: list[numbers.Number]) -> bool:
    """True when the number is the sum or difference of two other numbers in the answer."""
    for first, second in combinations(operands, 2):
        for a, b, n in product(first.readings, second.readings, number.readings):
            tolerance = max(a.unit, b.unit, n.unit)
            if abs(n.value - (a.value + b.value)) < tolerance:
                return True
            if abs(n.value - abs(a.value - b.value)) < tolerance:
                return True
    return False


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


# --- section names shown to the user -------------------------------------------------
# Must equal carwise.ingest.chunk.SECTION_SEPARATOR (a test checks it); not imported,
# because chunk imports schemas, which imports this module.
MERGED_SECTION_SEPARATOR = " / "
ELLIPSIS = "…"


def section_label(section: str, max_chars: int) -> str:
    """A chunk's section name as the user sees it; Citation and telemetry keep the full one.

    Why: merged sections join every heading ("שאלות נפוצות / מה הטווח? / כמה עולה?"),
    which can run past 150 characters, and " / " reads like a path. A comma reads as a
    list, and a cut at a word boundary keeps the line short without a broken word.
    """
    label = section.replace(MERGED_SECTION_SEPARATOR, ", ").strip()
    if len(label) <= max_chars:
        return label
    cut = label[: max_chars - len(ELLIPSIS) + 1]
    space = cut.rfind(" ")
    cut = cut[:space] if space > 0 else cut[: max_chars - len(ELLIPSIS)]
    return cut.rstrip(" ,;:-") + ELLIPSIS


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


def unverified_reply(
    registry: Registry, hits: list[RetrievedChunk], limit: int, max_section_chars: int
) -> str:
    """Safe fallback when two answers failed the post-check: no model text at all,
    only where in the articles the closest information is."""
    places = []
    for car_id in closest_by_score(hits, limit):
        sections = [
            section_label(hit.chunk.section, max_section_chars)
            for hit in hits
            if hit.chunk.car == car_id
        ]
        places.append(f"{registry.get(car_id).display_name} ({', '.join(dict.fromkeys(sections))})")
    where = f" המידע הקרוב ביותר נמצא בכתבות על {'; '.join(places)}." if places else ""
    return (
        "לא הצלחתי לנסח תשובה שנשענת רק על הכתבות, ולכן לא אציג אותה."
        + where
        + " אפשר לנסח את השאלה מחדש, או לשאול על רכב אחד בכל פעם."
    )


def too_long_reply(limit: int) -> str:
    return f"ההודעה ארוכה מדי (יותר מ-{limit} תווים). אפשר לקצר ולשאול שוב?"


def budget_reply(max_cost_usd: float) -> str:
    return (
        f"הגעתי למגבלת העלות שהוגדרה לשיחה הזאת (${max_cost_usd:g}), ולכן השיחה נעצרת כאן. "
        "אפשר להתחיל שיחה חדשה בהפעלה הבאה."
    )


def server_budget_reply(max_total_cost_usd: float) -> str:
    """The shared cap of every session on this server (CW-605); a refresh cannot help."""
    return (
        "הגעתי למגבלת העלות הכוללת שהוגדרה לשרת הזה "
        f"(${max_total_cost_usd:g} לכל השיחות יחד), ולכן אין אפשרות לענות על שאלות נוספות."
    )


# --- scope of a recommendation (CW-606) ------------------------------------------------
# Prompt rule 8 asks every recommendation or ranking to say it covers only the eight
# reviewed cars; the eval showed the model leaving it out, so code adds it when missing.
# No digits and no car names: the post-check could never count it as a claim.
SCOPE_NOTE = "אני מתייחס רק לשמונה הרכבים שנבחנו בכתבות."
# "Eight" stated about the reviewed cars, in the phrasings answers use (up to three
# prefixes on "eight": "מבין שמונה", "לשמונת", "מ-8", "השמונה"):
# - eight, then a word for the cars or their articles: "שמונה הרכבים", "8 כתבות";
# - eight, then a relative clause about the review: "השמונה שנבחנו", "שמונת שבכתבות";
# - the cars, then eight: "הרכבים השמונה";
# - "among the eight" with no noun ("מבין השמונה", "מתוך ה-8", "מהשמונה"), only where
#   the phrase ends: punctuation, the end of the text, a review clause, or a pronoun or
#   "יש"/"אין" that starts the next clause ("הזול מהשמונה הוא ..."). So "בין השמונה
#   לתשע שניות" or "כל ה-8 שניות" is not a scope statement. Attached ב is left out:
#   "בשמונה" is "in eight", as in "בשמונה שניות".
# A bare "שמונה" is not enough: "שמונה הילוכים", "בשמונה שניות" or "שמונה שנות
# אחריות" say nothing about the scope. The clause verbs are listed, not any word
# starting with ש, because "שניות", "שנים" and "שעות" start with it too.
# Accepted limits (they only leave the note out): an "eight cars" phrase about
# something else, such as "8 רכבים נמכרו" or "שמונה דגמים של מותג אחר".
_EIGHT = rf"(?<!\w)[{HEBREW_PREFIXES}]{{0,{_MAX_PREFIXES}}}[-־]?(?:שמונה|שמונת|8)"
_FLEET = r"ה?(?:רכבים|רכבי|מכוניות|דגמים|דגמי|כתבות|מבחנים|מבחני)|כלי\s+ה?רכב"
_REVIEWED = r"ש(?:נבחנו|נסקרו|נבדקו|הוצגו|נכללו|מופיעים|מופיעות|בכתבות|במבחנים|במבחן|במאגר)"
_FLEET_FIRST = rf"(?<!\w)[{HEBREW_PREFIXES}]{{0,{_MAX_PREFIXES}}}ה(?:רכבים|מכוניות|דגמים|כתבות)"
_AMONG = r"(?<!\w)ו?(?:(?:מבין|מתוך|בין|מכל|לכל|כל)\s+|מ)ה[-־]?(?:שמונה|8)"
# A decimal point is not the end of a phrase ("ה-8.5"), and a dash ends it only with a
# space before it: "8-9" and "8–9" are ranges.
_NEXT_CLAUSE = rf"(?:{_REVIEWED}|הוא|היא|הם|הן|זה|זו|יש|אין)(?!\w)"
_PHRASE_END = rf"(?=\s*(?:[.,](?!\d)|[:;!?)])|\s+[-–—]|\s*$|\s+{_NEXT_CLAUSE})"
_EIGHT_CARS = re.compile(
    rf"{_EIGHT}\s+(?:{_FLEET}|{_REVIEWED})(?!\w)"
    rf"|{_FLEET_FIRST}\s+ה[-־]?(?:שמונה|8)(?!\w)"
    rf"|{_AMONG}{_PHRASE_END}"
)
# Markdown emphasis and quotes may sit inside the phrase: "**שמונה** הרכבים".
_EMPHASIS = str.maketrans("", "", '*"')


def states_scope(answer: str) -> bool:
    """True when the answer already says it covers only the eight reviewed cars."""
    return bool(_EIGHT_CARS.search(normalize(answer).translate(_EMPHASIS)))


EMPTY_REPLY = "לא התקבלה שאלה. על איזה רכב אפשר לעזור?"
LLM_ERROR_REPLY = "משהו השתבש ביצירת התשובה. אפשר לנסות שוב בעוד רגע?"
