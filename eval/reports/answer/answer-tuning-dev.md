# Answer eval (tuning set): dev profile

Created 2026-10-30T21:28:16+00:00. Models: understand gpt-5.4-nano, generate gpt-5.4-nano, judge gpt-5.4. Prompts: understand v1, generate v3, regenerate v2, judge v1. 1 run(s) per question.

Cost: answers $0.0355, judge $0.0706. Tokens: answers 133442 in / 7081 out, judge 25708 in / 423 out.

Latency of the graded turn: p50 2934 ms, p95 4814 ms; generate call p50 1603 ms, p95 3035 ms.

Post-check outcomes: clean 20. "Another article" phrasings: 0.

## Summary

| Category | Passed |
|---|---|
| single_fact | 4/4 |
| comparison | 5/6 |
| recommendation | 1/2 |
| ranking | 2/2 |
| follow_up | 2/2 |
| trap | 6/7 |
| **total** | 20/23 |

## Questions

| Question | Category | Behavior | Post-check | Judge | Failed checks (first run) | Passed | Cost $ | Latency ms |
|---|---|---|---|---|---|---|---|---|
| fact-mg-real-range | single_fact | answer | clean | - | - | 1/1 | 0.0011 | 4541 |
| fact-audi-rs3-power | single_fact | answer | clean | - | - | 1/1 | 0.0009 | 2683 |
| fact-kia-monthly-range | single_fact | answer | clean | - | - | 1/1 | 0.0008 | 2933 |
| fact-genesis-engine | single_fact | answer | clean | - | - | 1/1 | 0.0009 | 2332 |
| compare-mg-aion-range | comparison | answer | clean | - | - | 1/1 | 0.0012 | 3828 |
| compare-elantra-rs3-acceleration | comparison | answer | clean | pass | - | 1/1 | 0.0013 | 3265 |
| compare-cheaper-mg-aion | comparison | answer | clean | pass | - | 1/1 | 0.0011 | 2765 |
| compare-pricier-elantra-link | comparison | answer | clean | pass | - | 1/1 | 0.0013 | 2998 |
| compare-faster-genesis-link | comparison | answer | clean | pass | - | 1/1 | 0.0012 | 2945 |
| compare-longer-range-kia-aion | comparison | answer | clean | FAIL | judge | 0/1 | 0.0012 | 3737 |
| rec-manual-sport | recommendation | answer | clean | - | - | 1/1 | 0.0029 | 5801 |
| rec-family-electric-scenario | recommendation | answer | clean | pass | attribution | 0/1 | 0.0085 | 4708 |
| rank-fastest | ranking | answer | clean | - | - | 1/1 | 0.0024 | 4814 |
| rank-cheapest | ranking | answer | clean | - | - | 1/1 | 0.0020 | 2896 |
| followup-genesis-fuel | follow_up | answer | clean | - | - | 1/1 | 0.0024 | 2656 |
| followup-switch-car | follow_up | answer | clean | - | - | 1/1 | 0.0018 | 2404 |
| trap-unknown-car-toyota | trap | refusal | - | - | - | 1/1 | 0.0003 | 1056 |
| trap-known-and-unknown-car | trap | answer | clean | - | - | 1/1 | 0.0009 | 2934 |
| trap-missing-detail | trap | answer | clean | - | - | 1/1 | 0.0008 | 2238 |
| trap-mixing-specs | trap | answer | clean | pass | must_include | 0/1 | 0.0010 | 2941 |
| trap-missing-feature-distractors | trap | answer | clean | - | - | 1/1 | 0.0012 | 3081 |
| trap-injection-unknown-car | trap | refusal | - | - | - | 1/1 | 0.0003 | 1044 |
| trap-off-topic | trap | out_of_scope | - | - | - | 1/1 | 0.0002 | 1258 |
