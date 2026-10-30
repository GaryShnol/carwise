# Answer eval (holdout set): final profile

Created 2026-10-30T22:06:13+00:00. Models: understand gpt-5.4-nano, generate gpt-5.4-mini, judge gpt-5.4. Prompts: understand v1, generate v3, regenerate v2, judge v1, judge_criteria v3. 3 run(s) per question.

Cost: answers $0.0409, judge $0.0000. Tokens: answers 83799 in / 2927 out, judge 0 in / 0 out.

Latency of the graded turn: p50 2668 ms, p95 2974 ms; generate call p50 1289 ms, p95 1574 ms.

Post-check outcomes: clean 18. "Another article" phrasings: 0; "excerpts" wording: 0.

Notes: judge criteria v3: compare-longer-range-kia-aion accepts either Kia figure (432 or 397), aligned with the keyword check of the same question (must_include ["432", "397"]); version 2 was ambiguous ("each figure") and was read as requiring both. Changed to match the question's existing check, not to change a result.

Stability over 3 runs: same behavior in 6/6 questions, same numbers in 4/6, identical text in 22% of answer pairs (mean).

## Summary

| Category | Passed |
|---|---|
| single_fact | 9/9 |
| comparison | 3/6 |
| ranking | 3/3 |
| **total** | 15/18 |

## Questions

| Question | Category | Behavior | Post-check | Judge | Failed checks (first run) | Passed | Same behavior / numbers / text | Cost $ | Latency ms |
|---|---|---|---|---|---|---|---|---|---|
| holdout-fact-c3-power | single_fact | answer | clean | - | - | 3/3 | yes / yes / 100% | 0.0042 | 2973 |
| holdout-fact-link-trunk | single_fact | answer | clean | - | - | 3/3 | yes / NO / 0% | 0.0053 | 2705 |
| holdout-fact-elantra-power | single_fact | answer | clean | - | - | 3/3 | yes / yes / 0% | 0.0048 | 2468 |
| holdout-compare-topspeed-mg-aion | comparison | answer | clean | - | must_include | 0/3 | yes / yes / 0% | 0.0059 | 2650 |
| holdout-compare-economy-c3-elantra | comparison | answer | clean | - | - | 3/3 | yes / yes / 33% | 0.0087 | 2662 |
| holdout-rank-most-expensive | ranking | answer | clean | - | - | 3/3 | yes / NO / 0% | 0.0120 | 2668 |
