# docs

Reference material behind the main [README](../README.md). Each decision record (ADR) states
the context, what was measured, the decision and when it would change. The numbers in it come
from the committed reports under [`eval/reports/`](../eval/reports/).

## Decision records

| ADR | Decision | Ticket |
|---|---|---|
| [0001](decisions/0001-llm-sampling-controls.md) | LLM sampling controls (temperature 0, seed, `reasoning_effort: none`) and verified prices | CW-104 |
| [0002](decisions/0002-embedding-model.md) | Embedding model: `intfloat/multilingual-e5-large`, chosen from four retrieval set-ups | CW-305 |
| [0003](decisions/0003-retrieval-tuning.md) | Retrieval tuning: chunk window, forced spec boxes, k and caps, relevance threshold | CW-303, CW-306 |
| [0004](decisions/0004-answer-eval-and-generate-prompt.md) | Answer-level evaluation, and generate prompt v3 kept over v4 and v5 | CW-302 |

## Operations

| Document | Contents |
|---|---|
| [docker.md](docker.md) | The run line, what happens at first start, measured image size and start times, what the image contains |
| [ci.md](ci.md) | What each GitHub Actions workflow runs and when, its security choices, and the repository settings the owner applies |

## Elsewhere in the repository

- [`BOARD.md`](../BOARD.md): epics, tickets, acceptance criteria, Backlog and change log.
- [`CLAUDE.md`](../CLAUDE.md): the project guide the work followed (architecture, rules, scope).
- [`eval/reports/`](../eval/reports/): committed eval reports (metrics only, no answer text).
- [`CHANGELOG.md`](../CHANGELOG.md): release notes per tag.
