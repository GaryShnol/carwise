# Retrieval eval: BAAI/bge-m3

Created 2026-10-30T20:24:52+00:00. 3 run(s) per question; no LLM calls (understand outputs replayed from a recording by gpt-5.4-nano, prompt v1, recorded 2026-10-30T19:44:51+00:00).

Settings: top_k 5, per_car_cap 3, cross_car_top_k 12, cross_car_per_car_cap 2, relevance_threshold 0.0, min_chars 300, max_chars 1500, lexical off.

## Summary

| Category | Passed | Sources hit | MRR |
|---|---|---|---|
| single_fact | 4/4 | 4/4 | 1.000 |
| comparison | 4/6 | 9/12 | 0.335 |
| recommendation | 1/2 | 1/2 | 0.125 |
| ranking | 2/2 | 2/2 | 0.500 |
| follow_up | 2/2 | 2/2 | 0.750 |
| trap | 6/7 | 3/4 | 0.583 |
| **total** | 19/23 | 21/26 | 0.555 |

Retrieve stage latency: p50 114 ms, p95 297 ms (query embedding plus scoring, CPU). Model warm-up 9.6 s.

## Score distribution

Best retrieval score per case. Threshold probes ask about one of the eight cars on a
topic its article does not cover (eval/negatives.yaml); CW-303 sets the relevance
threshold between the two rows.

| Best score of | n | min | Q1 | median | Q3 | max |
|---|---|---|---|---|---|---|
| answerable | 20 | 0.581 | 0.612 | 0.627 | 0.723 | 0.793 |
| threshold_probes | 8 | 0.591 | 0.598 | 0.647 | 0.675 | 0.693 |

## Questions

| Question | Category | Behavior | Expected sources: rank | Best score | Pass |
|---|---|---|---|---|---|
| fact-mg-real-range | single_fact | answer | mg_s6 / הטווח: 1 (car rank 1) | 0.793 | pass |
| fact-audi-rs3-power | single_fact | answer | audi_rs3 / שוברת השיאים: 1 (car rank 1) | 0.677 | pass |
| fact-kia-monthly-range | single_fact | answer | kia_ev9 / קיה EV9: 1 (car rank 1) | 0.723 | pass |
| fact-genesis-engine | single_fact | answer | genesis_gv80 / מנוע בנזין חדש: 1 (car rank 1) | 0.750 | pass |
| compare-mg-aion-range | comparison | answer | mg_s6 / הטווח: 3 (car rank 1)<br>aion_ht / הטווח בפועל: 1 (car rank 1) | 0.612 | pass |
| compare-elantra-rs3-acceleration | comparison | answer | hyundai_elantra_n / הרכב הנבחן: 5 (car rank 3)<br>audi_rs3 / הרכב הנבחן: 2 (car rank 1) | 0.620 | pass |
| compare-cheaper-mg-aion | comparison | answer | mg_s6 / הרכב הנבחן: 5 (car rank 2)<br>aion_ht / הרכב הנבחן: 1 (car rank 1) | 0.623 | pass |
| compare-pricier-elantra-link | comparison | answer | hyundai_elantra_n / הרכב הנבחן: 5 (car rank 2)<br>link_and_co_01 / הרכב הנבחן: miss (car rank 8) | 0.623 | FAIL |
| compare-faster-genesis-link | comparison | answer | genesis_gv80 / הרכב הנבחן: miss (car rank 4)<br>link_and_co_01 / הרכב הנבחן: miss (car rank 11) | 0.606 | FAIL |
| compare-longer-range-kia-aion | comparison | answer | kia_ev9 / קיה EV9: 4 (car rank 1)<br>any of: aion_ht / הרכב הנבחן: 3 (car rank 3); aion_ht / הטווח בפועל: miss (car rank 5) | 0.627 | pass |
| rec-manual-sport | recommendation | answer | hyundai_elantra_n / תיבה ידנית: 4 (car rank 2) | 0.647 | pass |
| rec-family-electric-scenario | recommendation | answer | any of: mg_s6 / הרכב הנבחן: miss (car rank 2); aion_ht / הרכב הנבחן: miss (car rank 2); mg_s6 / הכי מתאים: miss (car rank 7); aion_ht / מה קורה מאחור: miss (car rank 11) | 0.581 | FAIL |
| rank-fastest | ranking | answer | audi_rs3 / הרכב הנבחן: 2 (car rank 1) | 0.592 | pass |
| rank-cheapest | ranking | answer | citroen_c3 / הרכב הנבחן: 2 (car rank 2) | 0.620 | pass |
| followup-genesis-fuel | follow_up | answer | genesis_gv80 / מנוע בנזין חדש: 2 (car rank 2) | 0.724 | pass |
| followup-switch-car | follow_up | answer | aion_ht / הרכב הנבחן: 1 (car rank 1) | 0.744 | pass |
| trap-unknown-car-toyota | trap | refusal | - | - | pass |
| trap-known-and-unknown-car | trap | answer | genesis_gv80 / מה כולל וכמה עולה: 3 (car rank 3) | 0.649 | pass |
| trap-missing-detail | trap | answer | kia_ev9 / קיה EV9: 1 (car rank 1) | 0.595 | pass |
| trap-mixing-specs | trap | answer | mg_s6 / מה המחיר של MG S6: miss (car rank 7) | 0.748 | FAIL |
| trap-missing-feature-distractors | trap | answer | link_and_co_01 / מנוע, ביצועים: 1 (car rank 1) | 0.719 | pass |
| trap-injection-unknown-car | trap | refusal | - | - | pass |
| trap-off-topic | trap | out_of_scope | - | - | pass |

## Negative probes (no article answers these)

Behavior probes must get the out-of-scope reply; threshold probes are not graded
here, they supply the score distribution above.

| Probe | Purpose | Behavior | Intent | Best score | Pass |
|---|---|---|---|---|---|
| neg-insurance | behavior | out_of_scope | out_of_scope | - | pass |
| neg-change-tyre | behavior | out_of_scope | out_of_scope | - | pass |
| neg-driving-lessons | behavior | out_of_scope | out_of_scope | - | pass |
| neg-license-fee | behavior | out_of_scope | out_of_scope | - | pass |
| neg-dead-battery | behavior | out_of_scope | out_of_scope | - | pass |
| neg-sell-used-car | behavior | out_of_scope | out_of_scope | - | pass |
| thr-insurance-genesis | threshold | answer | fact | 0.693 | - |
| thr-warranty-elantra | threshold | answer | fact | 0.682 | - |
| thr-service-cost-link | threshold | answer | fact | 0.675 | - |
| thr-resale-audi | threshold | answer | fact | 0.616 | - |
| thr-towing-kia | threshold | answer | fact | 0.591 | - |
| thr-delivery-mg | threshold | answer | fact | 0.671 | - |
| thr-dealer-citroen | threshold | answer | fact | 0.598 | - |
| thr-theft-aion | threshold | answer | fact | 0.647 | - |
