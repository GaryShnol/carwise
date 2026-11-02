> **About this file.** An independent code review of commit `1224478` (`v1.0`), written by a
> separate, fresh Claude Code session in read-only mode. It ran no paid answer eval, made 8 live
> pipeline turns on the `dev` profile costing $0.0107 in total, and wrote nothing to the
> repository except the review itself (see its section 5 and Appendix). The review text below is
> kept as written. Its findings were addressed in epic E6 (CR-0NN maps to CW-6NN); a status table
> is at the end, under "Status after E6".

# Code review: carwise

## 1. Summary

**Scope.** Commit `1224478` (`main`, tagged `v1.0`), reviewed 2026-11-01. I read every module in
`src/carwise` and `app/`, the eval runner (`eval/answer.py`, `retrieval.py`, `recording.py`,
`rescore.py`, `judge.py`, `questions.yaml`), the risky tests (pipeline, post-check, concurrency,
injection), `config/`, the Dockerfile, the three workflows and the composite action, README,
BOARD, CLAUDE.md and the four ADRs. I treated every claim in the docs and reports as unverified
and checked it against code, data, or a reproduction.

**Checks run.**

| Check | Result |
|---|---|
| `uv sync --locked` | OK (lock file matches) |
| `uv run pytest -q` | 700 passed, 3 deselected (slow/live), 29 s |
| `uv run ruff check .` / `ruff format --check .` | clean / 124 files formatted |
| `uv run mypy src app eval` | no issues in 46 files (strict) |
| gitleaks v8.21.2 over full history (Docker) | 129 commits, no leaks |
| History grep for keys and sensitive files | only two fake test keys; no `.env`, raw HTML, logs or answer files ever committed |
| Retrieval eval, tuning set (to scratch dir) | 23/23, 26/26, MRR 0.631: identical to the committed report |
| Retrieval eval, hold-out (to scratch dir) | 5/6, 7/8, MRR 0.669: identical |
| Offline reproductions (scripted fake LLM, real index) | see findings |
| Real-model calls, `dev` profile, 8 turns | $0.0107 total |

**Overall assessment.** This is a careful, well-tested proof of concept. The pipeline order
matches the spec, the code is typed and readable, the eval is unusually disciplined (recorded
understand outputs, hold-out set, cost caps, metrics-only reports), and the published retrieval
numbers reproduce exactly. The weak points are concentrated in one place: the deterministic
name matching behind the gate and the post-check. Short registry aliases (`S6`, `C3`, `Aion`,
`אלנטרה`) route other models of the same brands to a corpus car. The outside-brand list matches
common Hebrew verbs (`רנו` inside `שמרנו`, `מכרנו`). The post-check does not see cars from corpus
brands that are not in the registry. The README states these guarantees more strongly than the
code delivers them. There are also two eval-validity points a careful reader would raise (one-way
re-scoring, unpinned corpus), and the Docker command publishes an unauthenticated, key-spending
UI on every host interface.

**Finding counts.**

| Severity | Confirmed | Suspected | Total |
|---|---|---|---|
| Critical | 0 | 0 | 0 |
| High | 1 | 0 | 1 |
| Medium | 6 | 0 | 6 |
| Low | 10 | 1 | 11 |
| Info | 2 | 0 | 2 |
| **Total** | **19** | **1** | **20** |

## 2. Top 5 issues to fix first

1. **CR-001** Short aliases (`S6`, `C3`, `Aion`, `אלנטרה`) map other models (Audi S6, Aion Y, an
   Elantra hybrid) onto corpus cars in code, so the registry gate passes them through.
2. **CR-002** The outside brand `רנו` (Renault) matches inside common Hebrew verbs, which adds a
   false "not covered: Renault" to the answer or refuses the question outright.
3. **CR-003** The numeric post-check whitelists every number in the LLM-rewritten question, so a
   number invented by the understand call passes as "the user's own words".
4. **CR-005** The Docker run line publishes the UI on all interfaces with no auth, and a page
   refresh resets the per-session cost cap.
5. **CR-007** The headline 64/69 is re-scored after auditing only the failures, so grading
   corrections could only raise the score. This is not stated as a bias.

## 3. Findings

### CR-001: Short aliases route other models of the same brand to a corpus car

- **Severity:** High · **Status:** CONFIRMED · **Category:** 1. Correctness / 2. Grounding
- **Location:** `config/cars.yaml:20,53,63,75`; `src/carwise/guardrails.py:142-144`;
  `src/carwise/pipeline.py:350-351`
- **Description:** `cars_in_text` adds every registry car whose alias appears in the message,
  regardless of what the model said. The registry includes bare model codes and short names:
  `C3`, `S6`, `Aion`, `אלנטרה`. Several real cars outside the corpus contain them (Audi S6,
  Citroën C3 Aircross, GAC Aion Y/S, Elantra non-N). The car-name post-check uses the same matcher,
  so an answer that names "Aion Y" is read as the Aion HT. The registry comment says brand-only
  names and generic codes were left out, but `S6`, `C3` and `Aion` are exactly that kind of code
  within their brands.
- **Evidence:** offline, with the real registry:
  ```
  כמה עולה אאודי S6?        -> ['mg_s6']             brands: []
  מה דעתך על GAC Aion Y?     -> ['aion_ht']
  סיטרואן C3 איירקרוס        -> ['citroen_c3']
  יונדאי אלנטרה היברידית     -> ['hyundai_elantra_n']
  ```
  Live (`dev`): "כמה עולה יונדאי אלנטרה היברידית?" gave `cars=['hyundai_elantra_n']`,
  `not_covered=[]`, so no gate and no "not covered" note reached generation. The generator happened
  to say the hybrid is not mentioned. The Audi S6 and Aion Y turns were saved only because the
  understand model also listed them in `unrecognized_cars`.
- **Impact:** The registry gate is presented as the primary, code-enforced refusal. For this class
  of question, whether the bot answers about the wrong car depends on the model's caution. The
  post-check also cannot catch it, because the cited car is a retrieved corpus car. The trigger is
  likely: asking about a sibling model or trim is a common question.
- **Suggested fix:** Match bare codes only with their brand (`MG S6`, `סיטרואן C3`, `איון HT`), or
  require that no other model token follows the alias. Drop any `unrecognized_cars` entry that
  contains a matched alias plus extra model words from the "known" set, so the turn becomes known +
  unknown. Add tests for the four collisions above.
- **Effort:** S

### CR-002: Outside brand "רנו" matches Hebrew first-person-plural verbs

- **Severity:** Medium · **Status:** CONFIRMED · **Category:** 1. Correctness
- **Location:** `config/settings.yaml:113`; `src/carwise/guardrails.py:114-117,147-148`;
  `src/carwise/pipeline.py:209-212,352-354`
- **Description:** Brands are matched as whole words after up to three of the prefix letters
  `והבכלמש`. `רנו` preceded by those letters forms ordinary verbs: `שמרנו`, `הכרנו`, `מכרנו`,
  `שכרנו`. Each such message gets `not_covered=['רנו']`. If the turn names no known car, the
  registry gate refuses with "I have no information about רנו".
- **Evidence:**
  ```
  offline: outside_brands_in_text("שמרנו לך את הנתונים?")  -> ['רנו']
  offline (scripted understand, no cars): "בחרנו בינתיים מה הכי חסכוני? כבר הכרנו כמה"
           -> refusal=unknown_car, not_covered=['רנו']
  live:    "מכרנו את הרכב הקודם שלנו, איזה רכב חשמלי הכי מתאים למשפחה?" -> not_covered=['רנו']
  live:    "שמרנו כסף, מה הרכב הכי זול שנבחן?"                           -> not_covered=['רנו']
  ```
  In both live turns the model happened to list all eight cars, so the turn reached generation.
  The generate prompt still received "Cars the articles do not cover: רנו".
- **Impact:** Family users naturally speak in the plural ("we sold", "we kept"). The result is
  either a wrong refusal or a prompt that invites a stray Renault sentence. It is visible in a demo.
- **Suggested fix:** Remove short Hebrew brands that collide with common words (`רנו`), or allow
  only the prefixes that attach to nouns. A better fix is to require a model word or the Latin
  name next to a short brand. Add a regression test with a few common verbs.
- **Effort:** S

### CR-003: Numbers in the LLM-rewritten question count as "the user's own words"

- **Severity:** Medium · **Status:** CONFIRMED · **Category:** 2. Grounding
- **Location:** `src/carwise/pipeline.py:283-288` (`user_texts = [plan.message, plan.question, ...]`)
- **Description:** `plan.question` is `standalone_question`, the output of LLM call 1, not user
  text. Any number in it is allowed in the answer. The understand prompt asks the model to "carry
  over constraints", so numbers do appear there. A number the understand model invents, or takes
  from an earlier assistant answer about a different car, passes the numeric check. The generator
  receives that rewritten question and is primed to repeat the number.
- **Evidence:** scripted understand output, real pipeline code:
  ```
  understand.standalone_question = 'כמה כוח סוס יש ל-MG S6 עם 350 כ"ס?'   user: 'כמה כוח סוס יש ל-MG S6?'
  generation = 'ל-MG S6 יש 350 כ"ס (MG S6, פרק 0).'
  -> refusal: None | post_check: clean
  ```
- **Impact:** A fabricated figure would be shown as checked. This needs an understand-model error,
  which is less likely at temperature 0, but this check exists precisely so that model errors are
  not trusted. The README says numbers must come from "the user's own words" (README:263), which
  is not what the code checks.
- **Suggested fix:** Use only `plan.message`, the user turns in the history window, and the stored
  preference values (already grounded). If carrying numbers from earlier answers is wanted, add
  the earlier turns' cited chunks rather than the rewrite.
- **Effort:** S

### CR-004: Car-name post-check misses corpus-brand models and unlisted models; README overstates it

- **Severity:** Medium · **Status:** CONFIRMED · **Category:** 2. Grounding / 9. Docs
- **Location:** `src/carwise/guardrails.py:161-193`; `config/settings.yaml` (`outside_brands`);
  README:31-32, README:262
- **Description:** The check flags only registry aliases and the outside-brand list. Brands that
  are in the corpus (Kia, Hyundai, Audi, MG, Genesis, GAC) are excluded from the outside list by
  design, so any other model of those brands passes unflagged. Model names without a brand also
  pass. The docstring states this limit, but the README TL;DR says "every car name ... must appear
  in the chunks", and the Known limitations section does not mention it.
- **Evidence:**
  ```
  unsupported_cars('ל-MG S6 טווח של 400 ק"מ, יותר מקיה EV6.', [mg_s6 chunk]) -> []
  unsupported_cars('ל-MG S6 טווח של 400 ק"מ, יותר מאיוניק 5.', [mg_s6 chunk]) -> []
  ```
- **Impact:** The kind of outside-knowledge leak most likely in a car chatbot (a sibling model of
  a reviewed car) is the one the check does not see. The README claim is wrong as written.
- **Suggested fix:** Correct the README wording now. In code, flag `<corpus brand> + <model token>`
  patterns that are not a registry alias (for example a regex for a brand followed by a Latin or
  digit token), or keep a small list of sibling models.
- **Effort:** S (docs) / M (code)

### CR-005: Docker command exposes the unauthenticated UI on all interfaces; per-session cap is reset by refresh

- **Severity:** Medium · **Status:** CONFIRMED · **Category:** 3. Security
- **Location:** `Dockerfile:66`, `README.md:120`, `docs/docker.md:7,15`; `app/ui_page.py:84-88`;
  `app/ui_text.py` (`STOPPED`)
- **Description:** `-p 8501:8501` binds to `0.0.0.0` on the host (and on Linux, Docker's rules
  bypass ufw). `docs/docker.md:15` says it "publishes the UI on http://localhost:8501", which is
  misleading. Each browser session gets a fresh `OpenAIClient` with its own `$2` cap, and the
  stop message itself tells the user to refresh. Anyone on the same network can spend the owner's
  API key without limit. The README's warning ("should not be exposed to other users") does not
  match the command it gives.
- **Evidence:** `ui_page.render`: `if "llm" not in state: state.llm = ui.new_llm(settings)`, so a
  new session gets a new client and a new cap. `STOPPED = "...כדי להתחיל מחדש יש לרענן את הדף."`
- **Impact:** Moderate likelihood on a laptop on shared Wi-Fi. The cost is real money on the
  reviewer's key.
- **Suggested fix:** Document `-p 127.0.0.1:8501:8501`. Add a process-wide spend cap (one shared
  counter in `Resources`, checked next to the per-session one).
- **Effort:** S

### CR-006: "Covers only the eight reviewed cars" is enforced by the prompt only, and the eval shows it failing

- **Severity:** Medium · **Status:** CONFIRMED · **Category:** 2. Grounding / 6. Design
- **Location:** `src/carwise/llm/prompts/generate.v3.txt:11` (rule 8); `src/carwise/pipeline.py:456-482`
- **Description:** CLAUDE.md requires recommendation and ranking answers to say they cover only
  the eight cars, and states the principle "do not trust the model, bound it". The statement is
  only requested in the prompt. The committed final report fails it in 2 of 6 ranking runs
  (`rank-fastest`, `rank-cheapest`: `must_include` of the "eight" group).
- **Evidence:** `eval/reports/answer/final/v3/answer-tuning-rescored-final.md`: ranking 4/6. The
  README lists these as failures, not as a missing code guard.
- **Impact:** A stated guarantee in a main flow holds 67% of the time on rankings. A deterministic
  fix would raise the published score by two runs at no cost.
- **Suggested fix:** In `_grounded`, when `plan.intent is RECOMMEND` and the answer lacks the
  phrase, prepend a fixed sentence from `guardrails` (code-built, like the refusals).
- **Effort:** S

### CR-007: Headline answer score is re-scored after auditing only failures

- **Severity:** Medium · **Status:** CONFIRMED · **Category:** 5. Evaluation validity
- **Location:** README:37, README:346-349; `docs/decisions/0004-answer-eval-and-generate-prompt.md:36-48`;
  `eval/rescore.py`; `eval/judge.yaml` (criteria v3)
- **Description:** ADR 0004 says each of the four corrections "was found by reading a failure".
  Three checker fixes and one judge-criterion change were applied, and the same answers were
  graded again (62 → 64/69). Passing answers were not audited for false passes, so the corrections
  could only move the score up. The judge criterion was changed after its verdict was seen. The
  fixes look correct, and both reports are committed. The issue is that the one-way direction of
  the correction is not stated, and the headline uses the re-scored number.
- **Evidence:** README:346-349; `answer-tuning-final.md` (62/69) vs
  `answer-tuning-rescored-final.md` (64/69); the notes line of the report records the criteria
  change.
- **Impact:** A hiring panel will notice post-hoc grading changes. It weakens trust in the 93%
  figure more than the 2-run difference warrants.
- **Suggested fix:** State the bias in the Caveats. Audit a random sample of passing runs with the
  same care, or report 62/69 as the headline and 64/69 as "after checker fixes". Freeze judge
  criteria before a run whose number is published.
- **Effort:** S

### CR-008: Off-topic gate is skipped whenever a car is named

- **Severity:** Low · **Status:** CONFIRMED · **Category:** 1. Correctness
- **Location:** `src/carwise/pipeline.py:213-215`
- **Description:** `if plan.intent in NO_RETRIEVAL_INTENTS and not plan.cars`. An off-topic
  request that mentions a corpus car goes to retrieval and generation.
- **Evidence:** live (`dev`): "תכתוב לי שיר על אודי RS3" gave `intent=out_of_scope`,
  `cars=['audi_rs3']`, no refusal. The bot wrote a poem with citations, and the post-check was
  clean.
- **Impact:** Contradicts the README "Intent check" row. Harmless content, but the bot leaves its
  role, and the reply costs a generation call.
- **Suggested fix:** Refuse `out_of_scope` regardless of cars. Keep the car exception only for
  `chitchat` if wanted.
- **Effort:** S

### CR-009: Numeric post-check is looser than "every number must appear in the chunks"

- **Severity:** Low · **Status:** CONFIRMED · **Category:** 2. Grounding / 9. Docs
- **Location:** `src/carwise/numbers.py:42-44`; `src/carwise/guardrails.py:196-247`; README:263
- **Description:** These behaviors are by design but are not in the README:
  - (a) Truncation is accepted: source `5.9` backs an answer of `5` seconds.
  - (b) Any number in any retrieved chunk backs the answer, whichever car or attribute it belongs
    to. Mixing numbers between cars is caught only by the eval-only attribution check.
  - (c) Small numbers are almost always backed. Over the eight spec boxes alone, 9 of the integers
    1–10 are backed, so counts (seats, gears, airbags) are effectively unchecked.
  - (d) `derived` accepts any sum or difference of two answer numbers, with a tolerance equal to
    the coarsest unit.
- **Evidence:** `unsupported_numbers('MG S6 מאיץ ל-100 ב-5 שניות', [chunk '...ב-5.9 שניות'])` → `[]`.
  On the real index, 9/10 integers in [1,10], 13/100 in [1,100] and 21/901 in [100,1000] are
  backed by the spec boxes. The check is strict for 3-digit and larger figures.
- **Impact:** Low for large figures, which are the ones that matter most (prices, ranges). It
  becomes a real gap for small counts and cross-car mixing.
- **Suggested fix:** Accept rounding only, not truncation. In the README, state that the check is
  per value, not per car, and that small numbers are weakly checked. Consider promoting the
  attribution check to runtime for comparisons.
- **Effort:** S (docs) / M (code)

### CR-010: Article corpus is not pinned; published numbers depend on whatever the site serves

- **Severity:** Low · **Status:** CONFIRMED · **Category:** 5. Evaluation validity / 4. Reliability
- **Location:** `src/carwise/ingest/fetch.py:182-199`; `.github/actions/corpus/action.yml`
  (cache key is the hash of `cars.yaml`); eval reports
- **Description:** The fetched HTML has no content hash. Reports record embedder, retrieval and
  chunking settings, but not a corpus or index fingerprint. If the publisher edits an article, a
  reviewer's `ingest` produces different chunks and positional `chunk_id`s, and the committed
  reports (which reference chunk ids) silently stop matching. Expected sources are matched by
  section name, which helps, but section text and numbers can change too.
- **Evidence:** No `sha256` over raw HTML or chunks anywhere outside the index fingerprint (grep).
  The report JSON has no corpus field.
- **Impact:** Today the numbers reproduce exactly (verified). Over months they may not, and the
  eval will not say why.
- **Suggested fix:** Record each article's SHA-256 (it is not article text) in `cars.yaml` or a
  manifest. Warn on mismatch at ingest, and write the index fingerprint into every report.
- **Effort:** S

### CR-011: Markdown link filter misses reference-style links and images

- **Severity:** Low · **Status:** SUSPECTED (filter gap confirmed; Streamlit rendering not tested) · **Category:** 3. Security
- **Location:** `src/carwise/guardrails.py:41,59-63`; `app/ui_page.py:34-41`
- **Description:** `_LINK` catches `http(s)://`, `www.` and inline `[x](y)`, but not
  reference-style links or images with a protocol-relative target. Refusal texts that embed
  `not_covered` names (raw strings from the understand call) are rendered as markdown without
  this filter.
- **Evidence:**
  ```
  answer_text_problem("לפרטים [לחצו כאן][1]\n\n[1]: //evil.example/x")    -> None
  answer_text_problem("תמונה ![a][i]\n\n[i]: //evil.example/p.png")       -> None
  ```
- **Impact:** Low. An attacker must steer the generator (through publisher text, or their own
  message, which affects only their own session). To settle it, render the string with
  `st.markdown` and check whether a link or image appears.
- **Suggested fix:** Also reject `^\s*\[[^\]]+\]:` and `\]\[`. Escape `[`, `]` and `!` in names
  that go into refusal templates.
- **Effort:** S

### CR-012: No output-token cap on LLM calls; worst-case turn latency far above "about twice the timeout"

- **Severity:** Low · **Status:** CONFIRMED · **Category:** 4. Reliability / 8. Cost
- **Location:** `src/carwise/llm/openai_client.py:124-129,148-158,174-207`; README:531-533
- **Description:** No `max_completion_tokens` is sent. A runaway generation is bounded only by the
  model's maximum, and the budget check runs before each call, not during it. Each
  `complete_json` makes up to 2 attempts, the SDK retries each once (`retries: 1`), and a turn has
  up to 3 calls. With `timeout_s: 30`, one turn can block for several minutes, not "about twice
  `llm.timeout_s`".
- **Evidence:** `_call` passes `model`, `messages`, `response_format` and the sampling controls
  only. The retry structure is in `complete_json` plus `max_retries=settings.llm.retries`.
- **Impact:** Unlikely, but it is the one unbounded cost and latency path in a project that
  emphasizes bounds.
- **Suggested fix:** Set `max_completion_tokens` per stage in config (understand about 300,
  generate about 800). Add a per-turn deadline, or set SDK `max_retries=0` and keep the explicit
  retry. Fix the README sentence.
- **Effort:** S

### CR-013: Telemetry records raw user words and can mislabel the profile

- **Severity:** Low · **Status:** CONFIRMED · **Category:** 7. Code quality / 3. Privacy
- **Location:** `src/carwise/telemetry.py:48`; `app/chat.py:95`
- **Description:** (a) `not_covered` holds raw names from the user's message, chosen by the
  understand model. With a prompt-injection message, it can hold arbitrary user text. The README
  says the log is "never the message text". (b) The CLI labels the log with
  `profile_name or settings.default_profile`. When `CARWISE_PROFILE=final` comes from `.env`
  without `--profile`, lines say `dev` while the models are final's. The UI reads the environment
  correctly.
- **Evidence:** code as cited. `.env.example` sets `CARWISE_PROFILE`.
- **Impact:** Minor privacy-claim mismatch, and wrong cost attribution when profiles are compared.
- **Suggested fix:** Log the count or a hash of `not_covered`. Use the resolved profile name
  (`os.environ.get("CARWISE_PROFILE") or default`) in the CLI, as the UI does.
- **Effort:** S

### CR-014: Query embedded twice for comparisons and recommendations

- **Severity:** Low · **Status:** CONFIRMED · **Category:** 8. Performance
- **Location:** `src/carwise/retrieval/retriever.py:106-110,146`; `src/carwise/pipeline.py:385,397,403`
- **Description:** `_ranked` embeds the query on every call. A comparison runs `search_per_car`
  and then `spec_boxes`, and a recommendation runs `search_all` and then `spec_boxes`, so e5-large
  embeds the same text twice on CPU. The UI also holds the global retrieval lock for both.
- **Evidence:** retrieval p50 405 ms / p95 1086 ms in my tuning-set run, which is dominated by
  embedding.
- **Impact:** Roughly 100–300 ms per compare or recommend turn, and longer lock hold times in the UI.
- **Suggested fix:** Embed once in the pipeline (or memoize the last query in `Retriever`) and pass
  the vector down.
- **Effort:** S

### CR-015: Three Hebrew number-word tables and two number tokenizers

- **Severity:** Low · **Status:** CONFIRMED · **Category:** 6. Design / 7. Maintainability
- **Location:** `src/carwise/numbers.py`; `src/carwise/preferences.py:43-151`;
  `eval/answer.py:49-53,353-363`
- **Description:** Digits are parsed in `numbers.py`. A second tokenizer with a full number-word
  grammar lives in `preferences.py`, and a third, smaller word table lives in the eval. A fix in
  one (for example CW-405's "חמישה") must be repeated in the others. The eval already diverges: it
  covers 1–7 only.
- **Impact:** Maintenance risk. Grounding and grading can disagree on the same text.
- **Suggested fix:** Move number-word parsing into `carwise.numbers` (as an opt-in reading) and use
  it from preferences and the eval.
- **Effort:** M

### CR-016: Recommendation spec boxes ignore `force_spec_box`

- **Severity:** Low · **Status:** CONFIRMED · **Category:** 6. Design
- **Location:** `src/carwise/pipeline.py:380-398`; ADR 0003, step 2
- **Description:** ADR 0003 describes option B as applying to "compare and recommend intents"
  behind `retrieval.force_spec_box`. In code, the flag gates only `COMPARE`. Recommendations always
  add spec boxes for named cars (CW-306). Setting the flag to `false` does not reproduce the ADR's
  "no option" baseline.
- **Impact:** Config does not do what its documentation says, which matters for re-running the
  ablation.
- **Suggested fix:** Gate both branches on the flag, or document that CW-306 made recommendation
  spec boxes unconditional.
- **Effort:** S

### CR-017: Stale documentation and status

- **Severity:** Low · **Status:** CONFIRMED · **Category:** 9. Docs / 10. Hygiene
- **Location:** `BOARD.md:74,155`; `src/carwise/retrieval/store.py:4,171`; `eval/retrieval.py:30`;
  `docs/docker.md:15`
- **Description:** BOARD still shows E5 and CW-503 as `IN REVIEW`, although PR #6 is merged and
  `v1.0` is tagged. The Definition of Done requires the board to reflect reality. Comments say the
  corpus has "75 chunks" (it has 78). `docs/docker.md` says `-p 8501:8501` publishes on localhost
  (see CR-005).
- **Suggested fix:** Update the statuses and counts.
- **Effort:** S

### CR-018: Retrieval eval is not run automatically in CI

- **Severity:** Low · **Status:** CONFIRMED · **Category:** 10. CI
- **Location:** `.github/workflows/ci.yml`, `.github/workflows/eval.yml`; CLAUDE.md §13–14
- **Description:** CLAUDE.md says "make test and the retrieval eval run in CI", and allows falling
  back to unit tests only "if the site blocks CI ... and document it". The retrieval eval is
  manual-only, and `docs/ci.md` does not say the site blocked the runner. A retrieval regression
  can therefore merge with green CI. The README is honest about this.
- **Suggested fix:** Run the retrieval job on pull requests to `main` (it is free, and the articles
  and model are cached), or record why not.
- **Effort:** S

### CR-019: The post-check has never fired in a real run

- **Severity:** Info · **Status:** CONFIRMED · **Category:** 5. Evaluation
- **Location:** README:242 (decision table "Evidence"), README:352
- **Description:** "Clean on every answer of the 3-run final eval" is offered as evidence for the
  post-check. A check that never triggered on 78 real answers shows a low false-positive rate. It
  shows nothing about recall, which is tested only by synthetic unit tests. My eight live turns
  were also all clean, including the poem.
- **Suggested fix:** Add a small adversarial set (scripted bad generations, or a real
  "answer with outside knowledge" prompt) and report how many the post-check catches.
- **Effort:** S

### CR-020: Judge and recording caveats

- **Severity:** Info · **Status:** CONFIRMED · **Category:** 5. Evaluation
- **Location:** `eval/judge.py`; `eval/recording.py`
- **Description:** The judge is the same vendor and family as the generator (gpt-5.4 vs
  gpt-5.4-mini). It emits `passed` before `reason`, and it has no human-labelled calibration set.
  The retrieval eval grades one recorded sample of the understand step, so its numbers are
  conditional on that sample. Both are reasonable for a take-home project and partly documented.
- **Suggested fix:** Put `reason` before `passed` in the schema. Hand-label the judged runs once
  and report agreement.
- **Effort:** S

## 4. Claims audit

| Claim (source) | Verdict | Evidence |
|---|---|---|
| Retrieval tuning set 23/23, 26/26, MRR 0.631 (README:304-315) | verified | Reproduced exactly from a clean run into a scratch dir |
| Retrieval hold-out 5/6, 7/8, MRR 0.669; miss is MG S6 top speed at car rank 4 (README:320-322, ADR 0003) | verified | Reproduced exactly |
| Answer level final 64/69 with per-category table (README:326-337) | verified (as re-scored) | `answer-tuning-rescored-final.md`; pre-re-score 62/69 also committed; see CR-007 |
| Hold-out answers 15/18, $0.0409, misses are the MG S6 top speed (README:358-362) | verified | `holdout-v3/answer-holdout-final.md`: only `holdout-compare-topspeed` failed (0/3) |
| Cost $0.2447 / $0.2017; 400,092 in / 18,764 out; p50 2.8 s, p95 4.1 s | verified | Report header |
| Stability 23/23 behavior, 15/23 numbers, 28% text | verified | Report header |
| v3 64/69, v4 60/69, v5 63/69 (README:243, ADR 0004) | verified | ADR tables match the committed reports; `PROMPT_VERSIONS["generate"] == "v3"` |
| Embedding choice 21/23 vs e5-base 17, bge-m3 19, e5-base+BM25 18 | verified | `eval/reports/candidates.md` |
| 78 chunks | verified | Index holds 78 (comments saying 75 are stale, CR-017) |
| "None over the 512-token window" | unverifiable here | Not re-measured; ADR 0003 report shows it |
| Answerable min 0.846, probe min 0.847 | verified | Reproduced score spread |
| "Every car name ... must appear in the chunks" (README:31, 262) | wrong | CR-001, CR-004 |
| "Every number must appear in the chunks or in the user's own words" (README:263) | wrong | CR-003 (LLM rewrite), CR-009 |
| "Chitchat and off-topic messages get a fixed reply ... no retrieval" (README:259) | wrong when a car is named | CR-008 |
| Registry gate refuses cars outside the eight before generation | partly | Works for distinct names; fails for alias collisions (CR-001) and refuses on false brand hits (CR-002) |
| Post-check "clean on every answer" as evidence (README:242) | verified but not evidence of effect | CR-019 |
| UI "listens on localhost only" (README:108) | verified for `python -m app ui`; wrong for the Docker line | `--address localhost` default; CR-005 |
| Turn log "never the message text" (README:24, 269) | partly | `not_covered` raw names are logged (CR-013) |
| Log never holds the key (tested with a planted key) | verified | Test with a planted `sk-test-…`; gitleaks clean |
| Cost cap per chat session / per browser session | verified | Per-client `total_cost_usd`; see CR-005 for refresh |
| "SDK retries ... about twice `llm.timeout_s`" (README:531) | understated | CR-012 |
| Retrieval is deterministic | verified | Two runs identical to the committed report; score rounding plus id tie-break |
| Reports hold no article text | verified | No Hebrew run over 70 chars in any committed report file |
| No secrets / no articles in the repo or its history | verified | gitleaks plus history file list; the HTML fixture is synthetic |
| Actions pinned to SHAs, read-only token, fork-safe | verified | Workflows; the article-cache exposure to forks is documented in `docs/ci.md` |
| Example conversation cost $0.021 | verified | The five shown turn costs sum to $0.0214 |
| README and docs links | verified | All relative links resolve |
| Docker first start 177 s, later 17 s; image size | unverifiable here | Image not built in this review |

## 5. Areas reviewed with no findings, and areas not reviewed

**Solid, no findings:**

- **Pipeline order and refusal paths.** The fixed order is followed. Every refusal is built by code
  before generation. Budget, empty input, over-long input and LLM failures each map to a fixed
  Hebrew reply.
- **History windowing and escaping.** `_window` bounds each user turn and the total. Escaping of
  `<` and `>`, role markers and one-line fields is applied consistently in prompts and in the judge.
- **Preference grounding.** Values must share content tokens with the current message. Lifted
  values are rejected and flagged, and the profile lives only in the session.
- **Citation id check.** Only ids retrieved in the same turn survive.
- **LLM client.** Strict JSON schema plus Pydantic validation, one corrective retry, honest
  per-attempt cost accounting on failures, auth errors redacted, and an empty `OPENAI_BASE_URL`
  handled.
- **Thread safety in the UI.** The retriever and logger are shared behind locks, and each session
  has its own client and pipeline. The concurrency tests exercise this with barriers.
- **Ingestion.** URLs come only from a validated registry (https, slug check), so there is no SSRF
  surface. robots.txt, Crawl-delay and the User-Agent are respected, and 4xx is final. The index
  is rebuilt only when the fingerprint changes, and vectors are computed before the old collection
  is deleted.
- **Deserialization.** `yaml.safe_load`, JSON and Pydantic only, with no pickle or eval.
- **Supply chain.** Exact pins in `pyproject.toml`, `uv.lock` with `--locked`, digest-pinned base
  images, a pinned uv binary, SHA-pinned actions, a pinned Hugging Face revision, no
  `trust_remote_code`.
- **Docker hardening (apart from CR-005).** Non-root user, multi-stage build, allow-list
  `.dockerignore`, a healthcheck, no key in build arguments or image layers.
- **Tests.** 700 offline tests, scripted fake LLM rather than mocks of internals, fixtures that do
  not copy article text, and markers for the slow and live tests.
- **Repo hygiene.** `.gitignore` covers `.env*`, data, logs and `eval/runs/`. The MIT license and
  copyright notes are present.

**Not reviewed, or only partly:**

- **Docker image.** Not built or run, for time and the 2 GB model download. Its size and start-time
  claims are unverified.
- **`src/carwise/ingest/clean.py`.** Skimmed only. It is covered by fixture tests, and the
  retrieval eval reproduced, which indirectly validates the cleaning on the current articles.
- **Answer-level eval.** Not re-run, because it costs about $0.45 against the $0.10 budget. Its
  claims were checked against the committed reports and the local `eval/runs/` logs only. A scan
  of those logs found no keyword pass that depended on a substring of a longer, unrelated number.
- **Token-window lengths and lexical (BM25) code paths.** Not re-measured; the BM25 path is off by
  default.
- **Streamlit rendering of reference-style markdown (CR-011).** Not tested in a browser.

## 6. Appendix

**Commands run (short output):**

```
git status / log -15 / tag      clean, HEAD 1224478, tags v0.1 v1.0
uv sync --locked                Resolved 134 packages; Checked 127
uv run pytest -q                700 passed, 3 deselected in 29.19s
uv run ruff check .             All checks passed!
uv run ruff format --check .    124 files already formatted
uv run mypy src app eval        Success: no issues found in 46 source files
docker run zricethezav/gitleaks:v8.21.2 git /repo   129 commits scanned, no leaks found
git log --all -p | grep <key patterns>              2 hits, both fake test keys
python -m app eval --out <scratch>                  23/23, 26/26, MRR 0.631
python -m app eval --holdout --out <scratch>        5/6, 7/8, MRR 0.669
```

Offline reproduction scripts (scripted `FakeLLMClient`, real registry, real index) were run from
the session scratchpad: `repro1.py` (CR-001, CR-002, CR-003, CR-004, CR-009), `repro2.py` (index
size, numeric coverage, brand hits in chunks) and `substr.py` (keyword-substring audit of the local
eval logs). Nothing was written to the repository except this file.

**Real-model spend:** 8 pipeline turns on the `dev` profile (gpt-5.4-nano for both calls), run in
two batches capped at $0.08 each: $0.0066 + $0.0041 = **$0.0107**. No turn logs were written
(`logger=None`).

## Status after E6

Added after the review; not part of it. Each finding CR-0NN is ticket CW-6NN on branch
`epic/e6-review-fixes`. FIXED means the behavior changed in code, or a stale document was
corrected or a test added that closes the finding. DOCUMENTED means the behavior is unchanged and
the gap is now stated (README, ADR addendum, `docs/ci.md` or a Backlog row). Test names are
`tests/<file>::<test>`.

| CR | Severity | Fix commit(s) | Status | Covering test or doc | Note |
|---|---|---|---|---|---|
| CR-001 | High | `9be8d7b` | FIXED | `tests/test_pipeline.py::test_an_alias_naming_another_model_is_not_the_corpus_car`; `tests/test_postcheck.py::test_sibling_model_in_the_answer_is_not_read_as_the_retrieved_car` | An alias preceded by another brand or followed by a listed sibling-model word (`config/cars.yaml`) is no longer the corpus car and is reported as not covered |
| CR-002 | Medium | `a09b953` | FIXED | `tests/test_pipeline.py::test_everyday_words_are_not_an_outside_brand`; `tests/test_pipeline.py::test_plural_verbs_without_a_car_are_not_refused_as_unknown_car` | Trade-off: a short brand after ש, כ, מ or two prefixes is no longer matched; pinned by `tests/test_postcheck.py::test_short_brand_after_two_prefixes_is_not_caught_in_the_answer` |
| CR-003 | Medium | `b027e6e` | FIXED | `tests/test_numeric.py::test_number_only_in_the_rewritten_question_is_flagged` | Only user turns in the history window and preference values count as the user's words |
| CR-004 | Medium | `cbd5d73`, `31e9919` (code part: `9be8d7b`) | DOCUMENTED | README "Known limitations and next steps" ("The car-name post-check sees only names it knows") and Guardrails row "Car-name post-check"; `eval/reports/postcheck-adversarial.md` | Partly fixed: CW-601 flags another model written on a corpus alias. Other models of corpus brands not built on an alias, brand-less model names and unlisted brands still pass; the README claim is corrected |
| CR-005 | Medium | `f5d7031`, `ea66379` | FIXED | `tests/test_docker.py::test_documented_run_command_publishes_on_loopback_only`; `tests/test_docker.py::test_compose_publishes_on_loopback_only`; `tests/test_shared_budget.py::test_reaching_the_total_blocks_every_session_and_a_new_one`; `tests/test_ui.py::test_sessions_and_a_refresh_share_one_budget_per_process` | Docs and `compose.yaml` publish on 127.0.0.1; a process-wide cap (`llm.max_total_cost_usd`) is not reset by a refresh |
| CR-006 | Medium | `fa88e47` | FIXED | `tests/test_recommend_scope.py::test_recommendation_without_the_statement_gets_it_once` | The answer eval was not re-run, so the published ranking score is unchanged |
| CR-007 | Medium | `a671c7c` (and `5f1dc7a`) | DOCUMENTED | README TL;DR and "Answer level" lead with 62/69; README "Caveats" ("Grading was corrected only after failures"); ADR 0004 "Addendum (2026-11-01, CW-607)" | The headline and the stated bias changed; passing runs were not audited and no new run was made |
| CR-008 | Low | `252fae4` | FIXED | `tests/test_pipeline.py::test_off_topic_request_naming_a_car_is_refused_without_retrieval` | Chitchat that names a car still goes to retrieval, as before |
| CR-009 | Low | `d7601b1`, `5f1dc7a` | DOCUMENTED | README "Known limitations and next steps" ("The numeric post-check is per value and weak on small numbers"); `eval/reports/postcheck-adversarial.md` | Truncation, per-value backing, small numbers and number words are unchanged; the rewrite source is fixed by CR-003 |
| CR-010 | Low | `023ae6f` | FIXED | `tests/test_manifest.py::test_compare_names_each_changed_missing_extra_or_rechunked_article`; `tests/test_entrypoint.py::test_ingest_warns_when_an_article_changed_but_does_not_fail`; `config/corpus.lock.yaml` | New reports carry the index fingerprint and manifest hash; existing reports are not rewritten |
| CR-011 | Low (SUSPECTED) | `5211ea6` | FIXED | `tests/test_pipeline.py::test_answer_guard_rejects_field_names_ids_and_non_hebrew` (CR-011 cases); `tests/test_ui.py::test_unknown_car_names_cannot_form_links_or_images` | Refusals render as literal text; preference values in the side panel still go through markdown (Backlog) |
| CR-012 | Low | `b069ff3` | FIXED | `tests/test_turn_bounds.py::test_pipeline_sends_each_stage_its_configured_cap`; `tests/test_turn_bounds.py::test_deadline_passed_before_generate_gives_the_llm_error_reply` | README states the computed worst case; the bounds are nominal (httpx applies the timeout per operation) |
| CR-013 | Low | `39c8c18` | FIXED | `tests/test_telemetry_privacy.py::test_unknown_car_names_are_counted_never_logged`; `tests/test_telemetry_privacy.py::test_cli_logs_the_profile_from_the_environment` | |
| CR-014 | Low | `c514dff` | FIXED | `tests/test_embed_once.py::test_each_turn_embeds_the_question_once` | |
| CR-015 | Low | `8f8c9b3` | DOCUMENTED | `BOARD.md` Backlog row "One number-word module (CW-615, CR-015)" | Three number readers remain |
| CR-016 | Low | `c3cb9ad` | DOCUMENTED | `docs/decisions/0003-retrieval-tuning.md` "Addendum (2026-11-01, CW-616)" | `force_spec_box` still gates comparisons only; comments in `config.py` and `settings.yaml` updated |
| CR-017 | Low | `8a136b3`, `01cf43e` | FIXED | `BOARD.md` (E5 and CW-503 DONE); `src/carwise/retrieval/store.py` (78 chunks); `tests/test_eval_candidates.py::test_index_build_header_states_the_reports_own_chunk_count` | `docs/docker.md` was corrected by `f5d7031` |
| CR-018 | Low | `8771994` | DOCUMENTED | `docs/ci.md` "Why the retrieval eval is manual" | CI is unchanged; the retrieval eval stays manual |
| CR-019 | Info | `31e9919` | FIXED | `tests/test_postcheck_adversarial.py::test_pipeline_gives_the_declared_outcome`; `tests/test_postcheck_adversarial.py::test_committed_report_matches_the_cases`; `eval/reports/postcheck-adversarial.md` | Recall is measured on 30 scripted cases (14/23 bad answers caught, 7/7 controls clean), not on real answers |
| CR-020 | Info | `09fdd63` | DOCUMENTED | README "Caveats" (judge and recorded understand sample); ADR 0004 "Addendum (2026-11-01, CW-620): judge caveats" | The judge schema is unchanged (`passed` before `reason`); no human-labelled set |

`ea66379` (CW-621, `compose.yaml` with the port on 127.0.0.1) is not a review ticket but keeps the
CR-005 fix for the one-command Docker start.

**Summary.** Fixed in code: CR-001, CR-002, CR-003, CR-005, CR-006, CR-008, CR-010, CR-011,
CR-012, CR-013 and CR-014. Closed by a corrected document or a new test: CR-017 (stale statuses
and counts) and CR-019 (the adversarial post-check set). Only documented, with the behavior
unchanged: CR-004 (partly fixed in code by CW-601), CR-007, CR-009, CR-015, CR-016, CR-018 and
CR-020. One open gap matters most: the car-name post-check does not see other models of corpus
brands that are not built on a registry alias (for example Kia EV6 or Kia Sorento), nor model
names without a brand or brands missing from the outside list. It is stated in README "Known
limitations and next steps" and in the Guardrails row "Car-name post-check", and pinned as known
misses in `eval/reports/postcheck-adversarial.md` (sibling models 1/3 caught, brand-less models
0/1). The post-check's recall is measured only on these scripted cases (CW-619); on real answers
it has only shown that it does not fire on clean ones (README "Answer level", "Post-check").
