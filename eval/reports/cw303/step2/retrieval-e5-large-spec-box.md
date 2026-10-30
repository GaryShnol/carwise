# Retrieval eval: intfloat/multilingual-e5-large

Created 2026-10-30T20:57:43+00:00. 3 run(s) per question; no LLM calls (understand outputs replayed from a recording by gpt-5.4-nano, prompt v1, recorded 2026-10-30T19:44:51+00:00).

Settings: top_k 5, per_car_cap 3, cross_car_top_k 12, cross_car_per_car_cap 2, relevance_threshold 0.0, force_spec_box True, min_chars 300, max_chars 1400, embed_section_chars 60, spec_header 0, lexical off.

## Summary

| Category | Passed | Sources hit | MRR |
|---|---|---|---|
| single_fact | 4/4 | 4/4 | 1.000 |
| comparison | 6/6 | 12/12 | 0.409 |
| recommendation | 1/2 | 1/2 | 0.500 |
| ranking | 2/2 | 2/2 | 0.171 |
| follow_up | 2/2 | 2/2 | 0.750 |
| trap | 7/7 | 4/4 | 0.833 |
| **total** | 22/23 | 25/26 | 0.631 |

Retrieve stage latency: p50 187 ms, p95 505 ms (query embedding plus scoring, CPU). Model warm-up 11.4 s.

## Score distribution

Best retrieval score per case. Threshold probes ask about one of the eight cars on a
topic its article does not cover (eval/negatives.yaml); CW-303 sets the relevance
threshold between the two rows.

| Best score of | n | min | Q1 | median | Q3 | max |
|---|---|---|---|---|---|---|
| answerable | 20 | 0.846 | 0.867 | 0.877 | 0.886 | 0.911 |
| threshold_probes | 8 | 0.847 | 0.855 | 0.871 | 0.881 | 0.896 |

## Questions

| Question | Category | Behavior | Expected sources: rank | Best score | Pass |
|---|---|---|---|---|---|
| fact-mg-real-range | single_fact | answer | mg_s6 / הטווח: 1 (car rank 1) | 0.911 | pass |
| fact-audi-rs3-power | single_fact | answer | audi_rs3 / שוברת השיאים: 1 (car rank 1) | 0.876 | pass |
| fact-kia-monthly-range | single_fact | answer | kia_ev9 / קיה EV9: 1 (car rank 1) | 0.885 | pass |
| fact-genesis-engine | single_fact | answer | genesis_gv80 / מנוע בנזין חדש: 1 (car rank 1) | 0.905 | pass |
| compare-mg-aion-range | comparison | answer | mg_s6 / הטווח: 1 (car rank 1)<br>aion_ht / הטווח בפועל: 5 (car rank 2) | 0.876 | pass |
| compare-elantra-rs3-acceleration | comparison | answer | hyundai_elantra_n / הרכב הנבחן: 1 (car rank 1)<br>audi_rs3 / הרכב הנבחן: 4 (car rank 1) | 0.883 | pass |
| compare-cheaper-mg-aion | comparison | answer | mg_s6 / הרכב הנבחן: 7 (car rank 7)<br>aion_ht / הרכב הנבחן: 4 (car rank 1) | 0.881 | pass |
| compare-pricier-elantra-link | comparison | answer | hyundai_elantra_n / הרכב הנבחן: 3 (car rank 1)<br>link_and_co_01 / הרכב הנבחן: 6 (car rank 3) | 0.882 | pass |
| compare-faster-genesis-link | comparison | answer | genesis_gv80 / הרכב הנבחן: 6 (car rank 3)<br>link_and_co_01 / הרכב הנבחן: 7 (car rank 5) | 0.854 | pass |
| compare-longer-range-kia-aion | comparison | answer | kia_ev9 / קיה EV9: 1 (car rank 1)<br>any of: aion_ht / הרכב הנבחן: 4 (car rank 1); aion_ht / הטווח בפועל: miss (car rank 4) | 0.877 | pass |
| rec-manual-sport | recommendation | answer | hyundai_elantra_n / תיבה ידנית: 1 (car rank 1) | 0.867 | pass |
| rec-family-electric-scenario | recommendation | answer | any of: mg_s6 / הרכב הנבחן: miss (car rank 5); aion_ht / הרכב הנבחן: miss (car rank 1); mg_s6 / הכי מתאים: miss (car rank 11); aion_ht / מה קורה מאחור: miss (car rank 9) | 0.869 | FAIL |
| rank-fastest | ranking | answer | audi_rs3 / הרכב הנבחן: 7 (car rank 2) | 0.850 | pass |
| rank-cheapest | ranking | answer | citroen_c3 / הרכב הנבחן: 5 (car rank 3) | 0.864 | pass |
| followup-genesis-fuel | follow_up | answer | genesis_gv80 / מנוע בנזין חדש: 2 (car rank 2) | 0.905 | pass |
| followup-switch-car | follow_up | answer | aion_ht / הרכב הנבחן: 1 (car rank 1) | 0.899 | pass |
| trap-unknown-car-toyota | trap | refusal | - | - | pass |
| trap-known-and-unknown-car | trap | answer | genesis_gv80 / מה כולל וכמה עולה: 3 (car rank 3) | 0.872 | pass |
| trap-missing-detail | trap | answer | kia_ev9 / קיה EV9: 1 (car rank 1) | 0.846 | pass |
| trap-mixing-specs | trap | answer | mg_s6 / מה המחיר של MG S6: 1 (car rank 1) | 0.903 | pass |
| trap-missing-feature-distractors | trap | answer | link_and_co_01 / מנוע, ביצועים: 1 (car rank 1) | 0.886 | pass |
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
| thr-insurance-genesis | threshold | answer | fact | 0.896 | - |
| thr-warranty-elantra | threshold | answer | fact | 0.871 | - |
| thr-service-cost-link | threshold | answer | fact | 0.871 | - |
| thr-resale-audi | threshold | answer | fact | 0.881 | - |
| thr-towing-kia | threshold | answer | fact | 0.859 | - |
| thr-delivery-mg | threshold | answer | fact | 0.887 | - |
| thr-dealer-citroen | threshold | answer | fact | 0.847 | - |
| thr-theft-aion | threshold | answer | fact | 0.855 | - |
