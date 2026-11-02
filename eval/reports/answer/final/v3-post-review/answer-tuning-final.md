# Answer eval (tuning set): final profile

Created 2026-11-01T19:57:52+00:00. Models: understand gpt-5.4-nano, generate gpt-5.4-mini, judge gpt-5.4. Prompts: understand v1, generate v3, regenerate v2, judge v1, judge_criteria v3. 3 run(s) per question.

Corpus: manifest sha256 4c50b3b52958ffebe928ddbccf877c381690c6026b497aaf6b1b20142e81750f, index fingerprint e51d4e94a95136fbd8c9a967a30498def9836c8ddeff770985d81525b09c3ecb.

Cost: answers $0.2584, judge $0.2148. Tokens: answers 397257 in / 19483 out, judge 78071 in / 1308 out.

Latency of the graded turn: p50 2445 ms, p95 4659 ms; generate call p50 1379 ms, p95 2083 ms.

Post-check outcomes: clean 60. "Another article" phrasings: 0; "excerpts" wording: 5.

Notes: judge criteria v3: compare-longer-range-kia-aion accepts either Kia figure (432 or 397), aligned with the keyword check of the same question (must_include ["432", "397"]); version 2 was ambiguous ("each figure") and was read as requiring both. Changed to match the question's existing check, not to change a result.

Stability over 3 runs: same behavior in 23/23 questions, same numbers in 12/23, identical text in 19% of answer pairs (mean).

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
| fact-mg-real-range | single_fact | answer | clean | - | - | 3/3 | yes / NO / 0% | 0.0055 | 4575 |
| fact-audi-rs3-power | single_fact | answer | clean | - | - | 3/3 | yes / NO / 33% | 0.0051 | 2368 |
| fact-kia-monthly-range | single_fact | answer | clean | - | - | 3/3 | yes / yes / 100% | 0.0049 | 2006 |
| fact-genesis-engine | single_fact | answer | clean | - | - | 3/3 | yes / yes / 0% | 0.0051 | 2483 |
| compare-mg-aion-range | comparison | answer | clean | - | - | 3/3 | yes / NO / 0% | 0.0089 | 2514 |
| compare-elantra-rs3-acceleration | comparison | answer | clean | pass | - | 3/3 | yes / yes / 0% | 0.0122 | 2489 |
| compare-cheaper-mg-aion | comparison | answer | clean | pass | - | 2/3 | yes / NO / 0% | 0.0107 | 2496 |
| compare-pricier-elantra-link | comparison | answer | clean | pass | - | 3/3 | yes / NO / 0% | 0.0076 | 2719 |
| compare-faster-genesis-link | comparison | answer | clean | pass | - | 3/3 | yes / yes / 0% | 0.0065 | 2432 |
| compare-longer-range-kia-aion | comparison | answer | clean | pass | - | 3/3 | yes / yes / 0% | 0.0070 | 2832 |
| rec-manual-sport | recommendation | answer | clean | - | - | 2/3 | yes / NO / 0% | 0.0263 | 4659 |
| rec-family-electric-scenario | recommendation | answer | clean | pass | - | 2/3 | yes / NO / 0% | 0.0728 | 4216 |
| rank-fastest | ranking | answer | clean | - | - | 2/3 | yes / NO / 0% | 0.0234 | 4907 |
| rank-cheapest | ranking | answer | clean | - | - | 2/3 | yes / NO / 0% | 0.0111 | 3446 |
| followup-genesis-fuel | follow_up | answer | clean | - | - | 3/3 | yes / yes / 0% | 0.0124 | 2157 |
| followup-switch-car | follow_up | answer | clean | - | - | 3/3 | yes / yes / 0% | 0.0123 | 2410 |
| trap-unknown-car-toyota | trap | refusal | - | - | - | 3/3 | yes / yes / 100% | 0.0008 | 839 |
| trap-known-and-unknown-car | trap | answer | clean | - | - | 3/3 | yes / yes / 0% | 0.0055 | 2333 |
| trap-missing-detail | trap | answer | clean | - | - | 3/3 | yes / NO / 0% | 0.0052 | 2511 |
| trap-mixing-specs | trap | answer | clean | pass | - | 3/3 | yes / yes / 0% | 0.0056 | 2392 |
| trap-missing-feature-distractors | trap | answer | clean | - | - | 3/3 | yes / NO / 0% | 0.0079 | 2765 |
| trap-injection-unknown-car | trap | refusal | - | - | - | 3/3 | yes / yes / 100% | 0.0008 | 1033 |
| trap-off-topic | trap | out_of_scope | - | - | - | 3/3 | yes / yes / 100% | 0.0007 | 963 |
