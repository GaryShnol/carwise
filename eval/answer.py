"""Answer level of the eval (CW-302): deterministic checks on real generated answers.

Why code first and a judge only where code cannot decide: every check here is
free, repeatable and explainable, so a failure points at a cause. The LLM judge
(eval/judge.py) grades only what code cannot read: the direction of a
comparison, a premise correction, and whether a recommendation fits the stated
preferences.

What is checked on the last answer of each question:

- behavior, from the refusal type (an answer, a gate refusal, the out-of-scope reply);
- the expected cars are cited (citations are already verified in code against the
  chunks retrieved that turn, so a citation is a real source);
- `must_include` groups, `must_not_include` strings, `must_not_match` patterns;
- the CW-202/CW-206 post-check outcome (a fallback means both drafts failed);
- "in another article" phrasings, which the generate prompt forbids (CW-202);
- car-number attribution: a number placed with car A must be one that A's chunks
  state, when another retrieved car's chunks are what back it;
- the preference profile after the last turn, for the multi-turn scenario.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from carwise import guardrails, numbers
from carwise.config import Settings
from carwise.pipeline import Pipeline
from carwise.preferences import Session
from carwise.registry import Powertrain, Registry
from carwise.schemas import Answer, PostCheckOutcome, Preferences, RefusalReason, RetrievedChunk
from eval.questions import Behavior, Question

# The phrasings generate v2/v3 forbid (rule 10), plus close variants seen in Hebrew.
ANOTHER_ARTICLE = (
    "בכתבה אחרת",
    "במאמר אחר",
    "לפי מקור אחר",
    "בכתבה נוספת",
    "במאמר נוסף",
    "בכתבה נפרדת",
    "in another article",
)
# Calling the sources "the excerpts" exposes the pipeline; generate v4 asks for "the articles".
EXCERPT_WORDING = ("בקטעים", "הקטעים", "קטעים שסופקו", "בקטע ", "excerpt")
GATE_REFUSALS = {RefusalReason.UNKNOWN_CAR, RefusalReason.LOW_RELEVANCE}
_CLAUSE_END = ",;:—–"  # a number's clause ends at these (a hyphen is part of "ב-EV9", not one)
_SENTENCE_PUNCTUATION = ".!?…"
# Small Hebrew number words, for a passenger count written as a word ("חמישה").
_NUMBER_WORDS = {
    "אחד": 1, "אחת": 1, "שניים": 2, "שתיים": 2, "שני": 2, "שתי": 2, "שלושה": 3, "שלוש": 3,
    "ארבעה": 4, "ארבע": 4, "חמישה": 5, "חמש": 5, "שישה": 6, "שש": 6, "שבעה": 7, "שבע": 7,
}  # fmt: skip


class BudgetStopError(RuntimeError):
    """The answer eval reached its cost cap; the run stops with what it has."""


class Check(BaseModel):
    """One deterministic check: its name, the result, and a metrics-only detail."""

    model_config = ConfigDict(extra="forbid")

    name: str
    passed: bool
    detail: str = ""


class Attribution(BaseModel):
    model_config = ConfigDict(extra="forbid")

    number: str
    placed_with: str  # the car the answer puts the number with
    backed_by: list[str]  # the retrieved cars whose chunks state it


@dataclass
class Played:
    """Every turn of one question, played through the real pipeline in one session."""

    answers: list[Answer]
    preferences: Preferences
    user_turns: list[str] = field(default_factory=list)

    @property
    def last(self) -> Answer:
        return self.answers[-1]


def play(question: Question, pipeline: Pipeline, history_window: int) -> Played:
    session = Session(history_window=history_window)
    answers = []
    for message in question.turns:
        answer = pipeline.answer(message, session)
        answers.append(answer)
        if answer.refusal is RefusalReason.BUDGET_EXCEEDED:
            raise BudgetStopError(f"{question.id}: the answer eval reached its cost cap")
    return Played(answers, session.preferences, list(question.turns))


def behavior_of(answer: Answer) -> str:
    """What the user got: an answer, a gate refusal, the out-of-scope reply, or a failure."""
    refusal = answer.refusal
    if refusal is None:
        return Behavior.ANSWER.value
    if refusal in GATE_REFUSALS:
        return Behavior.REFUSAL.value
    if refusal is RefusalReason.OUT_OF_SCOPE:
        return Behavior.OUT_OF_SCOPE.value
    return refusal.value  # unverified (post-check fallback), llm_error, ...


def another_article_count(text: str) -> int:
    lowered = guardrails.normalize(text)
    return sum(lowered.count(guardrails.normalize(phrase)) for phrase in ANOTHER_ARTICLE)


def fingerprint(text: str) -> str:
    """A short hash: two runs can be compared without storing what they said."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def stated_numbers(text: str, registry: Registry) -> list[str]:
    """The numbers an answer states, as values, sorted; car names ("S6", "01") excluded."""
    normalized = "\n".join(guardrails.normalize(line) for line in text.splitlines())
    found = numbers.find_numbers(_without_car_names(normalized, registry))
    return sorted({format(n.readings[0].value.normalize(), "f") for n in found if n.readings})


def excerpt_wording_count(text: str) -> int:
    lowered = guardrails.normalize(text)
    return sum(lowered.count(guardrails.normalize(word)) for word in EXCERPT_WORDING)


def _car_values(hits: Iterable[RetrievedChunk]) -> dict[str, set[Decimal]]:
    by_car: dict[str, list[str]] = {}
    for hit in hits:
        chunk = hit.chunk
        by_car.setdefault(chunk.car, []).append(f"{chunk.car_name}\n{chunk.section}\n{chunk.text}")
    return {car: numbers.source_values(texts) for car, texts in by_car.items()}


def _backed(number: numbers.Number, values: set[Decimal]) -> bool:
    return any(reading.backed_by(value) for reading in number.readings for value in values)


def _blank(text: str, spans: Iterable[tuple[int, int]]) -> str:
    """The text with each span replaced by spaces, so offsets stay valid."""
    chars = list(text)
    for start, end in spans:
        chars[start:end] = " " * (end - start)
    return "".join(chars)


def citation_spans(text: str) -> list[tuple[int, int]]:
    """Top-level "(...)" spans, nesting allowed: "(קיה EV9, ... (דוח מס' 4))" is one citation."""
    spans: list[tuple[int, int]] = []
    depth, opened = 0, 0
    for i, ch in enumerate(text):
        if ch == "(":
            if depth == 0:
                opened = i
            depth += 1
        elif ch == ")" and depth:
            depth -= 1
            if depth == 0:
                spans.append((opened, i + 1))
    return spans


def sentences(text: str) -> list[str]:
    """Split at a line break, or at . ! ? … followed by whitespace, outside parentheses.

    Section names inside citations end with "?" ("מה התחדש?"); splitting there would
    cut a citation in two and turn its car names into claims.
    """
    parts: list[str] = []
    depth, begin = 0, 0
    for i, ch in enumerate(text):
        if ch == "(":
            depth += 1
        elif ch == ")" and depth:
            depth -= 1
        at_end = ch in _SENTENCE_PUNCTUATION and i + 1 < len(text) and text[i + 1].isspace()
        if ch == "\n" or (depth == 0 and at_end):
            parts.append(text[begin : i + 1])
            begin = i + 1
    parts.append(text[begin:])
    return [part for part in parts if part.strip()]


def _without_car_names(text: str, registry: Registry) -> str:
    """Car names blanked, so "S6" or "01" is never read as a quantity."""
    return _blank(text, [(start, end) for start, end, _ in guardrails.car_mentions(text, registry)])


def _nearest(
    sentence: str, mentions: list[tuple[int, int, str]], start: int, end: int
) -> str | None:
    """The car mentioned closest to a number in its clause, before or after it.

    Hebrew names the car on either side of a figure: "ב-EV9 הוא 397 ק"מ" and
    "370 ק"מ באיון HT". A clause ends at a comma, semicolon, colon or dash, and a
    mention after the number that opens with the conjunction "ו" starts a new clause
    ("MG S6 המחיר 179,990 ולאיון HT ..."). A tie goes to the car before. With no car in
    the clause, the nearest car named before the number in the sentence owns it.
    """

    def ends_clause(i: int) -> bool:
        if sentence[i] not in _CLAUSE_END:
            return False
        between_digits = 0 < i < len(sentence) - 1 and sentence[i - 1 : i + 2 : 2].isdigit()
        return not (sentence[i] == "," and between_digits)  # "168,888" is one number

    left = max((i for i in range(start) if ends_clause(i)), default=-1)
    right = next((i for i in range(end, len(sentence)) if ends_clause(i)), len(sentence))
    best: tuple[int, int, str] | None = None
    for m_start, m_end, car in mentions:
        before = m_end <= start
        if before and m_start <= left:
            continue
        if not before and (m_start >= right or sentence[m_start] == "ו"):
            continue
        distance = start - m_end if before else m_start - end
        key = (distance, 0 if before else 1)
        if best is None or key < best[:2]:
            best = (key[0], key[1], car)
    if best:
        return best[2]
    earlier = [car for m_start, _, car in mentions if m_start < start]
    return earlier[-1] if earlier else None


def attribution_problems(
    answer: str, hits: Sequence[RetrievedChunk], user_texts: Iterable[str], registry: Registry
) -> list[Attribution]:
    """Numbers the answer places with one car while only another retrieved car states them.

    Owner of a number: the car of the next citation in the same sentence when that
    citation names exactly one car (the generate prompt cites after each claim);
    otherwise the nearest car named before it in the sentence. A number no chunk
    backs is the CW-206 check's business, not this one's; a number the user stated,
    or one the owner's chunks state too, is fine.
    """
    by_car = _car_values(hits)
    if len(by_car) < 2:
        return []
    user_texts = list(user_texts)
    # The user's own numbers, in digits or as words ("משפחה של חמישה" makes "5" theirs).
    from_user = numbers.source_values(user_texts) | {
        Decimal(value) for text in user_texts for value in number_words(text)
    }
    problems: list[Attribution] = []
    normalized = "\n".join(guardrails.normalize(line) for line in answer.splitlines())
    in_answer = numbers.find_numbers(_without_car_names(normalized, registry))
    for sentence in sentences(normalized):
        citations = [
            (start, end, guardrails.cars_in_text(sentence[start + 1 : end - 1], registry))
            for start, end in citation_spans(sentence)
        ]
        outside = _blank(sentence, [(start, end) for start, end, _ in citations])
        mentions = guardrails.car_mentions(outside, registry)
        plain = _blank(outside, [(start, end) for start, end, _ in mentions])
        for number in numbers.find_numbers(plain):
            if guardrails.derived(number, [n for n in in_answer if n.text != number.text]):
                continue  # a sum or difference of two numbers the answer states
            cited = next((cars for start, _, cars in citations if start > number.start), [])
            if len(cited) == 1:
                owner: str | None = cited[0]
            else:  # no citation after it, or one citing several cars: the nearest car named
                owner = _nearest(outside, mentions, number.start, number.start + len(number.token))
            if owner is None or owner not in by_car or _backed(number, from_user):
                continue
            if _backed(number, by_car[owner]):
                continue
            others = [c for c, values in by_car.items() if c != owner and _backed(number, values)]
            if others:
                problems.append(
                    Attribution(number=number.text, placed_with=owner, backed_by=others)
                )
    return problems


def number_words(text: str) -> set[int]:
    """Small numbers written as Hebrew words ("חמישה", "לחמישה", "ושניים")."""
    found = set()
    for word in re.findall(r"[א-ת]+", text):
        for cut in range(min(3, len(word))):  # up to two one-letter prefixes, as in "ולחמישה"
            if cut and word[cut - 1] not in guardrails.HEBREW_PREFIXES:
                break
            if word[cut:] in _NUMBER_WORDS:
                found.add(_NUMBER_WORDS[word[cut:]])
                break
    return found


def _small_numbers(text: str) -> set[int]:
    found = {int(r.value) for n in numbers.find_numbers(text) for r in n.readings if r.unit == 1}
    return found | number_words(text)


def preference_checks(
    expected: dict[str, object], profile: Preferences, settings: Settings
) -> list[Check]:
    """The profile after the last turn, read with numbers parsed and hint words matched."""
    checks = []
    for key, want in expected.items():
        if key == "budget_max_nis":
            value = profile.budget.value if profile.budget else ""
            target = Decimal(str(want))
            ok = any(r.backed_by(target) for n in numbers.find_numbers(value) for r in n.readings)
        elif key == "passengers":
            value = profile.passengers.value if profile.passengers else ""
            ok = int(str(want)) in _small_numbers(value)
        elif key == "powertrain":
            value = profile.powertrain.value if profile.powertrain else ""
            words = settings.guardrails.powertrain_words[Powertrain(str(want))]
            ok = bool(guardrails.mentioned(value, words))
        else:
            raise ValueError(f"unknown preference expectation {key!r}")
        checks.append(Check(name=f"preference:{key}", passed=ok, detail="" if ok else "not set"))
    return checks


def checks_for(
    question: Question, played: Played, settings: Settings, registry: Registry
) -> list[Check]:
    """Every deterministic check that applies to this question's last answer."""
    answer, expect = played.last, question.expect
    behavior = behavior_of(answer)
    text = guardrails.normalize(answer.text)
    checks = [
        Check(
            name="behavior",
            passed=behavior == expect.behavior.value,
            detail=f"{behavior}, expected {expect.behavior.value}",
        )
    ]
    if expect.behavior is Behavior.ANSWER:
        cited = {source.car for source in answer.sources}
        needed = {source.car for source in expect.sources}
        missing = sorted(needed - cited)
        any_cars = {source.car for source in expect.sources_any}
        any_ok = not any_cars or bool(any_cars & cited)
        checks.append(
            Check(
                name="sources_cited",
                passed=not missing and any_ok,
                detail=", ".join(missing + ([] if any_ok else ["none of sources_any"])),
            )
        )
    missing_groups = [
        group
        for group in expect.must_include
        if not any(guardrails.normalize(alt) in text for alt in group)
    ]
    if expect.must_include:
        checks.append(
            Check(
                name="must_include",
                passed=not missing_groups,
                detail="; ".join("/".join(group[:3]) for group in missing_groups),
            )
        )
    if expect.must_not_include:
        found = [s for s in expect.must_not_include if guardrails.normalize(s) in text]
        checks.append(Check(name="must_not_include", passed=not found, detail=", ".join(found)))
    if expect.must_not_match:
        hit = [p for p in expect.must_not_match if re.search(p, answer.text)]
        checks.append(Check(name="must_not_match", passed=not hit, detail=f"{len(hit)} pattern(s)"))
    if answer.post_check is not None:
        outcome = answer.post_check.outcome
        kinds = sorted({k for attempt in answer.post_check.attempts for k in attempt.kinds()})
        checks.append(
            Check(
                name="post_check",
                passed=outcome is not PostCheckOutcome.FALLBACK,
                detail=f"{outcome.value}" + (f" ({', '.join(kinds)})" if kinds else ""),
            )
        )
    count = another_article_count(answer.text)
    checks.append(Check(name="another_article", passed=count == 0, detail=str(count)))
    if behavior == Behavior.ANSWER.value:
        wrong = attribution_problems(answer.text, answer.retrieved, played.user_turns, registry)
        checks.append(
            Check(
                name="attribution",
                passed=not wrong,
                detail="; ".join(
                    f"{w.number}: {w.placed_with} <- {'/'.join(w.backed_by)}" for w in wrong
                ),
            )
        )
    if expect.preferences:
        checks += preference_checks(expect.preferences, played.preferences, settings)
    return checks
