# BOARD.md: carwise task board

Living task board for the project, kept in the repository like a lightweight Jira. It is the single source of truth for scope and progress. Rules for updating it are in `CLAUDE.md`, section 19.

**Last updated:** 2026-10-30
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
| D2 | LLM provider | Decided: OpenAI only. `dev` profile: `gpt-5.4-nano` for both calls; `final` profile: `gpt-5.4-nano` for understanding and `gpt-5.4-mini` for generation (confirmed by the answer eval). Ollama stays an optional offline runtime via `base_url`. `OPENAI_API_KEY` provided by the owner in a local `.env` (gitignored). Prices verified on the official pricing page in CW-104 (no difference) | DECIDED |
| D3 | Default embedding model | Local multilingual sentence-transformers model, confirmed by CW-305 | OPEN |
| D4 | Repository visibility | Public (decided); raw articles never committed | DECIDED |
| D5 | Fetch fallback | Script download; private archive sent to the interviewer | DECIDED |
| D6 | Submission format (repository link, short cover email) | Link plus a three-line email | OPEN |

## Progress summary

| Epic | Milestone / tag | Tickets | Done | Points | Status |
|---|---|---|---|---|---|
| E0 Scaffold and source check | none | 3 | 3 | 3 | DONE |
| E1 Thin vertical slice | `v0.1` | 6 | 6 | 11 | DONE |
| E2 Reliability and guardrails | none | 6 | 1 | 9 | IN PROGRESS |
| E3 Measurement | none | 3 | 0 | 5 | TODO |
| E4 Interface and packaging | none | 3 | 0 | 4 | TODO |
| E5 Documentation and release | `v1.0` | 3 | 0 | 4 | TODO |
| **Total** |  | **24** | **10** | **36** |  |

## Epic E0: Scaffold and source check

Goal: a clean repository skeleton, and certainty about whether the source articles can be fetched automatically.

Branch: CW-001 was committed to `main` (first scaffold commit); the rest of E0 uses `epic/e0-source-check` | Tag: none

| ID | Ticket | Type | Size | Pri | Status | Depends on |
|---|---|---|---|---|---|---|
| CW-001 | Repository scaffold | `chore` | S | P1 | DONE |  |
| CW-002 | Source access check (spike) | `chore` | S | P1 | DONE | CW-001 |
| CW-003 | GitHub setup: repo, milestones, issues, PR template | `chore` | S | P2 | DONE | CW-001 |

## Epic E1: Thin vertical slice

Goal: a rough but working bot, end to end, from raw articles to a grounded answer in the command line, plus the eval question set that guides everything after it.

Branch: `epic/e1-vertical-slice` | Tag: `v0.1`

| ID | Ticket | Type | Size | Pri | Status | Depends on |
|---|---|---|---|---|---|---|
| CW-101 | Download script, cache and clean the eight articles | `feat` | S | P1 | DONE | CW-002 |
| CW-102 | Structure-aware chunking with metadata | `feat` | M | P1 | DONE | CW-101 |
| CW-103 | Embeddings, Chroma index, per-car retrieval | `feat` | M | P1 | DONE | CW-102 |
| CW-104 | `LLMClient` interface and one implementation | `feat` | S | P1 | DONE | CW-001 |
| CW-105 | Basic pipeline (understand, generate) and CLI | `feat` | L | P1 | DONE | CW-103, CW-104 |
| CW-106 | Eval question set (about 15, with trap questions), written before the guardrails | `feat` | M | P1 | DONE | CW-102 |

## Epic E2: Reliability and guardrails

Goal: the model is bounded by code at every point where it could err.

Branch: `epic/e2-reliability` | Tag: none

| ID | Ticket | Type | Size | Pri | Status | Depends on |
|---|---|---|---|---|---|---|
| CW-201 | Relevance gate and fixed refusal | `feat` | M | P1 | DONE | CW-105 |
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
- [x] Each of the eight URLs is fetched once programmatically, or the failure is documented.
- [x] Robots rules checked and respected; a block is never worked around.
- [x] Decision recorded in the commit message and in the README data note: automated download, or the user supplies the files manually. (Recorded in the commit message and the change log; the README data note is written in CW-501.)
- [x] Fallback message drafted for the case where the download fails.

### CW-003 GitHub setup
- [x] Public repository created, named `carwise`.
- [x] Pre-publish check: no secrets, no `.env`, no raw articles, no logs or index in the history.
- [x] One GitHub milestone per epic. No per-ticket issues: this board is the single source of truth, and commits reference ticket ids.
- [x] `.github/pull_request_template.md` for epic pull requests: tickets completed, key decisions with the alternative considered, how verified, measurements.
- [x] Branch protection on `main` requires a pull request and green CI once CI exists (CW-403). (Protection requires a pull request now; the green-CI requirement is added with CW-403.)

### CW-101 Download script, cache and clean the eight articles
- [x] `config/cars.yaml` lists the eight cars: canonical id, display name, Hebrew and Latin-script aliases, body type and powertrain (as stated in the articles), URL.
- [x] Script reads the URL list from the car registry and saves raw HTML under `data/raw/` (not committed).
- [x] Polite fetching: identifiable User-Agent, short delay, one retry, clear error message with manual-placement instructions.
- [x] A second run uses the cache and works offline.
- [x] Cleaning yields body text only and keeps headings and paragraph breaks.
- [x] Findings from the CW-002 probe, to be used by the cleaner: the article body is inside `<main>` and ends at the `כתבות אחרונות` heading; boilerplate headings to skip are the WhatsApp prompt, `תפריט מהיר`, `המומחה האובייקטיבי…`, `כתבות באותם נושאים`, `מותגים מתחרים` and empty headings; the publication date is in the JSON-LD `datePublished`.
- [x] The Kia EV9 long-term report has almost no section headings (unlike the road tests, which have about 10 question-style headings), so its chunks fall back to paragraph structure, with the report title as the section.

### CW-102 Structure-aware chunking with metadata
- [x] Splits on headings and paragraphs; merges too-short and splits too-long chunks per config.
- [x] Handles both article formats among the eight (road tests and the Kia EV9 long-term report); publication date is stored as metadata when the page shows it.
- [x] Every chunk has `car` (a canonical id from the registry), `section`, `source_url`, `chunk_id`.
- [x] Unit tests: structure preserved, metadata present, no empty chunks.
- [x] Size rule as built: no chunk exceeds `max_chars`; a chunk is below `min_chars` only when merging it with either neighbor would exceed `max_chars` (none today: 75 chunks, 317 to 1464 characters). Oversize sections split evenly at block boundaries so no tiny remainder is left.
- [x] Heading lines stay in the chunk text, so merged sections (pros and cons, several FAQ questions) keep their boundaries; `embed_text` adds the car name and section in front.

### CW-103 Embeddings, Chroma index, per-car retrieval
- [x] Multilingual embedding model with Hebrew support; version pinned in config.
- [x] `make ingest` builds the index; retrieval is deterministic for the same query.
- [x] Retrieval can filter by car and returns similarity scores.
- [x] Unit tests: per-car filter returns only that car.
- [x] As built: `embeddings.provider` selects the embedder (`sentence_transformers`, or `fake` for offline tests); `intfloat/multilingual-e5-base` pinned to commit `d1287505`, loaded from the local cache when present. The index fingerprint (embedder, chunk limits, chunk ids, chunk text) skips unchanged rebuilds. Retrieval ranks every candidate exactly and breaks ties by chunk id; `search`, `search_per_car` and `search_all` (cap per car). `python -m app search` prints metadata only.
- [x] Finding for CW-303: 5 of 75 chunks exceed the model's 512-token window (max 647 tokens), so their tails are not embedded; tune `max_chars` (or measure in tokens). Similarity scores are compressed (about 0.79 to 0.86, an off-corpus car scores like a real match), which confirms the registry check must be the primary gate.

### CW-104 `LLMClient` interface and one implementation
- [x] Interface with `complete()` (supports structured output) and `embed()` if needed. As built: one method, `complete_json(system, messages, schema, *, model) -> LLMResult` (parsed object, usage, cost, latency, model); no `embed()`, embeddings stay local.
- [x] One implementation over the official OpenAI SDK with a configurable `base_url`; it serves OpenAI by default, and any OpenAI-compatible server (for example Ollama at `http://localhost:11434/v1`) as an option. Uses Chat Completions, the API those servers implement.
- [x] Config profiles selected by an environment variable or flag; keys from environment only. (Both profiles use OpenAI per decision D2, not a local `dev` model as first drafted.)
- [x] Structured output is always validated with Pydantic, because local models are less reliable at following a schema. Strict JSON schema plus Pydantic; one corrective retry with the validation error, then `LLMOutputError`.
- [x] Profiles: `dev` = `gpt-5.4-nano` for both calls; `final` = `gpt-5.4-nano` for understanding and `gpt-5.4-mini` for generation. Names and prices live in config.
- [x] Spike: both models accept `temperature=0` and a seed; `reasoning_effort` accepts `none` and `low` (not `minimal`); defaults spend no reasoning tokens, `low` adds 17 to 32 billed as output. Config sends temperature 0, seed 7, effort `none`. Prices match the official page. Wording still varies between runs on open questions. See `docs/decisions/0001-llm-sampling-controls.md`.
- [x] Three-prompt Hebrew sanity check (a fact, a comparison, a refusal) with the chosen models: 12 of 12 valid Hebrew JSON replies with correct facts and refusals (in `scripts/llm_spike.py`).
- [x] Timeouts and one retry; a fake client exists for tests. Also: cost per call from config prices, a running total that refuses calls past `llm.max_cost_usd`, and a `live` test (deselected by default).

### CW-105 Basic pipeline and CLI
- [x] `pipeline.answer(message, session) -> Response` is the single entry point. As built: `Pipeline(settings, registry, retriever, llm).ask(message, history) -> Answer` (owner's spec of 2026-10-30); CLI, UI and eval call only this.
- [x] Prompts live in versioned text files, not in code: `src/carwise/llm/prompts/*.v1.txt`, exposed as named constants by `src/carwise/prompts.py`; telemetry records the prompt version.
- [x] Understand call returns intent, cars (canonical ids), standalone query, preference updates (validated by Pydantic); invalid output gets one retry, then falls back to using the raw message as the query (cars then come from deterministic name matching).
- [x] The understand schema includes `unrecognized_cars` (raw names of cars that match no registry entry), and generation returns JSON with `answer` and `used_chunk_ids`; ids not retrieved this turn are rejected in code (dropped and flagged).
- [x] History window size comes from config.
- [x] Chitchat and out-of-scope intents skip retrieval and reply briefly with what the bot can do.
- [x] All replies are in Hebrew; the first message states that knowledge is limited to the eight reviewed cars; tone is friendly and concise. The answer validator rejects non-Hebrew text, JSON field names and chunk ids inside the answer (one corrective retry).
- [x] Comparison questions retrieve separately per car.
- [x] The understand schema already contains the preference-update field; merging and using preferences is implemented in CW-203.
- [x] Generated answers cite car and section; CLI chat works end to end (`python -m app chat [--profile final] [--show-cost]`).
- [x] Unit tests with the fake `LLMClient`: intent handling, fallback on invalid output, chitchat skipping retrieval; also unknown-car and low-similarity refusals, history follow-up, invalid cited ids, telemetry without text.
- [x] Pulled forward at the minimum, refined later: the registry gate (unknown car only, or an outside brand from `guardrails.outside_brands`; known plus unknown cars are answered with a note) and the similarity gate (threshold 0 until CW-303) for CW-201; one JSON line per turn in `logs/turns.jsonl` for CW-204. The chat loads the embedding model at start, so the first question is not a one-minute wait.
- [x] Known issue for CW-202 and CW-302: in the real run the comparison answer called two sections of the MG S6 article "another article". Facts were right; the wording was not.

### CW-106 Eval question set
- [x] About 15 questions in `eval/questions.yaml`, written after reading the articles and before building the guardrails and tuning, so the eval guides the work.
- [x] Categories: single-car facts, two-car comparisons, preference-driven recommendations, ranking questions across all cars, history-dependent follow-ups.
- [x] At least one scripted multi-turn scenario in which preferences accumulate and the final recommendation reflects them.
- [x] At least 4 trap questions: car not in the corpus, detail never mentioned, a mixing trap, and one more of the author's choice.
- [x] Each question states what must hold (cars, required fact or keyword, or expected refusal), not a full reference answer.
- [x] Each answerable question also records the expected car and section for the retrieval eval.

### CW-201 Relevance gate and fixed refusal
- [x] Below-threshold score, or a car that is not in the car registry, returns a fixed refusal without the generation call.
- [x] The registry check, including `unrecognized_cars`, is the primary gate; the threshold is tuned on the eval, which includes near-miss questions (a known car, a detail the articles never mention). (The threshold stays configurable at 0 until CW-303 tunes it.)
- [x] The reply is templated and filled in by code: it says plainly what the articles do not cover, then suggests the closest cars among the eight (by body type and powertrain from the registry, or by the best-scoring chunks) and invites a follow-up question.
- [x] No outside knowledge is ever added; for a known car with a missing detail the generation step says "not mentioned in the articles" and offers the closest related facts from the chunks. (Generate prompt rule 2.)
- [x] Unit tests: refuses below threshold; refuses unknown car.
- [x] As built: the unknown car is never classified (that would be outside knowledge); suggestions come from the user's own words (the current message and the user turns in the history window, never the model's rewritten question, which can add "electric" from model knowledge of the unknown car), via hint words in `guardrails.body_type_words` and `powertrain_words` mapped to the registry values (a car scores one point per matching dimension; within a dimension the kind with the most hint words wins, so "היברידי נטען" is plug-in only). Without a hint, the low-relevance refusal suggests the cars of the best-scoring chunks; with neither, every refusal lists the eight cars grouped by powertrain with their body type. `Answer.suggested_cars` and the telemetry line record what was offered; at most `guardrails.max_suggestions` cars.

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

| 2026-10-29 | CW-002 done: all eight URLs return 200 with real article bodies, `robots.txt` was read and allows them. Decision: automatic download (identifiable User-Agent, 3 s delay, cache in `data/raw/`); manual placement stays as the documented fallback. |

| 2026-10-29 | CW-003 done: six milestones (E0 to E5), PR template, pre-publish scan of the history found no secrets or data files, `.gitattributes` added to keep LF line endings (the Makefile needs them). Epic E0 closed. |

| 2026-10-30 | CW-201 done: refusals suggest the closest of the eight cars (hint words from the user's message, else best-scoring chunks, else all eight grouped by powertrain and body type) and invite a follow-up; similarity threshold stays configurable at 0 until CW-303. |

| 2026-10-29 | CW-101 done: `config/cars.yaml` plus `registry.py`, `fetch.py` (the CW-002 probe folded in and deleted), `clean.py` on beautifulsoup4 with `html.parser`, and `python -m app ingest` printing a per-article report. Each registry body type and powertrain carries the article words behind it; the Elantra article never states the Elantra's body type, so that value is null. Cleaner findings: the spec table uses `role=row` markup inside `<li>` and is kept as one line per row; "סיכום AI" is a script-loaded widget and is skipped; the Elantra sections are numbered `<h3>` questions; the Kia report has no subheadings and ends with four label/value stats. |
