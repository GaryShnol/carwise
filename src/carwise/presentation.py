"""Display-only tidying of a generated answer (CW-627).

Why: the generation prompt asks the model to cite car and section next to every
claim, and the post-check and eval rely on the answer as the model wrote it. On
screen, though, the markers are noise: the model often copies a whole FAQ
heading or several merged headings into "(MG S6, ...)", and the CLI and the UI
already list every cited chunk under the answer. So the display hides them,
while the `Answer` object, telemetry and eval keep the original text.

Only the CLI and UI import this module; the pipeline, guardrails and eval never
do, so nothing a check or a report sees can change here.

What counts as a marker is deliberately narrow: a balanced parenthesised group
whose every top-level ";" segment starts with a registry car name (any alias,
Hebrew prefixes allowed, matched by the guardrails' own name matching) followed
directly by a comma. Every other parenthesis ("(WLTP)", "(MG S6)") is kept.
"""

from __future__ import annotations

import re

from carwise.guardrails import car_mentions, normalize
from carwise.registry import Registry

# No space is left in front of these after a marker is removed.
_PUNCTUATION = ".,;:!?"
_HORIZONTAL_SPACE = " \t"
_LIST_MARKER_ONLY = re.compile(r"\s*(?:[-*+]|\d+[.)])?\s*")


def strip_inline_citations(text: str, registry: Registry) -> str:
    """The text without inline "(car, section)" markers, tidied where one was removed.

    Lines without a marker are returned exactly as they were. A line made only of
    markers disappears together with one blank line next to it. If nothing but
    markers was written, the original text is returned rather than an empty answer.
    """
    lines = text.split("\n")
    kept: list[str] = []
    removed_at: list[int] = []  # indices into `kept` where a whole line vanished
    for line in lines:
        stripped, changed = _strip_line(line, registry)
        if changed and _is_empty(stripped):
            removed_at.append(len(kept))
            continue
        kept.append(stripped)
    result = "\n".join(_close_gaps(kept, removed_at))
    return result if result.strip() else text


def _strip_line(line: str, registry: Registry) -> tuple[str, bool]:
    groups = [g for g in _top_level_groups(line) if _is_citation(line[g[0] + 1 : g[1]], registry)]
    if not groups:
        return line, False
    out = ""
    pos = 0
    for start, end in groups:
        out += line[pos:start]
        if out.strip():
            out = out.rstrip(_HORIZONTAL_SPACE)
        pos = end + 1
        after = pos
        while after < len(line) and line[after] in _HORIZONTAL_SPACE:
            after += 1
        if not out.strip() or after == len(line) or line[after] in _PUNCTUATION:
            pos = after  # drop the space: line start, line end, or before punctuation
            if pos < len(line) and out.endswith(line[pos]):
                pos += 1  # "text. (marker)." keeps one full stop, not two
        elif after > pos or line[after].isalnum():
            out += " "  # exactly one space between the words around the marker
            pos = after
    out += line[pos:]
    return out.rstrip(), True


def _is_empty(line: str) -> bool:
    """Blank, or only a list marker left ("-", "*", "1.") after the markers went."""
    return _LIST_MARKER_ONLY.fullmatch(line) is not None


def _top_level_groups(line: str) -> list[tuple[int, int]]:
    """(open, close) index pairs of balanced groups not nested in another balanced group.

    An unmatched "(" or ")" is treated as a plain character, so a stray bracket
    neither hides a later marker nor makes an unclosed group removable."""
    stack: list[int] = []
    pairs: list[tuple[int, int]] = []
    for index, char in enumerate(line):
        if char == "(":
            stack.append(index)
        elif char == ")" and stack:
            pairs.append((stack.pop(), index))
    pairs.sort()
    top: list[tuple[int, int]] = []
    for start, end in pairs:
        if top and start < top[-1][1]:
            continue
        top.append((start, end))
    return top


def _split_top_level(content: str, separator: str) -> list[str]:
    parts: list[str] = []
    depth = 0
    current = ""
    for char in content:
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        if char == separator and depth == 0:
            parts.append(current)
            current = ""
        else:
            current += char
    parts.append(current)
    return parts


def _is_citation(content: str, registry: Registry) -> bool:
    """Every top-level ";" segment is "<car name>, <something>"."""
    for segment in _split_top_level(content, ";"):
        head, *rest = _split_top_level(segment, ",")
        if not rest or not ",".join(rest).strip() or not _is_car_name(head, registry):
            return False
    return True


def _is_car_name(raw: str, registry: Registry) -> bool:
    """The whole (normalized) text is exactly one corpus car name."""
    name = normalize(raw)
    mentions = car_mentions(name, registry)
    return len(mentions) == 1 and mentions[0][:2] == (0, len(name))


def _close_gaps(lines: list[str], removed_at: list[int]) -> list[str]:
    """Drop one blank line where a whole line vanished, so no empty paragraph is left."""
    result = list(lines)
    for index in sorted(set(removed_at), reverse=True):
        before_blank = index > 0 and not result[index - 1].strip()
        after_blank = index < len(result) and not result[index].strip()
        at_edge = index == 0 or index == len(result)
        if after_blank and (before_blank or index == 0):
            del result[index]
        elif before_blank and (after_blank or at_edge):
            del result[index - 1]
    return result
