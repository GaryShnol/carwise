# Answer eval diff: generate v3 -> v4 (dev profile)

| | Before | After |
|---|---|---|
| Passed | 21/23 | 21/23 |
| Answer cost $ | 0.0355 | 0.0352 |
| Judge cost $ | 0.0790 | 0.0817 |
| Graded turn p50 / p95 ms | 2934 / 4814 | 2903 / 5405 |
| "Another article" phrasings | 0 | 0 |
| "Excerpts" wording | not recorded | 2 |
| Prompts | {'understand': 'v1', 'generate': 'v3', 'regenerate': 'v2', 'judge': 'v1', 'judge_criteria': 'v3 (re-judged: 1 question(s))'} | {'understand': 'v1', 'generate': 'v4', 'regenerate': 'v2', 'judge': 'v1', 'judge_criteria': 'v3 (re-judged: 1 question(s))'} |

| Question | Category | Before | After | Change | Failed before | Failed after |
|---|---|---|---|---|---|---|
| fact-mg-real-range | single_fact | 1/1 | 1/1 | - | - | - |
| fact-audi-rs3-power | single_fact | 1/1 | 1/1 | - | - | - |
| fact-kia-monthly-range | single_fact | 1/1 | 1/1 | - | - | - |
| fact-genesis-engine | single_fact | 1/1 | 1/1 | - | - | - |
| compare-mg-aion-range | comparison | 1/1 | 1/1 | - | - | - |
| compare-elantra-rs3-acceleration | comparison | 1/1 | 1/1 | - | - | - |
| compare-cheaper-mg-aion | comparison | 1/1 | 1/1 | - | - | - |
| compare-pricier-elantra-link | comparison | 1/1 | 1/1 | - | - | - |
| compare-faster-genesis-link | comparison | 1/1 | 1/1 | - | - | - |
| compare-longer-range-kia-aion | comparison | 0/1 | 1/1 | fixed | judge | - |
| rec-manual-sport | recommendation | 1/1 | 1/1 | - | - | - |
| rec-family-electric-scenario | recommendation | 1/1 | 0/1 | REGRESSED | - | judge |
| rank-fastest | ranking | 1/1 | 1/1 | - | - | - |
| rank-cheapest | ranking | 1/1 | 1/1 | - | - | - |
| followup-genesis-fuel | follow_up | 1/1 | 1/1 | - | - | - |
| followup-switch-car | follow_up | 1/1 | 1/1 | - | - | - |
| trap-unknown-car-toyota | trap | 1/1 | 1/1 | - | - | - |
| trap-known-and-unknown-car | trap | 1/1 | 1/1 | - | - | - |
| trap-missing-detail | trap | 1/1 | 1/1 | - | - | - |
| trap-mixing-specs | trap | 0/1 | 0/1 | - | must_include | must_include, judge |
| trap-missing-feature-distractors | trap | 1/1 | 1/1 | - | - | - |
| trap-injection-unknown-car | trap | 1/1 | 1/1 | - | - | - |
| trap-off-topic | trap | 1/1 | 1/1 | - | - | - |
