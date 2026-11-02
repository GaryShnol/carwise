# Answer eval (holdout set): final profile

Created 2026-11-01T19:59:07+00:00. Models: understand gpt-5.4-nano, generate gpt-5.4-mini, judge gpt-5.4. Prompts: understand v1, generate v3, regenerate v2, judge v1, judge_criteria v3. 3 run(s) per question.

Corpus: manifest sha256 4c50b3b52958ffebe928ddbccf877c381690c6026b497aaf6b1b20142e81750f, index fingerprint e51d4e94a95136fbd8c9a967a30498def9836c8ddeff770985d81525b09c3ecb.

Cost: answers $0.0501, judge $0.0000. Tokens: answers 85352 in / 2817 out, judge 0 in / 0 out.

Latency of the graded turn: p50 2182 ms, p95 3439 ms; generate call p50 1102 ms, p95 1634 ms.

Post-check outcomes: clean 18. "Another article" phrasings: 0; "excerpts" wording: 0.

Notes: judge criteria v3: compare-longer-range-kia-aion accepts either Kia figure (432 or 397), aligned with the keyword check of the same question (must_include ["432", "397"]); version 2 was ambiguous ("each figure") and was read as requiring both. Changed to match the question's existing check, not to change a result.

Stability over 3 runs: same behavior in 6/6 questions, same numbers in 3/6, identical text in 17% of answer pairs (mean).

## Summary

| Category | Passed |
|---|---|
| single_fact | 9/9 |
| comparison | 5/6 |
| ranking | 2/3 |
| **total** | 16/18 |

## Questions

| Question | Category | Behavior | Post-check | Judge | Failed checks (first run) | Passed | Same behavior / numbers / text | Cost $ | Latency ms |
|---|---|---|---|---|---|---|---|---|---|
| holdout-fact-c3-power | single_fact | answer | clean | - | - | 3/3 | yes / yes / 33% | 0.0045 | 2141 |
| holdout-fact-link-trunk | single_fact | answer | clean | - | - | 3/3 | yes / NO / 0% | 0.0051 | 2182 |
| holdout-fact-elantra-power | single_fact | answer | clean | - | - | 3/3 | yes / yes / 33% | 0.0071 | 2121 |
| holdout-compare-topspeed-mg-aion | comparison | answer | clean | - | - | 2/3 | yes / NO / 0% | 0.0077 | 2380 |
| holdout-compare-economy-c3-elantra | comparison | answer | clean | - | - | 3/3 | yes / yes / 33% | 0.0087 | 2442 |
| holdout-rank-most-expensive | ranking | answer | clean | - | must_include | 2/3 | yes / NO / 0% | 0.0171 | 3292 |
