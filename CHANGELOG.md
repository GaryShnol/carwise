# Changelog

Release notes per tag. Tickets and their acceptance criteria are in [BOARD.md](BOARD.md);
measurements are in the ADRs under [docs/decisions/](docs/decisions/).

## Unreleased

- Stray comma removed from the greeting (CW-625).
- README note on exclusivity claims built from absence (CW-626).
- Inline "(car, section)" citation markers hidden in the CLI and UI display (CW-627).

## v1.0.1 (2026-11-02)

Fixes from the independent code review of `v1.0`
([docs/review/](docs/review/), CR-001 to CR-020 map to CW-601 to CW-620).

### E6: Review fixes

- Car-name matching: a short alias next to another brand or a sibling-model word is not the
  corpus car (CW-601); a short Hebrew outside brand no longer matches ordinary words (CW-602).
- Numeric post-check accepts only the user's own words, never the understand rewrite (CW-603).
- "Covers only the eight reviewed cars" is added in code to recommendations and rankings
  that lack it (CW-606); off-topic requests are refused even when they name a car (CW-608).
- Docker binds to localhost only, with a process-wide spend cap (CW-605); one-command start
  with `compose.yaml` (CW-621).
- Link filter handles reference-style links, images and escaped names (CW-611); output-token
  caps and a per-turn deadline (CW-612); the query is embedded once per turn (CW-614);
  telemetry logs only a count of uncovered names (CW-613).
- Corpus manifest with per-article hashes, a warning at ingest, and the fingerprint in every
  report (CW-610); adversarial post-check test set (CW-619).
- Docs: headline answer score 62/69 with the re-scoring bias stated (CW-607), what the car-name
  and numeric checks cover (CW-604, CW-609), judge caveats (CW-620), CI and ADR notes and stale
  counts (CW-615 to CW-618), and the review itself with a status table (CW-622).
- Post-review answer eval on `final`, 3 runs, frozen checker and judge (CW-623): tuning 64/69
  (single_fact 12/12, comparison 17/18, recommendation 4/6, ranking 4/6, follow_up 6/6,
  trap 21/21), hold-out 16/18 (9/9, 5/6, 2/3), $0.5233, tuning graded turn p50 2445 ms / p95 4659 ms,
  same behavior 23/23, same numbers 12/23, post-check clean on 60 + 18 answers. The changes
  against `v1.0` are within run-to-run noise
  ([ADR 0004](docs/decisions/0004-answer-eval-and-generate-prompt.md)).

## v1.0 (2026-10-31)

The first complete release: a Hebrew chatbot grounded in eight auto.co.il road-test articles,
with a CLI, a Streamlit UI, a Docker image, an eval with committed reports, and the README.

### E2: Reliability and guardrails (PR #3)

- Registry gate and templated refusals that suggest the closest of the eight cars, from the
  user's own hint words only (CW-201).
- Car-name post-check with Hebrew prefix handling and an outside-brand list; one stricter
  regeneration, then a fixed fallback (CW-202).
- Numeric post-check: every number must appear in the retrieved chunks or the user's words
  (CW-206).
- Typed preference memory for one conversation, each value with its source message; `/prefs`
  and `/reset` (CW-203).
- One JSON telemetry line per turn with tokens, cost, latency per stage and check results;
  cost cap per session (CW-204).
- Prompt-injection hygiene (escaping every outside value) and input limits (CW-205).

### E3: Measurement (PR #4)

- Eval runner: retrieval level (free, replays recorded understand outputs) and answer level
  (deterministic checks, an LLM judge only where code cannot decide), per-category reports,
  stability over runs, cost caps (CW-302).
- Embedding model chosen on the retrieval eval: `intfloat/multilingual-e5-large`
  ([ADR 0002](docs/decisions/0002-embedding-model.md)) (CW-305).
- Retrieval tuning: every chunk inside the 512-token window, each named car's spec box forced
  into comparisons, threshold 0.80 as an off-topic backstop
  ([ADR 0003](docs/decisions/0003-retrieval-tuning.md)) (CW-303).
- Recommendations search all cars; named cars are only a hint (CW-306).
- Answer eval on `final`, 3 runs: generate prompt v3 kept at 64/69 over v4 (60/69) and v5
  (63/69); hold-out 15/18 ([ADR 0004](docs/decisions/0004-answer-eval-and-generate-prompt.md)).

### E4: Interface and packaging (PR #5)

- Number-aware preference grounding (Hebrew number words) and rejected field names in the
  telemetry (CW-405).
- Streamlit UI in Hebrew, right to left: chat, live preference panel, retrieved chunks,
  cost per answer, article links (CW-401).
- Dockerfile with the index built into a volume at first start, non-root, pinned base, and an
  allow-list build context (CW-402).
- GitHub Actions: offline lint, types and tests on Python 3.11 and 3.13; manual retrieval eval,
  answer eval and Docker smoke workflows (CW-403).

### E5: Documentation and release

- README: TL;DR, quickstart (uv, Docker, Ollama as an untested option), architecture diagram,
  decision table, guardrails, eval results and caveats, a real example conversation and a UI
  screenshot, limitations, AWS mapping, data and licensing (CW-501, CW-502).
- `docs/README.md` index of the ADRs and operations docs.
- Fixed: an empty `OPENAI_BASE_URL` (what copying `.env.example` produced) made the OpenAI
  SDK use `""` as its base URL, so every LLM call failed. Found by the clean-clone check
  (CW-503).
- `.gitignore` covers other `.env.*` files and the local Ollama config copy.
- Tests: a SyntaxWarning in `tests/test_ui.py` removed; the suite runs without warnings.
- Hygiene scan before release: gitleaks over every commit and the tracked tree found no leaks,
  no article text or data files are in the history.

### Known limitations

See [README: Known limitations and next steps](README.md#known-limitations-and-next-steps):
prose-only figures in comparisons, wrong "not mentioned" claims not caught in the pipeline,
rare "in another article" phrasing, the turn log not persisted in Docker, and local use with
your own key.

## v0.1 (2026-10-30)

The first working vertical slice, from raw articles to a grounded answer in the command line.

### E0: Scaffold and source check (PR #1)

- Repository scaffold, `python -m app` entry point, config, MIT license (CW-001).
- Source access spike: all eight URLs fetchable, `robots.txt` allows them (CW-002).
- GitHub setup: milestones, pull-request template, branch protection requiring a pull request
  (CW-003).

### E1: Thin vertical slice (PR #2)

- Polite download, cache and cleaning of the eight articles; the car registry (CW-101).
- Structure-aware chunking with `car`, `section`, `source_url` and `chunk_id` (CW-102).
- Local embeddings and Chroma index with per-car retrieval (CW-103).
- `LLMClient` on the OpenAI SDK with a configurable `base_url`, strict JSON output, cost per
  call, and the `dev` and `final` profiles
  ([ADR 0001](docs/decisions/0001-llm-sampling-controls.md)) (CW-104).
- The pipeline (understand, retrieve, generate with checked citations) and the CLI (CW-105).
- The eval question set, written before the guardrails (CW-106).
