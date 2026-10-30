# Answer eval (tuning-rescored set): final profile

Created 2026-10-30T22:01:16+00:00. Models: understand gpt-5.4-nano, generate gpt-5.4-mini, judge gpt-5.4. Prompts: understand v1, generate v4, regenerate v2, judge v1, judge_criteria v3. 3 run(s) per question.

Cost: answers $0.2527, judge $0.1903. Tokens: answers 412147 in / 19300 out, judge 78529 in / 1290 out.

Latency of the graded turn: p50 2699 ms, p95 4244 ms; generate call p50 1456 ms, p95 2436 ms.

Post-check outcomes: clean 60. "Another article" phrasings: 0; "excerpts" wording: 2.

Notes: judge criteria v3: compare-longer-range-kia-aion accepts either Kia figure (432 or 397), aligned with the keyword check of the same question (must_include ["432", "397"]); version 2 was ambiguous ("each figure") and was read as requiring both. Changed to match the question's existing check, not to change a result. Re-scored offline from answer-tuning-final-generatev4-20261030T215631Z: attribution and false-not-mentioned checks computed with the current code.

Stability over 3 runs: same behavior in 23/23 questions, same numbers in 14/23, identical text in 20% of answer pairs (mean).

## Summary

| Category | Passed |
|---|---|
| single_fact | 12/12 |
| comparison | 14/18 |
| recommendation | 4/6 |
| ranking | 3/6 |
| follow_up | 6/6 |
| trap | 21/21 |
| **total** | 60/69 |

## Questions

| Question | Category | Behavior | Post-check | Judge | Failed checks (first run) | Passed | Same behavior / numbers / text | Cost $ | Latency ms |
|---|---|---|---|---|---|---|---|---|---|
| fact-mg-real-range | single_fact | answer | clean | - | - | 3/3 | yes / yes / 0% | 0.0055 | 3296 |
| fact-audi-rs3-power | single_fact | answer | clean | - | - | 3/3 | yes / NO / 33% | 0.0049 | 2485 |
| fact-kia-monthly-range | single_fact | answer | clean | - | - | 3/3 | yes / yes / 33% | 0.0051 | 2580 |
| fact-genesis-engine | single_fact | answer | clean | - | - | 3/3 | yes / NO / 0% | 0.0051 | 2685 |
| compare-mg-aion-range | comparison | answer | clean | - | - | 3/3 | yes / yes / 0% | 0.0063 | 2717 |
| compare-elantra-rs3-acceleration | comparison | answer | clean | pass | - | 2/3 | yes / NO / 0% | 0.0070 | 2741 |
| compare-cheaper-mg-aion | comparison | answer | clean | pass | - | 3/3 | yes / yes / 33% | 0.0055 | 2540 |
| compare-pricier-elantra-link | comparison | answer | clean | pass | - | 3/3 | yes / NO / 0% | 0.0075 | 2896 |
| compare-faster-genesis-link | comparison | answer | clean | pass | - | 3/3 | yes / yes / 0% | 0.0063 | 3240 |
| compare-longer-range-kia-aion | comparison | answer | clean | FAIL | judge | 0/3 | yes / yes / 0% | 0.0110 | 2634 |
| rec-manual-sport | recommendation | answer | clean | - | - | 3/3 | yes / NO / 0% | 0.0213 | 4243 |
| rec-family-electric-scenario | recommendation | answer | clean | FAIL | preference:passengers, judge | 1/3 | yes / NO / 0% | 0.0746 | 4080 |
| rank-fastest | ranking | answer | clean | - | must_include | 1/3 | yes / NO / 0% | 0.0165 | 3956 |
| rank-cheapest | ranking | answer | clean | - | - | 2/3 | yes / NO / 0% | 0.0222 | 3120 |
| followup-genesis-fuel | follow_up | answer | clean | - | - | 3/3 | yes / yes / 0% | 0.0141 | 2856 |
| followup-switch-car | follow_up | answer | clean | - | - | 3/3 | yes / yes / 0% | 0.0134 | 2299 |
| trap-unknown-car-toyota | trap | refusal | - | - | - | 3/3 | yes / yes / 100% | 0.0008 | 1212 |
| trap-known-and-unknown-car | trap | answer | clean | - | - | 3/3 | yes / yes / 0% | 0.0047 | 2605 |
| trap-missing-detail | trap | answer | clean | - | - | 3/3 | yes / yes / 33% | 0.0048 | 2484 |
| trap-mixing-specs | trap | answer | clean | pass | - | 3/3 | yes / yes / 33% | 0.0055 | 2530 |
| trap-missing-feature-distractors | trap | answer | clean | - | - | 3/3 | yes / NO / 0% | 0.0092 | 3085 |
| trap-injection-unknown-car | trap | refusal | - | - | - | 3/3 | yes / yes / 100% | 0.0008 | 1090 |
| trap-off-topic | trap | out_of_scope | - | - | - | 3/3 | yes / yes / 100% | 0.0007 | 1086 |
