# ADR 0001: LLM sampling controls and pricing

- **Status:** Accepted
- **Date:** 2026-10-30
- **Ticket:** CW-104
- **Evidence:** `scripts/llm_spike.py` (rerun with `uv run --env-file .env python scripts/llm_spike.py`)

## Context

CLAUDE.md section 9 asks for a low temperature (0 to 0.2) and a seed, and warns that some
OpenAI reasoning-model families reject a custom temperature; in that case we would fall back
to a low `reasoning_effort` plus a seed. The config profiles use `gpt-5.4-nano` (understanding,
and generation in `dev`) and `gpt-5.4-mini` (generation in `final`). The prices in
`config/settings.yaml` had been copied from a third-party source and needed checking.

## What the spike measured (2026-10-30, Chat Completions API)

Accepted parameters, with a short strict-JSON request:

| Setting | gpt-5.4-nano | gpt-5.4-mini |
|---|---|---|
| nothing sent (defaults) | accepted, 0 reasoning tokens | accepted, 0 reasoning tokens |
| `temperature=0`, with or without `seed` | accepted | accepted |
| `temperature=0.2` | accepted | accepted |
| `reasoning_effort=none` (also with `temperature=0`) | accepted, 0 reasoning tokens | accepted, 0 reasoning tokens |
| `reasoning_effort=minimal` | **rejected** (HTTP 400: supported values start at `none`, `low`) | **rejected** |
| `reasoning_effort=low` | accepted, 29 to 32 reasoning tokens | accepted, 17 reasoning tokens |

Usage fields returned by the API: `prompt_tokens`, `completion_tokens`, `total_tokens`,
`prompt_tokens_details.{cached_tokens, audio_tokens}`, and
`completion_tokens_details.{reasoning_tokens, accepted_prediction_tokens,
rejected_prediction_tokens, audio_tokens}`. `reasoning_tokens` is a subset of
`completion_tokens`, and OpenAI's reasoning guide states that reasoning tokens are billed as
output tokens. With `low` effort a 17-token reply became 40 to 55 output tokens, so the
reasoning setting does affect cost and latency.

Repeatability, with `temperature=0`, `seed=7` and `reasoning_effort=none`:

- An open-ended Hebrew sentence ("describe what matters when choosing a family car"): 3 runs,
  3 different outputs on both models.
- Grounded questions over a small synthetic context (a fact and a comparison): `gpt-5.4-nano`
  returned the same wording in all three profile runs; the "not mentioned" refusal varied in
  wording but was correct each time.

Hebrew sanity check (fact, comparison, refusal) on synthetic context: all 12 calls returned
valid JSON in Hebrew with the right facts and a correct refusal; 0.76 to 1.2 s per call; about
$0.00007 to $0.0001 per call on nano and $0.00024 to $0.00026 on mini at this prompt size.
One nano refusal repeated the JSON field name inside the answer text (`mentioned_in_context=false`),
a prompt-wording issue to handle in the generation prompt (CW-105).

## Pricing check

Verified on 2026-10-30 against <https://developers.openai.com/api/docs/pricing> (Standard tier,
USD per 1M tokens). **No difference** from `config/settings.yaml`:

| Model | Input | Cached input | Output |
|---|---|---|---|
| gpt-5.4-nano | 0.20 | 0.02 | 1.25 |
| gpt-5.4-mini | 0.75 | 0.075 | 4.50 |

Batch and Flex tiers are half price; we do not use them (interactive chat needs low latency).

## Decision

- Send `temperature: 0.0`, `seed: 7` and `reasoning_effort: none` on every call.
  `none` is sent explicitly, although it matches today's default, so a changed provider default
  cannot silently add reasoning tokens.
- The fallback described in CLAUDE.md (low effort plus seed instead of temperature) is not
  needed for these models. The config keeps all three controls optional (null means "not
  sent"), so a model that rejects one is a config change, not a code change.
- Prices stay as they are; the client refuses a model that has no price in config.

## Consequences

- Facts and sources are expected to be stable across runs; exact wording is not. The README's
  determinism section says this plainly, and the eval checks required facts and refusals,
  never exact sentences.
- With no reasoning tokens, a turn costs input plus a short output: well under one cent, in
  line with CLAUDE.md section 11.
- Revisit when the models change (rerun the spike) or if the answer eval shows that `low`
  effort fixes real failures that justify its extra output tokens.
