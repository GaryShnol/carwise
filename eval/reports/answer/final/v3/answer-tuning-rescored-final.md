# Answer eval (tuning-rescored set): final profile

Created 2026-10-30T21:56:27+00:00. Models: understand gpt-5.4-nano, generate gpt-5.4-mini, judge gpt-5.4. Prompts: understand v1, generate v3, regenerate v2, judge v1, judge_criteria v3. 3 run(s) per question.

Cost: answers $0.2447, judge $0.2017. Tokens: answers 400092 in / 18764 out, judge 77989 in / 1292 out.

Latency of the graded turn: p50 2770 ms, p95 4106 ms; generate call p50 1577 ms, p95 2117 ms.

Post-check outcomes: clean 60. "Another article" phrasings: 0; "excerpts" wording: 8.

Notes: judge criteria v3: compare-longer-range-kia-aion accepts either Kia figure (432 or 397), aligned with the keyword check of the same question (must_include ["432", "397"]); version 2 was ambiguous ("each figure") and was read as requiring both. Changed to match the question's existing check, not to change a result. Re-scored offline from answer-tuning-final-generatev3-20261030T215129Z: attribution check recomputed with the current code.

Stability over 3 runs: same behavior in 23/23 questions, same numbers in 15/23, identical text in 28% of answer pairs (mean).

## Summary

| Category | Passed |
|---|---|
| single_fact | 12/12 |
| comparison | 17/18 |
| recommendation | 4/6 |
| ranking | 4/6 |
| follow_up | 6/6 |
| trap | 21/21 |
| **total** | 64/69 |

## Questions

| Question | Category | Behavior | Post-check | Judge | Failed checks (first run) | Passed | Same behavior / numbers / text | Cost $ | Latency ms |
|---|---|---|---|---|---|---|---|---|---|
| fact-mg-real-range | single_fact | answer | clean | - | - | 3/3 | yes / yes / 33% | 0.0057 | 4838 |
| fact-audi-rs3-power | single_fact | answer | clean | - | - | 3/3 | yes / yes / 100% | 0.0051 | 3308 |
| fact-kia-monthly-range | single_fact | answer | clean | - | - | 3/3 | yes / yes / 33% | 0.0044 | 3914 |
| fact-genesis-engine | single_fact | answer | clean | - | - | 3/3 | yes / yes / 33% | 0.0051 | 3779 |
| compare-mg-aion-range | comparison | answer | clean | - | - | 3/3 | yes / yes / 33% | 0.0063 | 3300 |
| compare-elantra-rs3-acceleration | comparison | answer | clean | pass | - | 3/3 | yes / yes / 33% | 0.0070 | 4106 |
| compare-cheaper-mg-aion | comparison | answer | clean | pass | - | 3/3 | yes / yes / 33% | 0.0052 | 2298 |
| compare-pricier-elantra-link | comparison | answer | clean | pass | - | 3/3 | yes / NO / 0% | 0.0069 | 2565 |
| compare-faster-genesis-link | comparison | answer | clean | pass | - | 3/3 | yes / yes / 0% | 0.0059 | 2817 |
| compare-longer-range-kia-aion | comparison | answer | clean | FAIL | judge | 2/3 | yes / NO / 0% | 0.0094 | 3209 |
| rec-manual-sport | recommendation | answer | clean | - | - | 3/3 | yes / NO / 0% | 0.0262 | 4100 |
| rec-family-electric-scenario | recommendation | answer | clean | pass | preference:passengers | 1/3 | yes / NO / 0% | 0.0763 | 4258 |
| rank-fastest | ranking | answer | clean | - | - | 2/3 | yes / NO / 0% | 0.0168 | 3217 |
| rank-cheapest | ranking | answer | clean | - | must_include | 2/3 | yes / NO / 0% | 0.0155 | 3113 |
| followup-genesis-fuel | follow_up | answer | clean | - | - | 3/3 | yes / yes / 0% | 0.0132 | 2527 |
| followup-switch-car | follow_up | answer | clean | - | - | 3/3 | yes / yes / 0% | 0.0099 | 2395 |
| trap-unknown-car-toyota | trap | refusal | - | - | - | 3/3 | yes / yes / 33% | 0.0008 | 994 |
| trap-known-and-unknown-car | trap | answer | clean | - | - | 3/3 | yes / NO / 0% | 0.0052 | 2770 |
| trap-missing-detail | trap | answer | clean | - | - | 3/3 | yes / yes / 100% | 0.0044 | 2650 |
| trap-mixing-specs | trap | answer | clean | pass | - | 3/3 | yes / yes / 0% | 0.0054 | 2759 |
| trap-missing-feature-distractors | trap | answer | clean | - | - | 3/3 | yes / NO / 0% | 0.0086 | 2605 |
| trap-injection-unknown-car | trap | refusal | - | - | - | 3/3 | yes / yes / 100% | 0.0008 | 1087 |
| trap-off-topic | trap | out_of_scope | - | - | - | 3/3 | yes / yes / 100% | 0.0007 | 1089 |
