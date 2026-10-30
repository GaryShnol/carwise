# Answer eval (holdout set): dev profile

Created 2026-10-30T21:40:14+00:00. Models: understand gpt-5.4-nano, generate gpt-5.4-nano, judge gpt-5.4. Prompts: understand v1, generate v4, regenerate v2, judge v1, judge_criteria v2. 1 run(s) per question.

Cost: answers $0.0073, judge $0.0000. Tokens: answers 30628 in / 920 out, judge 0 in / 0 out.

Latency of the graded turn: p50 3009 ms, p95 3187 ms; generate call p50 1450 ms, p95 1794 ms.

Post-check outcomes: clean 6. "Another article" phrasings: 0; "excerpts" wording: 0.

## Summary

| Category | Passed |
|---|---|
| single_fact | 3/3 |
| comparison | 1/2 |
| ranking | 1/1 |
| **total** | 5/6 |

## Questions

| Question | Category | Behavior | Post-check | Judge | Failed checks (first run) | Passed | Cost $ | Latency ms |
|---|---|---|---|---|---|---|---|---|
| holdout-fact-c3-power | single_fact | answer | clean | - | - | 1/1 | 0.0009 | 3009 |
| holdout-fact-link-trunk | single_fact | answer | clean | - | - | 1/1 | 0.0010 | 2400 |
| holdout-fact-elantra-power | single_fact | answer | clean | - | - | 1/1 | 0.0011 | 2805 |
| holdout-compare-topspeed-mg-aion | comparison | answer | clean | - | must_include | 0/1 | 0.0011 | 3037 |
| holdout-compare-economy-c3-elantra | comparison | answer | clean | - | - | 1/1 | 0.0013 | 3151 |
| holdout-rank-most-expensive | ranking | answer | clean | - | - | 1/1 | 0.0020 | 3187 |
