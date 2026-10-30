# Answer eval (tuning set): final profile

Created 2026-10-30T22:14:14+00:00. Models: understand gpt-5.4-nano, generate gpt-5.4-mini, judge gpt-5.4. Prompts: understand v1, generate v5, regenerate v2, judge v1, judge_criteria v3. 3 run(s) per question.

Cost: answers $0.2685, judge $0.2030. Tokens: answers 405035 in / 19833 out, judge 78484 in / 1298 out.

Latency of the graded turn: p50 2701 ms, p95 4245 ms; generate call p50 1450 ms, p95 2320 ms.

Post-check outcomes: clean 60. "Another article" phrasings: 2; "excerpts" wording: 0.

Notes: judge criteria v3: compare-longer-range-kia-aion accepts either Kia figure (432 or 397), aligned with the keyword check of the same question (must_include ["432", "397"]); version 2 was ambiguous ("each figure") and was read as requiring both. Changed to match the question's existing check, not to change a result.

Stability over 3 runs: same behavior in 23/23 questions, same numbers in 12/23, identical text in 25% of answer pairs (mean).

## Summary

| Category | Passed |
|---|---|
| single_fact | 11/12 |
| comparison | 17/18 |
| recommendation | 5/6 |
| ranking | 4/6 |
| follow_up | 6/6 |
| trap | 20/21 |
| **total** | 63/69 |

## Questions

| Question | Category | Behavior | Post-check | Judge | Failed checks (first run) | Passed | Same behavior / numbers / text | Cost $ | Latency ms |
|---|---|---|---|---|---|---|---|---|---|
| fact-mg-real-range | single_fact | answer | clean | - | - | 2/3 | yes / NO / 0% | 0.0054 | 4073 |
| fact-audi-rs3-power | single_fact | answer | clean | - | - | 3/3 | yes / yes / 100% | 0.0046 | 2551 |
| fact-kia-monthly-range | single_fact | answer | clean | - | - | 3/3 | yes / yes / 100% | 0.0046 | 2746 |
| fact-genesis-engine | single_fact | answer | clean | - | - | 3/3 | yes / NO / 33% | 0.0051 | 2351 |
| compare-mg-aion-range | comparison | answer | clean | - | - | 3/3 | yes / yes / 0% | 0.0086 | 2842 |
| compare-elantra-rs3-acceleration | comparison | answer | clean | pass | - | 3/3 | yes / yes / 33% | 0.0069 | 2624 |
| compare-cheaper-mg-aion | comparison | answer | clean | pass | - | 3/3 | yes / yes / 0% | 0.0056 | 2641 |
| compare-pricier-elantra-link | comparison | answer | clean | pass | - | 3/3 | yes / NO / 0% | 0.0077 | 2743 |
| compare-faster-genesis-link | comparison | answer | clean | pass | - | 3/3 | yes / yes / 0% | 0.0061 | 2541 |
| compare-longer-range-kia-aion | comparison | answer | clean | FAIL | judge | 2/3 | yes / NO / 0% | 0.0110 | 3150 |
| rec-manual-sport | recommendation | answer | clean | - | - | 3/3 | yes / NO / 0% | 0.0278 | 4540 |
| rec-family-electric-scenario | recommendation | answer | clean | pass | preference:passengers | 2/3 | yes / NO / 0% | 0.0794 | 4233 |
| rank-fastest | ranking | answer | clean | - | - | 3/3 | yes / NO / 0% | 0.0217 | 3949 |
| rank-cheapest | ranking | answer | clean | - | must_include | 1/3 | yes / NO / 0% | 0.0224 | 2894 |
| followup-genesis-fuel | follow_up | answer | clean | - | - | 3/3 | yes / yes / 0% | 0.0154 | 2779 |
| followup-switch-car | follow_up | answer | clean | - | - | 3/3 | yes / yes / 0% | 0.0096 | 2787 |
| trap-unknown-car-toyota | trap | refusal | - | - | - | 3/3 | yes / yes / 100% | 0.0008 | 1008 |
| trap-known-and-unknown-car | trap | answer | clean | - | - | 3/3 | yes / yes / 0% | 0.0056 | 2435 |
| trap-missing-detail | trap | answer | clean | - | - | 3/3 | yes / NO / 0% | 0.0046 | 2462 |
| trap-mixing-specs | trap | answer | clean | pass | - | 2/3 | yes / NO / 0% | 0.0057 | 2896 |
| trap-missing-feature-distractors | trap | answer | clean | - | - | 3/3 | yes / NO / 0% | 0.0084 | 2616 |
| trap-injection-unknown-car | trap | refusal | - | - | - | 3/3 | yes / yes / 100% | 0.0008 | 1049 |
| trap-off-topic | trap | out_of_scope | - | - | - | 3/3 | yes / yes / 100% | 0.0007 | 891 |
