# ADR 0004: Answer-level evaluation and the default generate prompt

- **Status:** Accepted (generate v3 stays the default; owner review pending for the next steps)
- **Date:** 2026-10-31
- **Ticket:** CW-302 (answer level)
- **Evidence:** `eval/reports/answer/` (dev runs and their re-scores), `eval/reports/answer/final/`
  (final-profile runs, the v3/v4 diff, the hold-out). Answers themselves are in the gitignored
  `eval/runs/`; committed reports hold metrics only.

## How answers are graded

Every question is played turn by turn through the real pipeline (real understand and generate
calls), and the last answer is checked in code first:

| Check | What it verifies |
|---|---|
| behavior | answer, gate refusal or out-of-scope reply, read from the refusal type |
| sources_cited | the expected cars are cited (citations are verified in code against the chunks retrieved that turn) |
| must_include / must_not_include / must_not_match | the question's keyword groups and forbidden strings or patterns |
| post_check | the CW-202 car-name and CW-206 number check did not end in a fallback |
| another_article | no "in another article" phrasing (generate rule 10) |
| false_not_mentioned | eval only: an answer that says a car's price, 0-100 or range is not mentioned while a retrieved chunk of that car states it (each "not mentioned" read in its own clause; label caveats and remarks on the user's premise skipped) |
| attribution | a number placed with car A is not one that only another retrieved car's chunks state; sums and differences of stated numbers are skipped, and the owner is the next single-car citation, else the nearest car in the same clause (before or after the number) |
| preference:* | the profile after the multi-turn scenario holds the budget, powertrain and passenger count (numbers parsed, Hebrew number words, powertrain hint words) |

An LLM judge grades only what code cannot read: the direction of seven comparisons, the
mixing-trap premise correction and the preference scenario (`eval/judge.yaml`). The judge is
gpt-5.4, a larger model than either generator, price verified on the official page
(2.50 / 0.25 / 15.00 USD per 1M tokens, Standard, under 272K context). Caps per run: answers
$0.50, judge $0.30. Reports record the prompt versions and the judge-criteria version with the
reason it changed.

Stability, per question over the runs: the same behavior, the same set of stated numbers, and the
share of answer pairs that are word for word identical (hashes only, no text in the report).

## Corrections made on the way (all re-scored on the logged answers, no new model calls)

1. Attribution counted a number the user wrote as a word ("חמישה") as the model's.
2. Attribution read a difference ("a 2.0 s gap" from 5.8 and 3.8) as a claim, and assumed the car
   is named before its figure; Hebrew also writes "370 ק״מ באיון HT".
3. Sentences were split inside citations, whose section names end with "?" ("מה התחדש?").
4. Judge criteria v2 → v3 for the Kia/Aion range comparison: either Kia figure (432 or 397) is
   enough, aligned with the same question's keyword check; changed to match the existing check,
   not to change a result.

Each was found by reading a failure, fixed with a test, and the earlier runs were re-scored from
their logs with `eval/rescore.py`; the committed reports keep both the graded and the re-scored
numbers.

## Results: generate v3 against v4

v4 (`generate.v4.txt`) added three rules to v3: (a) compare figures given under different labels
and say they differ, (b) correct a premise with the asked car's own figure, (c) say "the
articles", never "the excerpts".

Dev profile (nano generates), 1 run, re-scored: v3 21/23, v4 21/23.

**Final profile** (nano understands, gpt-5.4-mini generates), tuning set, 3 runs per question:

| | generate v3 | generate v4 |
|---|---|---|
| Passed (re-scored) | **64/69 (92.8%)** | 60/69 (87.0%) |
| single_fact / comparison / recommendation / ranking / follow_up / trap | 12/12, 17/18, 4/6, 4/6, 6/6, 21/21 | 12/12, 14/18, 4/6, 3/6, 6/6, 21/21 |
| Same behavior across runs | 23/23 | 23/23 |
| Same numbers across runs | 15/23 | 14/23 |
| Identical answer text (mean share of pairs) | 28% | 20% |
| Post-check outcomes | clean 60 | clean 60 |
| "Another article" / "excerpts" wording | 0 / 8 | 0 / 2 |
| Cost: answers / judge | $0.2447 / $0.2017 | $0.2527 / $0.1903 |
| Tokens: answers in / out | 400,092 / 18,764 | 412,147 / 19,300 |
| Graded turn p50 / p95 | 2.8 / 4.1 s | 2.7 / 4.2 s |
| Generate call p50 / p95 | 1.6 / 2.1 s | 1.5 / 2.4 s |

Questions that differ (all others 3/3 under both):

| Question | v3 | v4 | What happened |
|---|---|---|---|
| compare-longer-range-kia-aion | 2/3 | 0/3 | v4: mini names the **Aion HT** as longer (370 against Kia's 397/432) in all three runs, because only the Aion's figure carries the label "in practice"; v3 run 1 declined to compare |
| compare-elantra-rs3-acceleration | 3/3 | 2/3 | v4 run 2 says the Elantra N is quicker (5.8 s against 3.8 s) |
| rank-fastest | 2/3 | 1/3 | the "only the eight reviewed cars" statement is missing (rule 8) |
| rank-cheapest | 2/3 | 2/3 | the same statement missing once each |
| rec-family-electric-scenario | 1/3 | 1/3 | the understand step did not record the passenger count (twice under v3, once under v4); v4 also once offered the over-budget Kia EV9 and once left out the eight-cars statement |

**Decision: generate v3 stays the default**, by the agreed order: pass rate first (64 against 60),
then stability (equal behavior; v3 slightly more stable numbers and text), then cost (v3 slightly
cheaper). v4's rule (a) made mini commit to a direction it got wrong, the worst kind of error for
a comparison. v4 stays in the repository for the record.

**Rule (b), the premise correction, does not need a v5:** `trap-mixing-specs` passes 3/3 on the
final profile under both v3 and v4 (it failed on nano, the dev generator). Rule (c) did work
(8 → 2 "excerpts" phrasings) and is the one v4 change worth keeping; see "Next".

## Failures of the chosen configuration, classified (v3, final, 5 of 69 runs)

| Failure | Runs | Class |
|---|---|---|
| Kia/Aion range comparison declined | 1 | generation |
| Passenger count not stored in the profile | 2 | preference grounding check (CW-203), see below; the recommendation itself passed the judge both times |
| "Only the eight reviewed cars" missing from a ranking | 2 | generation (rule 8) |

None is a retrieval failure on the tuning set, none is a post-check fallback, and no refusal or
trap question failed in any run (21/21).

**False "not mentioned" (eval-only check, added after this run and applied by re-scoring the
logged answers):** across the 207 graded answers of v3, v4 and v5 on the final profile it finds
one case: a v3 ranking run said the C3, MG S6, Aion HT and Link & Co 01 articles give no 0-100
figure although their retrieved spec boxes state one (the Kia, correctly, does not). That run had
already failed on the eight-cars statement, so no pass count changed. A first, sentence-level
version flagged 9 places, 8 of them wrong (label caveats such as "no range in practice, but an
average of 397 km", a remark on the user's 72.7 kWh premise, a car named in another clause); the
check now reads each "not mentioned" in its own clause, and those cases are its tests. Promoting
it into the pipeline's post-check is in the Backlog.

**Passenger count (diagnosis, nothing changed):** in every failing run the third turn ("אנחנו
חמישה, עם שני ילדים קטנים") carries the flag `preference_not_from_user`: the understand step did
return a passenger update, and the CW-203 grounding check rejected it. The check keeps a value only
if half of its content words occur in the user's message; the user wrote the number as a word, so
a value normalized to digits ("5", "5 נוסעים", "5 אנשים") fails, while one that keeps the user's
words ("חמישה נוסעים", "5 אנשים, כולל שני ילדים קטנים") passes, which is what the passing runs
show. The rejected value itself is not logged, so its exact text is inferred. It is the same
number-word blind spot the attribution check had; the earlier classification "understanding" was
wrong. The fix (digits matching a number word in the message count as grounded, and rejected
values are logged) is in the Backlog.

## Hold-out (6 questions written after tuning; generate v3, final, 3 runs)

15/18 passed: single facts 9/9, comparisons 3/6, ranking 3/3; same behavior 6/6, same numbers
4/6; post-check clean on all 18; answers $0.0409. All three misses are the known retrieval
weakness (ADR 0003): the MG S6 top speed is in a prose chunk that is not retrieved, and the answer
says the figure is not mentioned rather than inventing one. Six questions is a sanity check, not a
precise estimate.

## v5: v3 plus the "the articles" wording rule only

Measured exactly like v3 and v4 (final profile, 23 questions, 3 runs, judge criteria v3, same caps;
re-scored with the false "not mentioned" check, which found nothing in it):

| | v3 | v5 |
|---|---|---|
| Passed | **64/69** | 63/69 |
| Same behavior / same numbers across runs | 23/23 / **15/23** | 23/23 / 12/23 |
| Identical answer text (mean share of pairs) | **28%** | 25% |
| "Excerpts" wording / "another article" | 8 / 0 | **0** / 2 |
| Cost: answers / judge | $0.2447 / $0.2017 | $0.2685 / $0.2030 |
| Graded turn p50 / p95 | 2.8 / 4.1 s | 2.7 / 4.2 s |

Questions that differ: v5 fixed rank-fastest (3/3) and one family-scenario run, and lost one run
each of fact-mg-real-range and trap-mixing-specs (both for writing "בכתבה אחרת" about the MG S6's
own sections, the phrase rule 10 forbids) and of rank-cheapest (the eight-cars statement).

**Decision: v3 stays the default.** The rule set before the run was that v5 replaces v3 only if
neither the pass rate nor the stability gets worse; both got worse (63 against 64; same numbers
12 against 15; identical text 25% against 28%). v5 removed the "excerpts" wording completely, but
it brought back the "another article" phrasing that v3 never produced in 69 answers. Whether the
longer rule 10, which spells out the forbidden wording, primes it, or whether it is noise, one run
per prompt cannot tell. v5 stays in the repository as a tested variant; the hold-out was not run
again because the default did not change.

## Caveats

- 23 tuning questions (69 graded answers on final) and 6 hold-out questions are small samples.
- The judge is a model and can be wrong; it grades seven questions only, against criteria that
  state the expected outcome, and its verdicts are kept with reasons in `eval/runs/` for review.
- Low temperature reduces variance, it does not remove it: behavior was identical across runs for
  every question, the stated numbers for 15 of 23, the exact wording for about a quarter of pairs.
- Latency is end to end from one laptop to the OpenAI API; it includes local retrieval on CPU.

## Next (Backlog, not done)

- Promote the false "not mentioned" check into the pipeline's post-check (a regenerate on a hit),
  after a longer run shows its precision on more answers.
- Preference grounding: count digits that match a number word in the user's message as grounded,
  and log rejected preference values so a miss can be read directly.
- The "excerpts" wording that v3 still produces (8 of 69 answers) needs a fix that does not bring
  back "another article"; a rule that only says "call them the articles", without listing the
  forbidden wording, would be the next candidate to measure.

## README note (for CW-501)

> **Answer quality.** Each answer is checked in code (behavior, cited sources, required and
> forbidden facts, the car and number post-check, and whether each number sits with the right
> car); an LLM judge (gpt-5.4, a larger model than the generator) grades only the direction of
> comparisons, the mixing trap and the preference scenario. On the final profile (gpt-5.4-mini
> generates), 3 runs of 23 questions passed 64 of 69 (93%), with no refusal or trap failure and
> the post-check clean on every answer; 6 questions written after tuning passed 15 of 18, all
> misses being one known retrieval gap where the bot correctly said the figure was not in the
> articles. A full 3-run eval costs about $0.25 for answers and $0.20 for the judge. A prompt
> variant that pushed the model to always name a winner made it name the wrong one, and one that
> only changed how sources are named lost a little accuracy and stability, so the original prompt
> stayed: changes are kept only when the measurement says so. An eval-only check for answers that
> wrongly say a figure is "not mentioned" found one such case in 207 answers. The samples are
> small; numbers are reported per run and per question.
