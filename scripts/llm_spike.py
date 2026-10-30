"""CW-104 spike: which sampling controls do the configured models accept?

Run:  uv run --env-file .env python scripts/llm_spike.py
Cost: a few dozen tiny requests, well under one cent.

It answers four questions for every model named in the config profiles and
prints the raw evidence, which is summarized in
docs/decisions/0001-llm-sampling-controls.md:
1. Is a custom temperature accepted? With a seed? Which reasoning_effort values?
2. Which usage fields does the API return (cached and reasoning tokens)?
3. How many reasoning tokens does a short structured reply cost per effort level?
4. With the candidate setting, do repeated identical requests give identical JSON?
It ends with a three-prompt Hebrew sanity check (fact, comparison, refusal)
through carwise's own OpenAIClient, on synthetic context, not article text.

Lives in scripts/, not src/: a one-off measurement, not part of the product.
The API key is read by the SDK from the environment and never printed.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

import openai
from openai import OpenAI
from pydantic import BaseModel

from carwise.config import load_settings
from carwise.llm.base import LLMError
from carwise.llm.openai_client import OpenAIClient, response_format

REPEATS = 3
SEED = 7


class Probe(BaseModel):
    ok: bool
    word: str


PROBE_MESSAGES: list[Any] = [
    {"role": "system", "content": "Reply with JSON only."},
    {"role": "user", "content": 'Set ok to true and word to the Hebrew word for "car".'},
]

VARIANTS: dict[str, dict[str, Any]] = {
    "defaults (nothing sent)": {},
    "temperature=0": {"temperature": 0},
    "temperature=0 + seed": {"temperature": 0, "seed": SEED},
    "temperature=0.2": {"temperature": 0.2},
    "reasoning_effort=none": {"reasoning_effort": "none"},
    "reasoning_effort=none + temperature=0": {"reasoning_effort": "none", "temperature": 0},
    "reasoning_effort=minimal": {"reasoning_effort": "minimal"},
    "reasoning_effort=low": {"reasoning_effort": "low"},
    "reasoning_effort=low + seed": {"reasoning_effort": "low", "seed": SEED},
}


def probe(sdk: OpenAI, model: str, params: dict[str, Any]) -> tuple[str, Any]:
    try:
        response = sdk.chat.completions.create(
            model=model, messages=PROBE_MESSAGES, response_format=response_format(Probe), **params
        )
    except openai.BadRequestError as error:
        return f"REJECTED: {error.message[:160]}", None
    except openai.APIError as error:
        return f"ERROR {type(error).__name__}", None
    return "accepted", response


def usage_fields(response: Any) -> dict[str, Any]:
    return response.usage.model_dump(exclude_none=True) if response.usage else {}


def reasoning(response: Any) -> int:
    details = response.usage.completion_tokens_details if response.usage else None
    return (details.reasoning_tokens or 0) if details else 0


def check_model(sdk: OpenAI, model: str) -> dict[str, dict[str, Any]]:
    print(f"\n=== {model}")
    accepted: dict[str, dict[str, Any]] = {}
    for name, params in VARIANTS.items():
        status, response = probe(sdk, model, params)
        extra = ""
        if response is not None:
            accepted[name] = params
            usage = response.usage
            extra = (
                f" | in {usage.prompt_tokens} out {usage.completion_tokens}"
                f" (reasoning {reasoning(response)})"
                if usage
                else ""
            )
            if name == "defaults (nothing sent)":
                print(f"  raw usage fields: {json.dumps(usage_fields(response))}")
        print(f"  {name:<40} {status}{extra}")
    return accepted


def candidate(accepted: dict[str, dict[str, Any]]) -> tuple[str, dict[str, Any]] | None:
    """Preference order from CLAUDE.md section 9: low temperature + seed, else low effort + seed."""
    for name in (
        "reasoning_effort=none + temperature=0",
        "temperature=0 + seed",
        "temperature=0",
        "reasoning_effort=low + seed",
        "reasoning_effort=low",
    ):
        if name in accepted:
            params = dict(accepted[name])
            params.setdefault("seed", SEED)
            return name, params
    return None


def check_repeatability(sdk: OpenAI, model: str, params: dict[str, Any]) -> None:
    messages: list[Any] = [
        {"role": "system", "content": "Answer in Hebrew in one sentence. Reply with JSON only."},
        {"role": "user", "content": "תאר במשפט אחד מה חשוב בבחירת רכב משפחתי."},
    ]

    class Sentence(BaseModel):
        answer: str

    outputs = []
    for _ in range(REPEATS):
        try:
            response = sdk.chat.completions.create(
                model=model, messages=messages, response_format=response_format(Sentence), **params
            )
        except openai.APIError as error:
            print(f"  repeatability with {params}: request failed ({type(error).__name__})")
            return
        outputs.append(response.choices[0].message.content)
    distinct = len(set(outputs))
    print(f"  repeatability with {params}: {REPEATS} runs, {distinct} distinct outputs")


class SanityAnswer(BaseModel):
    answer: str
    mentioned_in_context: bool


SANITY_SYSTEM = (
    "You answer questions about cars using ONLY the context in the user message. "
    "Answer in Hebrew, briefly. If the context does not contain the answer, say that "
    "it is not mentioned and set mentioned_in_context to false."
)
SANITY_CONTEXT = (
    "הקשר (סינתטי): רכב א' - מנוע של 150 כוח סוס, מחיר 160 אלף ש\"ח. "
    'רכב ב\' - חשמלי, טווח של 450 ק"מ, מחיר 210 אלף ש"ח.'
)
SANITY_QUESTIONS = {
    "fact": "כמה כוח סוס יש לרכב א'?",
    "comparison": "איזה רכב זול יותר, א' או ב'?",
    "refusal": "מה צריכת הדלק של רכב ג'?",
}


def hebrew_sanity() -> None:
    settings = load_settings()
    client = OpenAIClient(settings)
    for profile_name, profile in settings.profiles.items():
        for role, model in (
            ("understand", profile.understand_model),
            ("generate", profile.generate_model),
        ):
            print(f"\n=== Hebrew sanity: profile {profile_name}, {role} model {model}")
            for kind, question in SANITY_QUESTIONS.items():
                message = {"role": "user", "content": f"{SANITY_CONTEXT}\nשאלה: {question}"}
                try:
                    result = client.complete_json(
                        SANITY_SYSTEM, [message], SanityAnswer, model=model
                    )
                except LLMError as error:
                    print(f"  {kind:<10} FAILED: {error}")
                    continue
                reply = result.parsed
                print(
                    f"  {kind:<10} mentioned={reply.mentioned_in_context!s:<5} "
                    f"in/out/reasoning {result.usage.input_tokens}/{result.usage.output_tokens}/"
                    f"{result.usage.reasoning_tokens} ${result.cost_usd:.6f} "
                    f"{result.latency_ms:.0f}ms | {reply.answer}"
                )
    print(f"\nHebrew sanity total cost: ${client.total_cost_usd:.6f}")


def main() -> int:
    if not os.environ.get("OPENAI_API_KEY"):
        print("OPENAI_API_KEY is not set; run: uv run --env-file .env python scripts/llm_spike.py")
        return 1
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    settings = load_settings()
    sdk = OpenAI(timeout=settings.llm.timeout_s, max_retries=settings.llm.retries)
    models = sorted(
        {m for p in settings.profiles.values() for m in (p.understand_model, p.generate_model)}
    )
    for model in models:
        accepted = check_model(sdk, model)
        chosen = candidate(accepted)
        if chosen is None:
            print("  no candidate setting accepted")
            continue
        print(f"  candidate: {chosen[0]} (+ seed)")
        check_repeatability(sdk, model, chosen[1])
    print(
        f"\nconfig now sends: temperature={settings.llm.temperature} "
        f"reasoning_effort={settings.llm.reasoning_effort} seed={settings.llm.seed}"
    )
    hebrew_sanity()
    return 0


if __name__ == "__main__":
    sys.exit(main())
