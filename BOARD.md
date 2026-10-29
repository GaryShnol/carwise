# BOARD.md: carwise task board

Living task board for the project, kept in the repository like a lightweight Jira. It is the single source of truth for scope and progress. Rules for updating it are in `CLAUDE.md`, section 19.

**Last updated:** 2026-10-29
**Release target:** `v1.0`
**Effort budget:** the assignment suggests 3 to 5 hours, and the owner accepts more time in exchange for a solid result. Target: all P1 and P2 tickets (36 points, about 6 to 7 hours with Claude Code assistance); P3 only if time allows. Points: S = 1, M = 2, L = 3.

## How to use this board

1. Pick the next `TODO` ticket whose dependencies are `DONE`.
2. Work on the epic's branch (named in the epic header) and set the ticket to `IN PROGRESS`.
3. Commit with the ticket id in the message, for example `feat(CW-102): structure-aware chunking`, and set the ticket to `DONE` in the same commit.
4. When all tickets of the epic are done, open one pull request for the epic, merge it without squashing, and tag the release.
5. Never leave a stale status. Anything not on this board goes to the Backlog at the bottom, not into the code.

**Definition of done for every ticket:** the code and its unit tests are in the same commit series (LLM calls mocked); `make lint` and `make test` pass; new dependencies carry a one-line justification; the ticket status is updated; docstrings explain why, not what.

**Statuses:** `TODO` | `IN PROGRESS` | `IN REVIEW` | `DONE` | `BLOCKED` | `DEFERRED`
**Sizes:** S (about 15 to 30 min) | M (about 30 to 45 min) | L (about 1 hour or more)
**Priority (`Pri`):** P1 = required by the assignment | P2 = signals engineering maturity for the role | P3 = optional

## Scope tiers and the cut line

The assignment estimates 3 to 5 hours and asks for clarity and decisions rather than completeness. Extra hours are acceptable, but extra scope is not: more time goes into depth (eval quality, tests, README, tuning), not into new features. Scope is tiered; if time runs short, cut from the bottom: P3 first, then P2 from the end of the list.

| Tier | Meaning | Tickets | Points |
|---|---|---|---|
| P1 | Everything the assignment asks for, plus the evidence for it | 16 | 27 |
| P2 | Role signals: telemetry, injection hygiene, numeric check, embedding comparison, tuning, Docker, CI, GitHub setup | 8 | 9 |
| P3 | Nice to have: nothing at present | 0 | 0 |

A P1 ticket never depends on a P2 or P3 ticket, so cutting from the bottom never breaks the submission.

P1 alone is the submission: ingestion, retrieval, grounded answers with refusal, preference inference, a UI, an eval, a README and an example conversation.

## Assignment coverage

| Requirement from the assignment | Where it is covered |
|---|---|
| Ingest and understand the eight articles | CW-101, CW-102 |
| Searchable knowledge base | CW-103 |
| Natural, user-friendly conversation | CW-105, CW-401 |
| Gradually infer user preferences | CW-203, scenario in CW-106 |
| Answers grounded in retrieved content, no hallucination | CW-201, CW-202, CW-206, citations in CW-105 |
| Conversational interface of my choice | CW-105 (CLI), CW-401 (Streamlit) |
| Submit: code | CW-003, CW-503 |
| Submit: short explanation of approach and architecture | CW-501 (TL;DR) |
| Submit: example interaction | CW-502 |
| Sensible trade-offs and explanations | Decision table in CW-501, Backlog below |

## Open decisions and pre-work

Items outside the code that must not be forgotten. Update the status as each is settled.

| # | Item | Default if unanswered | Status |
|---|---|---|---|
| D1 | Interviewer questions (language, no-answer behavior, preference memory) | Answered by email on 2026-10-29: Hebrew only; do what is best for the user without outside information; preferences for one conversation only | DECIDED |
| D2 | LLM provider | Decided: OpenAI only. `dev` profile: `gpt-5.4-nano` for both calls; `final` profile: `gpt-5.4-nano` for understanding and `gpt-5.4-mini` for generation (confirmed by the answer eval). Ollama stays an optional offline runtime via `base_url`. Still needed from the owner: `OPENAI_API_KEY` as an environment variable. Prices to be verified on the official pricing page in CW-104 | DECIDED, key pending |
| D3 | Default embedding model | Local multilingual sentence-transformers model, confirmed by CW-305 | OPEN |
| D4 | Repository visibility | Public (decided); raw articles never committed | DECIDED |
| D5 | Fetch fallback | Script download; private archive sent to the interviewer | DECIDED |
| D6 | Submission format (repository link, short cover email) | Link plus a three-line email | OPEN |

## Progress summary

| Epic | Milestone / tag | Tickets | Done | Points | Status |
|---|---|---|---|---|---|
| E0 Scaffold and source check | none | 3 | 1 | 3 | IN PROGRESS |
| E1 Thin vertical slice | `v0.1` | 6 | 0 | 11 | TODO |
| E2 Reliability and guardrails | none | 6 | 0 | 9 | TODO |
| E3 Measurement | none | 3 | 0 | 5 | TODO |
| E4 Interface and packaging | none | 3 | 0 | 4 | TODO |
| E5 Documentation and release | `v1.0` | 3 | 0 | 4 | TODO |
| **Total** |  | **24** | **0** | **36** |  |

## Epic E0: Scaffold and source check

Goal: a clean repository skeleton, and certainty about whether the source articles can be fetched automatically.

Branch: CW-001 was committed to `main` (first scaffold commit); the rest of E0 uses `epic/e0-source-check` | Tag: none

| ID | Ticket | Type | Size | Pri | Status | Depends on |
|---|---|---|---|---|---|---|
| CW-001 | Repository scaffold | `chore` | S | P1 | DONE |  |
| CW-002 | Source access check (spike) | `chore` | S | P1 | IN PROGRESS | CW-001 |
| CW-003 | GitHub setup: repo, milestones, issues, PR template | `chore` | S | P2 | TODO | CW-001 |

## Epic E1: Thin vertical slice

Goal: a rough but working bot, end to end, from raw articles to a grounded answer in the command line, plus the eval question set that guides everything after it.

Branch: `epic/e1-vertical-slice` | Tag: `v0.1`

| ID | Ticket | Type | Size | Pri | Status | Depends on |
|---|---|---|---|---|---|---|
| CW-101 | Download script, cache and clean the eight articles | `feat` | S | P1 | TODO | CW-002 |
| CW-102 | Structure-aware chunking with metadata | `feat` | M | P1 | TODO | CW-101 |
| CW-103 | Embeddings, Chroma index, per-car retrieval | `feat` | M | P1 | TODO | CW-102 |
| CW-104 | `LLMClient` interface and one implementation | `feat` | S | P1 | TODO | CW-001 |
| CW-105 | Basic pipeline (understand, generate) and CLI | `feat` | L | P1 | TODO | CW-103, CW-104 |
| CW-106 | Eval question set (about 15, with trap questions), written before the guardrails | `feat` | M | P1 | TODO | CW-102 |

## Epic E2: Reliability and guardrails

Goal: the model is bounded by code at every point where it could err.

Branch: `epic/e2-reliability` | Tag: none

| ID | Ticket | Type | Size | Pri | Status | Depends on |
|---|---|---|---|---|---|---|
| CW-201 | Relevance gate and fixed refusal | `feat` | M | P1 | TODO | CW-105 |
| CW-202 | Post-check for cars not retrieved this turn | `feat` | M | P1 | TODO | CW-105 |
| CW-203 | Preference model and `/prefs` command | `feat` | M | P1 | TODO | CW-105 |
| CW-204 | Turn telemetry and cost estimate | `feat` | S | P2 | TODO | CW-105 |
| CW-205 | Injection hygiene and input limits | `feat` | S | P2 | TODO | CW-105 |
| CW-206 | Numeric claim check in post-check | `feat` | S | P2 | TODO | CW-202 |

## Epic E3: Measurement

Goal: prove it works, and tune parameters with data instead of guesses.

Branch: `epic/e3-measurement` | Tag: none

| ID | Ticket | Type | Size | Pri | Status | Depends on |
|---|---|---|---|---|---|---|
| CW-302 | Eval runner and per-category report | `feat` | M | P1 | TODO | CW-201, CW-202, CW-106 |
| CW-305 | Embedding model comparison on the retrieval eval | `feat` | M | P2 | TODO | CW-302 |
| CW-303 | Tune relevance threshold, top-k and chunk size | `fix` | S | P2 | TODO | CW-302, CW-305 |

## Epic E4: Interface and packaging

Goal: something to show, and a way to run it with one command.

Branch: `epic/e4-interface-packaging` | Tag: none

| ID | Ticket | Type | Size | Pri | Status | Depends on |
|---|---|---|---|---|---|---|
| CW-401 | Streamlit UI in Hebrew, right to left (chat, preferences panel, sources, cost) | `feat` | M | P1 | TODO | CW-203 |
| CW-402 | Dockerfile and run command | `feat` | S | P2 | TODO | CW-401 |
| CW-403 | GitHub Actions: lint, tests, retrieval eval | `ci` | S | P2 | TODO | CW-302, CW-003 |

## Epic E5: Documentation and release

Goal: the README carries half of the grade; make it count.

Branch: `epic/e5-docs-release` | Tag: `v1.0`

| ID | Ticket | Type | Size | Pri | Status | Depends on |
|---|---|---|---|---|---|---|
| CW-501 | README: architecture, decision table, not-built list, AWS mapping | `docs` | M | P1 | TODO | CW-302 |
| CW-502 | Example conversation and eval results in README | `docs` | S | P1 | TODO | CW-302, CW-501 |
| CW-503 | Release `v1.0` | `chore` | S | P1 | TODO | all |

## Ticket details and acceptance criteria

### CW-001 Repository scaffold
- [x] Folder layout matches `CLAUDE.md` section 6.
- [x] `pyproject.toml` with pinned dependencies; `Makefile` with `ingest`, `chat`, `ui`, `eval`, `test`, `lint`, `docker`.
- [x] `config/settings.yaml` created; `.env.example` lists the required variables (profile, `OPENAI_API_KEY`, optional base URL override; no secrets).
- [x] `python -m app <ingest|chat|eval|ui>` is the primary entry point; the `Makefile` only wraps it, so everything works in PowerShell without `make`. Python 3.11 or newer, managed with `uv`.
- [x] `.gitignore` excludes `data/raw/`, `data/index/`, `logs/` and `.env`.
- [x] `ruff` configured; `make lint` and `make test` run (even if empty).
- [x] `LICENSE` (MIT) added.

### CW-002 Source access check (spike)
- [ ] Each of the eight URLs is fetched once programmatically, or the failure is documented.
- [ ] Robots rules checked and respected; a block is never worked around.
- [ ] Decision recorded in the commit message and in the README data note: automated download, or the user supplies the files manually.
- [ ] Fallback message drafted for the case where the download fails.

### CW-003 GitHub setup
- [ ] Public repository created, named `carwise`.
- [ ] Pre-publish check: no secrets, no `.env`, no raw articles, no logs or index in the history.
- [ ] One GitHub milestone per epic. No per-ticket issues: this board is the single source of truth, and commits reference ticket ids.
- [ ] `.github/pull_request_template.md` for epic pull requests: tickets completed, key decisions with the alternative considered, how verified, measurements.
- [ ] Branch protection on `main` requires a pull request and green CI once CI exists (CW-403).

### CW-101 Download script, cache and clean the eight articles
- [ ] `config/cars.yaml` lists the eight cars: canonical id, display name, Hebrew and Latin-script aliases, body type and powertrain (as stated in the articles), URL.
- [ ] Script reads the URL list from the car registry and saves raw HTML under `data/raw/` (not committed).
- [ ] Polite fetching: identifiable User-Agent, short delay, one retry, clear error message with manual-placement instructions.
- [ ] A second run uses the cache and works offline.
- [ ] Cleaning yields body text only and keeps headings and paragraph breaks.

### CW-102 Structure-aware chunking with metadata
- [ ] Splits on headings and paragraphs; merges too-short and splits too-long chunks per config.
- [ ] Handles both article formats among the eight (road tests and the Kia EV9 long-term report); publication date is stored as metadata when the page shows it.
- [ ] Every chunk has `car` (a canonical id from the registry), `section`, `source_url`, `chunk_id`.
- [ ] Unit tests: structure preserved, metadata present, no empty chunks.

### CW-103 Embeddings, Chroma index, per-car retrieval
- [ ] Multilingual embedding model with Hebrew support; version pinned in config.
- [ ] `make ingest` builds the index; retrieval is deterministic for the same query.
- [ ] Retrieval can filter by car and returns similarity scores.
- [ ] Unit tests: per-car filter returns only that car.

### CW-104 `LLMClient` interface and one implementation
- [ ] Interface with `complete()` (supports structured output) and `embed()` if needed.
- [ ] One implementation over the official OpenAI SDK with a configurable `base_url`; it serves OpenAI by default, and any OpenAI-compatible server (for example Ollama at `http://localhost:11434/v1`) as an option.
- [ ] Config profiles `dev` (local) and `final` (OpenAI), selected by an environment variable or flag; keys from environment only.
- [ ] Structured output is always validated with Pydantic, because local models are less reliable at following a schema.
- [ ] Profiles: `dev` = `gpt-5.4-nano` for both calls; `final` = `gpt-5.4-nano` for understanding and `gpt-5.4-mini` for generation. Names and prices live in config.
- [ ] Spike, documented in the commit message: does the chosen model accept a custom temperature? If not, use a low `reasoning_effort` plus a seed and note it in the README (determinism section). Check that reasoning tokens do not inflate cost, and verify prices on the official OpenAI pricing page.
- [ ] Three-prompt Hebrew sanity check (a fact, a comparison, a refusal) with the chosen models.
- [ ] Timeouts and one retry; a fake client exists for tests.

### CW-105 Basic pipeline and CLI
- [ ] `pipeline.answer(message, session) -> Response` is the single entry point.
- [ ] Prompts live in versioned text files, not in code.
- [ ] Understand call returns intent, cars (canonical ids), standalone query, preference updates (validated by Pydantic); invalid output gets one retry, then falls back to using the raw message as the query.
- [ ] The understand schema includes `unrecognized_cars` (raw names of cars that match no registry entry), and generation returns JSON with `answer` and `used_chunk_ids`; ids not retrieved this turn are rejected in code.
- [ ] History window size comes from config.
- [ ] Chitchat and out-of-scope intents skip retrieval and reply briefly with what the bot can do.
- [ ] All replies are in Hebrew; the first message states that knowledge is limited to the eight reviewed cars; tone is friendly and concise.
- [ ] Comparison questions retrieve separately per car.
- [ ] The understand schema already contains the preference-update field; merging and using preferences is implemented in CW-203.
- [ ] Generated answers cite car and section; CLI chat works end to end.
- [ ] Unit tests with the fake `LLMClient`: intent handling, fallback on invalid output, chitchat skipping retrieval.

### CW-106 Eval question set
- [ ] About 15 questions in `eval/questions.yaml`, written after reading the articles and before building the guardrails and tuning, so the eval guides the work.
- [ ] Categories: single-car facts, two-car comparisons, preference-driven recommendations, ranking questions across all cars, history-dependent follow-ups.
- [ ] At least one scripted multi-turn scenario in which preferences accumulate and the final recommendation reflects them.
- [ ] At least 4 trap questions: car not in the corpus, detail never mentioned, a mixing trap, and one more of the author's choice.
- [ ] Each question states what must hold (cars, required fact or keyword, or expected refusal), not a full reference answer.
- [ ] Each answerable question also records the expected car and section for the retrieval eval.

### CW-201 Relevance gate and fixed refusal
- [ ] Below-threshold score, or a car that is not in the car registry, returns a fixed refusal without the generation call.
- [ ] The registry check, including `unrecognized_cars`, is the primary gate; the threshold is tuned on the eval, which includes near-miss questions (a known car, a detail the articles never mention).
- [ ] The reply is templated and filled in by code: it says plainly what the articles do not cover, then suggests the closest cars among the eight (by body type and powertrain from the registry, or by the best-scoring chunks) and invites a follow-up question.
- [ ] No outside knowledge is ever added; for a known car with a missing detail the generation step says "not mentioned in the articles" and offers the closest related facts from the chunks.
- [ ] Unit tests: refuses below threshold; refuses unknown car.

### CW-202 Post-check
- [ ] A car named in the answer is acceptable only if it was retrieved this turn or appears in the text of the retrieved chunks (articles may mention rival cars legitimately); otherwise the answer is suspect.
- [ ] Name matching normalizes Hebrew prefixes, and a small configurable list of well-known brands outside the corpus is also checked.
- [ ] Suspect answers are regenerated once with a stricter instruction, or replaced with a safe fallback.
- [ ] Unit tests cover the flagged case, the clean case, and a rival car mentioned in a retrieved chunk.

### CW-203 Preference model and `/prefs`
- [ ] Typed preference object updated every turn; each field records its source message.
- [ ] `/prefs` prints the current profile; preferences last for one conversation only.
- [ ] Preferences may shape recommendation queries but never override grounding.
- [ ] Unit tests: updates merge across turns, a later statement overrides an earlier one, and each field keeps its source message.

### CW-204 Turn telemetry and cost estimate
- [ ] One JSON line per turn: chunk ids, scores, intent, tokens in and out, estimated cost, latency, post-check result.
- [ ] Prices come from config (zero for local models); secrets are never logged.
- [ ] Unit test for the cost calculation (tokens times configured price).
- [ ] Each line records the profile and model name; a `max_cost_usd` cap in config aborts a run (eval or chat session) when exceeded.

### CW-205 Injection hygiene and input limits
- [ ] System prompt states that article text is data, never instructions.
- [ ] Message length limit and a polite refusal for out-of-domain requests.
- [ ] Unit tests: over-long input is rejected politely; an instruction planted in a chunk is not followed.

### CW-206 Numeric claim check
- [ ] Every number in an answer (horsepower, price, consumption, dimensions) must appear in the retrieved chunks.
- [ ] A missing number marks the answer as suspect and feeds the same regenerate-or-fallback path as CW-202.
- [ ] Unit tests: matching numbers pass; an invented number is flagged; formatting differences (commas, units) are handled.

### CW-302 Eval runner and per-category report
- [ ] Retrieval eval (no LLM, deterministic, free): expected car and section among retrieved chunks.
- [ ] Answer eval: required keywords, refusal detected, no car outside the retrieved set.
- [ ] Each question runs several times; report shows stability and pass rate per category, plus tokens and cost of the run.
- [ ] The report records the profile and model name; the retrieval eval is provider-independent and runs locally for free.
- [ ] The answer eval runs on the local profile during development and once or twice on the `final` profile near the end; the `final` run supplies the published numbers.

### CW-305 Embedding model comparison
- [ ] At least two multilingual candidates that support Hebrew are compared on the retrieval eval.
- [ ] Result table (hit rate per category) and the chosen model are recorded for the README.
- [ ] The model name and version are pinned in config.

### CW-303 Tune relevance threshold, top-k and chunk size
- [ ] Values chosen from eval results (retrieval-based tuning locally; a confirmation run on the `final` profile); before and after numbers in the commit message and in the E3 pull request description.
- [ ] Chosen values and the reasoning recorded for the README.

### CW-401 Streamlit UI
- [ ] Chat window, side panel with the live preference profile.
- [ ] All text is Hebrew and renders right to left (`dir="rtl"`); Latin-script car names such as EV9 or GV80 inside Hebrew sentences stay readable.
- [ ] Command-line output is checked in a common terminal; any limitation is noted in the README.
- [ ] Expandable list of retrieved chunks under each answer (car, section, score).
- [ ] Tokens and estimated cost line per answer (from the CW-204 telemetry when it exists); distinct visual state for refusals.
- [ ] No business logic in the UI; it only calls `pipeline.answer`.

### CW-402 Dockerfile and run command
- [ ] Slim Python base, installs from `pyproject.toml`, default command starts the UI.
- [ ] One documented `docker run` line; the key is passed as an environment variable.

### CW-403 GitHub Actions
- [ ] Workflow runs lint, unit tests and the retrieval eval.
- [ ] The articles are downloaded in CI or restored from the Actions cache; if the site blocks CI, only unit tests on small fixtures run and this is documented.
- [ ] Answer eval runs only when `OPENAI_API_KEY` is configured and is triggered manually, not on every push; documented in the README.
- [ ] Branch protection on `main` requires green CI.

### CW-501 README
- [ ] Problem statement and run instructions (three commands at most).
- [ ] Architecture in plain language; decision table (decision, alternative, reason, when it changes).
- [ ] "Deliberately not built" section and the AWS production mapping.
- [ ] A TL;DR under one page at the top: approach, architecture in five lines, three key decisions.
- [ ] Determinism trade-off stated honestly; assumptions listed.
- [ ] Honest notes: time actually spent, what would be cut or added with more time, how AI tooling was used, and a copyright notice for the articles.
- [ ] Data note: articles are downloaded by `make ingest`, are not in the repository, and can be placed manually in `data/raw/`.
- [ ] Quotes from the articles are short, with the source named; the repository is public.
- [ ] Embedding model choice backed by the comparison from CW-305, and tuned values from CW-303, when those tickets are done; otherwise the README states the defaults and that they were not tuned.

### CW-502 Example conversation and eval results
- [ ] Sample conversation, produced with the `final` (OpenAI) profile, shows preferences inferred over several turns, a comparison and a refusal; article excerpts stay short (public repository).
- [ ] One UI screenshot included.
- [ ] Eval pass rate per category and known failure cases stated honestly.

### CW-503 Release `v1.0`
- [ ] All tickets `DONE` or `DEFERRED` with a reason.
- [ ] `make ingest`, `make chat`, `make ui`, `make eval` run from a clean checkout.
- [ ] Private archive of the raw articles prepared for the interviewer (outside the public repository).
- [ ] Final scan of the public history for secrets and copied article text.
- [ ] Short cover message for the interviewer drafted (repository link, how to run in three commands, where the TL;DR is).
- [ ] Tag `v1.0` on `main`.

## Backlog (not committed)

Ideas that are out of scope unless promoted to a ticket with a reason.

| Idea | Why it is not in scope | Promote when |
|---|---|---|
| Hybrid search (keywords plus embeddings) | Adds complexity without evidence of need | Eval shows model names or numbers are missed |
| Reranker | Corpus is small | Right car is retrieved but ranked too low |
| LLM judge for groundedness | Imperfect and costs tokens | Keyword checks prove too coarse |
| Second LLM provider (for example Bedrock) | One provider is enough | Provider switching becomes a requirement |
| Cross-session memory | Out of scope for a proof of concept | Persistent users are required |
| Agent loop with tools | Flow is linear | Live prices or external tools are needed |

## Change log

| Date | Change |
|---|---|
| 2026-10-28 | Board created with 22 tickets across 6 epics. |
| 2026-10-28 | Added CW-003, CW-206, CW-305, CW-404 (26 tickets, 38 points). Raw articles are no longer committed: download script plus private archive. |
| 2026-10-28 | Branching simplified: one branch per epic (E1 to E5), E0 on `main`, one commit series per ticket, one pull request per epic. The Branch and PR columns were replaced by a commit Type column. |
| 2026-10-28 | Decision: more hours are acceptable than the suggested 3 to 5; target is P1 and P2, with no new scope beyond the board. |
| 2026-10-28 | Audit against the assignment: added priority tiers, coverage table, open decisions, car registry, post-check rule for rival cars, chitchat path, multi-turn eval scenario, TL;DR and honesty notes in README. |
| 2026-10-28 | Decision: the repository is public. Added publication checks to CW-003, CW-501, CW-502 and CW-503. |
| 2026-10-29 | Local runtime decided: Ollama. Installed candidates noted in CW-104: gpt-oss:20b, qwen3:4b-instruct, DictaLM-3.0-1.7B. |
| 2026-10-29 | LLM provider decided: local OpenAI-compatible server for development and OpenAI toward the end, to save cost. One `LLMClient` implementation with a configurable `base_url`, profiles `dev` and `final`, a cost cap per run, and the published numbers and sample conversation produced on `final`. |
| 2026-10-29 | Interviewer answered: Hebrew only; no-answer behavior is at our discretion but without outside information; preferences for one conversation. Dropped English handling and the English eval category, made the no-answer reply helpful and templated, added body type and powertrain to the car registry, promoted CW-404 (right-to-left) to P2. |
| 2026-10-29 | Feature breakdown review: P1 no longer depends on P2 (UI no longer depends on telemetry, README no longer depends on tuning); eval question set moved to E1 as CW-106 so the eval guides the work; the "close test gaps" ticket removed because tests ship with each ticket; right-to-left merged into the UI ticket; per-ticket GitHub issues dropped (one source of truth). Now 24 tickets, 36 points. |
| 2026-10-29 | Architecture review: added `unrecognized_cars`, JSON generation output with `used_chunk_ids`, registry as the primary gate, Hebrew-prefix and out-of-corpus brand handling in the post-check; CW-206 promoted from P3 to P2 (P1+P2 is now 36 points). |
| 2026-10-29 | Provider decision revised: OpenAI only. `dev` = `gpt-5.4-nano`; `final` = nano for understanding and mini for generation. Ollama is optional. Entry point is `python -m app`, the Makefile is a thin wrapper. Tags reduced to `v0.1` and `v1.0`. |
| 2026-10-29 | CW-001 done. Entry point is `python -m app <ingest|chat|eval|ui>` (not `python -m carwise`), so the core package never imports from `app/` or `eval/`. `LICENSE` (MIT), `.gitignore` and a short `README.md` came from the repository's initial commit and were kept. |
| 2026-10-29 | Branching tightened: after the first scaffold commit (CW-001) nothing goes to `main` directly. Rest of E0 uses `epic/e0-source-check`; every epic gets a pull request. |
