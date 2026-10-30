# Answer eval (tuning-rescored set): dev profile

Created 2026-10-30T21:37:55+00:00. Models: understand gpt-5.4-nano, generate gpt-5.4-nano, judge gpt-5.4. Prompts: understand v1, generate v4, regenerate v2, judge v1, judge_criteria v3 (re-judged: 1 question(s)). 1 run(s) per question.

Cost: answers $0.0352, judge $0.0817. Tokens: answers 138234 in / 7634 out, judge 26609 in / 397 out.

Latency of the graded turn: p50 2903 ms, p95 5405 ms; generate call p50 1746 ms, p95 3720 ms.

Post-check outcomes: clean 20. "Another article" phrasings: 0; "excerpts" wording: 2.

Notes: Re-scored offline from answer-tuning-dev-20261030T213557Z: attribution check recomputed with the current code; re-judged with criteria v3: compare-longer-range-kia-aion ($0.0092).

## Summary

| Category | Passed |
|---|---|
| single_fact | 4/4 |
| comparison | 6/6 |
| recommendation | 1/2 |
| ranking | 2/2 |
| follow_up | 2/2 |
| trap | 6/7 |
| **total** | 21/23 |

## Questions

| Question | Category | Behavior | Post-check | Judge | Failed checks (first run) | Passed | Cost $ | Latency ms |
|---|---|---|---|---|---|---|---|---|
| fact-mg-real-range | single_fact | answer | clean | - | - | 1/1 | 0.0006 | 3283 |
| fact-audi-rs3-power | single_fact | answer | clean | - | - | 1/1 | 0.0007 | 2768 |
| fact-kia-monthly-range | single_fact | answer | clean | - | - | 1/1 | 0.0005 | 2505 |
| fact-genesis-engine | single_fact | answer | clean | - | - | 1/1 | 0.0006 | 2366 |
| compare-mg-aion-range | comparison | answer | clean | - | - | 1/1 | 0.0009 | 4303 |
| compare-elantra-rs3-acceleration | comparison | answer | clean | pass | - | 1/1 | 0.0014 | 3369 |
| compare-cheaper-mg-aion | comparison | answer | clean | pass | - | 1/1 | 0.0011 | 2577 |
| compare-pricier-elantra-link | comparison | answer | clean | pass | - | 1/1 | 0.0013 | 3020 |
| compare-faster-genesis-link | comparison | answer | clean | pass | - | 1/1 | 0.0013 | 3392 |
| compare-longer-range-kia-aion | comparison | answer | clean | pass | - | 1/1 | 0.0014 | 5067 |
| rec-manual-sport | recommendation | answer | clean | - | - | 1/1 | 0.0030 | 7684 |
| rec-family-electric-scenario | recommendation | answer | clean | FAIL | judge | 0/1 | 0.0084 | 4393 |
| rank-fastest | ranking | answer | clean | - | - | 1/1 | 0.0025 | 5405 |
| rank-cheapest | ranking | answer | clean | - | - | 1/1 | 0.0025 | 4558 |
| followup-genesis-fuel | follow_up | answer | clean | - | - | 1/1 | 0.0023 | 2781 |
| followup-switch-car | follow_up | answer | clean | - | - | 1/1 | 0.0019 | 2342 |
| trap-unknown-car-toyota | trap | refusal | - | - | - | 1/1 | 0.0003 | 1026 |
| trap-known-and-unknown-car | trap | answer | clean | - | - | 1/1 | 0.0010 | 2903 |
| trap-missing-detail | trap | answer | clean | - | - | 1/1 | 0.0008 | 2642 |
| trap-mixing-specs | trap | answer | clean | FAIL | must_include, judge | 0/1 | 0.0010 | 2711 |
| trap-missing-feature-distractors | trap | answer | clean | - | - | 1/1 | 0.0012 | 3294 |
| trap-injection-unknown-car | trap | refusal | - | - | - | 1/1 | 0.0003 | 1363 |
| trap-off-topic | trap | out_of_scope | - | - | - | 1/1 | 0.0002 | 1123 |
