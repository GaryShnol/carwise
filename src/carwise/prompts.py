"""The prompts of the two LLM calls, as named constants.

Why the text lives in versioned files (src/carwise/llm/prompts/<name>.v<N>.txt)
while code imports constants from here: a prompt change is a behavior change,
so it gets a new file and a new version that the telemetry records, and eval
runs stay comparable (CLAUDE.md section 12). Callers never touch the files.
"""

from __future__ import annotations

from pathlib import Path
from string import Template

from carwise.guardrails import escape_attribute, escape_text, one_line
from carwise.registry import Registry
from carwise.schemas import RetrievedChunk

PROMPT_DIR = Path(__file__).parent / "llm" / "prompts"
# Each prompt is versioned on its own, so changing one keeps the others comparable.
# generate v2 (CW-202): excerpts are one set of articles, no "in another article".
# generate v3 (CW-203): how to use the "User preferences" block for recommendations.
# regenerate v2 (CW-206): numbers exactly as the excerpts give them; show both operands.
# generate v4 (CW-302): compare figures under different labels and say so; correct a
# premise with the asked car's own figure; call the sources "the articles".
PROMPT_VERSIONS = {"understand": "v1", "generate": "v4", "regenerate": "v2"}


def _load(name: str) -> str:
    path = PROMPT_DIR / f"{name}.{PROMPT_VERSIONS[name]}.txt"
    return path.read_text(encoding="utf-8").strip()


# string.Template ($name) rather than str.format: prompt text may contain braces.
UNDERSTAND_SYSTEM_TEMPLATE = Template(_load("understand"))
GENERATE_SYSTEM = _load("generate")
REGENERATE_TEMPLATE = Template(_load("regenerate"))


def understand_system(registry: Registry) -> str:
    """The understand prompt with the registry inlined, so aliases resolve to ids."""
    lines = [f"- {car.id}: {', '.join(dict.fromkeys(car.aliases))}" for car in registry.cars]
    return UNDERSTAND_SYSTEM_TEMPLATE.substitute(car_registry="\n".join(lines))


def regenerate_instruction(problems: list[str]) -> str:
    """The follow-up user message of the one stricter retry after a failed post-check."""
    return REGENERATE_TEMPLATE.substitute(problems="; ".join(problems) + ".")


def generation_input(
    question: str,
    chunks: list[RetrievedChunk],
    not_covered: list[str],
    preferences: str = "",
) -> str:
    """The user message of the generate call: the question, then the excerpts as data.

    Every value from outside the code is escaped (CW-205): the question, the
    not-covered names and the preference values stay on their own line, and no
    text can close an excerpt or fake one with another car's id. `preferences`
    arrives as lines built by `preferences.prompt_block`, which escapes each value.
    """
    parts = [f"Question: {one_line(question)}"]
    if not_covered:
        parts.append(f"Cars the articles do not cover: {', '.join(map(one_line, not_covered))}")
    if preferences:
        parts.append(f"User preferences (stated by the user in this conversation):\n{preferences}")
    excerpts = [
        f'<excerpt id="{hit.chunk.chunk_id}" car="{escape_attribute(hit.chunk.car_name)}" '
        f'section="{escape_attribute(hit.chunk.section)}">\n'
        f"{escape_text(hit.chunk.text)}\n</excerpt>"
        for hit in chunks
    ]
    parts.append("<excerpts>\n" + "\n".join(excerpts) + "\n</excerpts>")
    return "\n\n".join(parts)
