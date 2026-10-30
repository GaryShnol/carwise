# Retrieval eval: intfloat/multilingual-e5-base

Created 2026-10-30T19:35:00+00:00. 3 run(s) per question; no LLM calls (understand outputs replayed from a recording by gpt-5.4-nano, prompt v1, recorded 2026-10-30T19:34:19+00:00).

Settings: top_k 5, per_car_cap 3, cross_car_top_k 12, cross_car_per_car_cap 2, relevance_threshold 0.0, min_chars 300, max_chars 1500.

## Summary

| Category | Passed | Sources hit | MRR |
|---|---|---|---|
| single_fact | 4/4 | 4/4 | 0.875 |
| comparison | 1/2 | 3/4 | 0.550 |
| recommendation | 1/2 | 1/2 | 0.500 |
| ranking | 1/2 | 1/2 | 0.036 |
| follow_up | 2/2 | 2/2 | 0.625 |
| trap | 7/7 | 4/4 | 0.633 |
| **total** | 16/19 | 15/18 | 0.591 |

Retrieve stage latency: p50 73 ms, p95 160 ms (query embedding plus scoring, CPU). Model warm-up 22.8 s.

## Questions

| Question | Category | Behavior | Expected sources: rank | Best score | Pass |
|---|---|---|---|---|---|
| fact-mg-real-range | single_fact | answer | mg_s6 / הטווח: 1 (car rank 1) | 0.891 | pass |
| fact-audi-rs3-power | single_fact | answer | audi_rs3 / שוברת השיאים: 1 (car rank 1) | 0.871 | pass |
| fact-kia-monthly-range | single_fact | answer | kia_ev9 / קיה EV9: 1 (car rank 1) | 0.871 | pass |
| fact-genesis-engine | single_fact | answer | genesis_gv80 / מנוע בנזין חדש: 2 (car rank 2) | 0.906 | pass |
| compare-mg-aion-range | comparison | answer | mg_s6 / הטווח: 1 (car rank 1)<br>aion_ht / הטווח בפועל: miss (car rank 4) | 0.870 | FAIL |
| compare-elantra-rs3-acceleration | comparison | answer | hyundai_elantra_n / הרכב הנבחן: 1 (car rank 1)<br>audi_rs3 / הרכב הנבחן: 5 (car rank 2) | 0.880 | pass |
| rec-manual-sport | recommendation | answer | hyundai_elantra_n / תיבה ידנית: 1 (car rank 1) | 0.881 | pass |
| rec-family-electric-scenario | recommendation | answer | any of: mg_s6 / הרכב הנבחן: miss (car rank 10); aion_ht / הרכב הנבחן: miss (car rank 4); mg_s6 / הכי מתאים: miss (car rank 8); aion_ht / מה קורה מאחור: miss (car rank 5) | 0.883 | FAIL |
| rank-fastest | ranking | answer | audi_rs3 / הרכב הנבחן: 14 (car rank 3) | 0.858 | pass |
| rank-cheapest | ranking | answer | citroen_c3 / הרכב הנבחן: miss (car rank 6) | 0.868 | FAIL |
| followup-genesis-fuel | follow_up | answer | genesis_gv80 / מנוע בנזין חדש: 4 (car rank 4) | 0.907 | pass |
| followup-switch-car | follow_up | answer | aion_ht / הרכב הנבחן: 1 (car rank 1) | 0.908 | pass |
| trap-unknown-car-toyota | trap | refusal | - | - | pass |
| trap-known-and-unknown-car | trap | answer | genesis_gv80 / מה כולל וכמה עולה: 1 (car rank 1) | 0.874 | pass |
| trap-missing-detail | trap | answer | kia_ev9 / קיה EV9: 1 (car rank 1) | 0.848 | pass |
| trap-mixing-specs | trap | answer | mg_s6 / מה המחיר של MG S6: 5 (car rank 5) | 0.880 | pass |
| trap-missing-feature-distractors | trap | answer | link_and_co_01 / מנוע, ביצועים: 3 (car rank 3) | 0.861 | pass |
| trap-injection-unknown-car | trap | refusal | - | - | pass |
| trap-off-topic | trap | out_of_scope | - | - | pass |

## Negative probes (no article answers these)

| Probe | Behavior | Intent | Best score |
|---|---|---|---|
| neg-insurance | out_of_scope | out_of_scope | - |
| neg-change-tyre | out_of_scope | out_of_scope | - |
| neg-driving-lessons | out_of_scope | out_of_scope | - |
| neg-license-fee | out_of_scope | out_of_scope | - |
| neg-dead-battery | out_of_scope | out_of_scope | - |
| neg-sell-used-car | out_of_scope | out_of_scope | - |
