"""The prompts of the two LLM calls, as named constants.

Why the text lives in versioned files (src/carwise/llm/prompts/<name>.v<N>.txt)
while code imports constants from here: a prompt change is a behavior change,
so it gets a new file and a new version that the telemetry records, and eval
runs stay comparable (CLAUDE.md section 12). Callers never touch the files.
"""

from __future__ import annotations

from pathlib import Path
from string import Template

from carwise.registry import Registry
from carwise.schemas import RetrievedChunk

PROMPT_DIR = Path(__file__).parent / "llm" / "prompts"
PROMPT_VERSION = "v1"


def _load(name: str) -> str:
    return (PROMPT_DIR / f"{name}.{PROMPT_VERSION}.txt").read_text(encoding="utf-8").strip()


# string.Template ($name) rather than str.format: prompt text may contain braces.
UNDERSTAND_SYSTEM_TEMPLATE = Template(_load("understand"))
GENERATE_SYSTEM = _load("generate")


def understand_system(registry: Registry) -> str:
    """The understand prompt with the registry inlined, so aliases resolve to ids."""
    lines = [f"- {car.id}: {', '.join(dict.fromkeys(car.aliases))}" for car in registry.cars]
    return UNDERSTAND_SYSTEM_TEMPLATE.substitute(car_registry="\n".join(lines))


def generation_input(question: str, chunks: list[RetrievedChunk], not_covered: list[str]) -> str:
    """The user message of the generate call: the question, then the excerpts as data."""
    parts = [f"Question: {question}"]
    if not_covered:
        parts.append(f"Cars the articles do not cover: {', '.join(not_covered)}")
    excerpts = [
        f'<excerpt id="{hit.chunk.chunk_id}" car="{hit.chunk.car_name}" '
        f'section="{hit.chunk.section}">\n{hit.chunk.text}\n</excerpt>'
        for hit in chunks
    ]
    parts.append("<excerpts>\n" + "\n".join(excerpts) + "\n</excerpts>")
    return "\n\n".join(parts)
