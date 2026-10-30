# Answer eval diff: generate v3 -> v5 (final profile)

| | Before | After |
|---|---|---|
| Passed | 64/69 | 63/69 |
| Answer cost $ | 0.2447 | 0.2685 |
| Judge cost $ | 0.2017 | 0.2030 |
| Graded turn p50 / p95 ms | 2770 / 4106 | 2701 / 4245 |
| "Another article" phrasings | 0 | 2 |
| "Excerpts" wording | 8 | 0 |
| Prompts | {'understand': 'v1', 'generate': 'v3', 'regenerate': 'v2', 'judge': 'v1', 'judge_criteria': 'v3'} | {'understand': 'v1', 'generate': 'v5', 'regenerate': 'v2', 'judge': 'v1', 'judge_criteria': 'v3'} |

| Question | Category | Before | After | Change | Failed before | Failed after |
|---|---|---|---|---|---|---|
| fact-mg-real-range | single_fact | 3/3 | 2/3 | REGRESSED | - | - |
| fact-audi-rs3-power | single_fact | 3/3 | 3/3 | - | - | - |
| fact-kia-monthly-range | single_fact | 3/3 | 3/3 | - | - | - |
| fact-genesis-engine | single_fact | 3/3 | 3/3 | - | - | - |
| compare-mg-aion-range | comparison | 3/3 | 3/3 | - | - | - |
| compare-elantra-rs3-acceleration | comparison | 3/3 | 3/3 | - | - | - |
| compare-cheaper-mg-aion | comparison | 3/3 | 3/3 | - | - | - |
| compare-pricier-elantra-link | comparison | 3/3 | 3/3 | - | - | - |
| compare-faster-genesis-link | comparison | 3/3 | 3/3 | - | - | - |
| compare-longer-range-kia-aion | comparison | 2/3 | 2/3 | - | judge | judge |
| rec-manual-sport | recommendation | 3/3 | 3/3 | - | - | - |
| rec-family-electric-scenario | recommendation | 1/3 | 2/3 | fixed | preference:passengers | preference:passengers |
| rank-fastest | ranking | 2/3 | 3/3 | fixed | - | - |
| rank-cheapest | ranking | 2/3 | 1/3 | REGRESSED | must_include | must_include |
| followup-genesis-fuel | follow_up | 3/3 | 3/3 | - | - | - |
| followup-switch-car | follow_up | 3/3 | 3/3 | - | - | - |
| trap-unknown-car-toyota | trap | 3/3 | 3/3 | - | - | - |
| trap-known-and-unknown-car | trap | 3/3 | 3/3 | - | - | - |
| trap-missing-detail | trap | 3/3 | 3/3 | - | - | - |
| trap-mixing-specs | trap | 3/3 | 2/3 | REGRESSED | - | - |
| trap-missing-feature-distractors | trap | 3/3 | 3/3 | - | - | - |
| trap-injection-unknown-car | trap | 3/3 | 3/3 | - | - | - |
| trap-off-topic | trap | 3/3 | 3/3 | - | - | - |
