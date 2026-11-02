# Answer eval diff: generate v3 -> v3 (final profile)

| | Before | After |
|---|---|---|
| Passed | 64/69 | 64/69 |
| Answer cost $ | 0.2447 | 0.2584 |
| Judge cost $ | 0.2017 | 0.2148 |
| Graded turn p50 / p95 ms | 2770 / 4106 | 2445 / 4659 |
| "Another article" phrasings | 0 | 0 |
| "Excerpts" wording | 8 | 5 |
| Prompts | {'understand': 'v1', 'generate': 'v3', 'regenerate': 'v2', 'judge': 'v1', 'judge_criteria': 'v3'} | {'understand': 'v1', 'generate': 'v3', 'regenerate': 'v2', 'judge': 'v1', 'judge_criteria': 'v3'} |

| Question | Category | Before | After | Change | Failed before | Failed after |
|---|---|---|---|---|---|---|
| fact-mg-real-range | single_fact | 3/3 | 3/3 | - | - | - |
| fact-audi-rs3-power | single_fact | 3/3 | 3/3 | - | - | - |
| fact-kia-monthly-range | single_fact | 3/3 | 3/3 | - | - | - |
| fact-genesis-engine | single_fact | 3/3 | 3/3 | - | - | - |
| compare-mg-aion-range | comparison | 3/3 | 3/3 | - | - | - |
| compare-elantra-rs3-acceleration | comparison | 3/3 | 3/3 | - | - | - |
| compare-cheaper-mg-aion | comparison | 3/3 | 2/3 | REGRESSED | - | - |
| compare-pricier-elantra-link | comparison | 3/3 | 3/3 | - | - | - |
| compare-faster-genesis-link | comparison | 3/3 | 3/3 | - | - | - |
| compare-longer-range-kia-aion | comparison | 2/3 | 3/3 | fixed | judge | - |
| rec-manual-sport | recommendation | 3/3 | 2/3 | REGRESSED | - | - |
| rec-family-electric-scenario | recommendation | 1/3 | 2/3 | fixed | preference:passengers | - |
| rank-fastest | ranking | 2/3 | 2/3 | - | - | - |
| rank-cheapest | ranking | 2/3 | 2/3 | - | must_include | - |
| followup-genesis-fuel | follow_up | 3/3 | 3/3 | - | - | - |
| followup-switch-car | follow_up | 3/3 | 3/3 | - | - | - |
| trap-unknown-car-toyota | trap | 3/3 | 3/3 | - | - | - |
| trap-known-and-unknown-car | trap | 3/3 | 3/3 | - | - | - |
| trap-missing-detail | trap | 3/3 | 3/3 | - | - | - |
| trap-mixing-specs | trap | 3/3 | 3/3 | - | - | - |
| trap-missing-feature-distractors | trap | 3/3 | 3/3 | - | - | - |
| trap-injection-unknown-car | trap | 3/3 | 3/3 | - | - | - |
| trap-off-topic | trap | 3/3 | 3/3 | - | - | - |
