# Retrieval eval: intfloat/multilingual-e5-large

Created 2026-10-30T21:10:36+00:00. 1 run(s) per question; no LLM calls (understand outputs replayed from a recording by gpt-5.4-nano, prompt v1, recorded 2026-10-30T21:09:46+00:00).

Settings: top_k 5, per_car_cap 3, cross_car_top_k 12, cross_car_per_car_cap 2, relevance_threshold 0.8, force_spec_box True, min_chars 300, max_chars 1400, embed_section_chars 60, spec_header 0, lexical off.

## Summary

| Category | Passed | Sources hit | MRR |
|---|---|---|---|
| single_fact | 3/3 | 3/3 | 1.000 |
| comparison | 1/2 | 3/4 | 0.425 |
| ranking | 1/1 | 1/1 | 0.167 |
| **total** | 5/6 | 7/8 | 0.669 |

Retrieve stage latency: p50 88 ms, p95 183 ms (query embedding plus scoring, CPU). Model warm-up 10.6 s.

## Score distribution

Best retrieval score per case. Threshold probes ask about one of the eight cars on a
topic its article does not cover (eval/negatives.yaml); CW-303 sets the relevance
threshold between the two rows.

| Best score of | n | min | Q1 | median | Q3 | max |
|---|---|---|---|---|---|---|
| answerable | 6 | 0.848 | 0.861 | 0.865 | 0.887 | 0.897 |
| threshold_probes | 0 | - | - | - | - | - |

## Questions

| Question | Category | Behavior | Expected sources: rank | Best score | Pass |
|---|---|---|---|---|---|
| holdout-fact-c3-power | single_fact | answer | citroen_c3 / הרכב הנבחן: 1 (car rank 1) | 0.883 | pass |
| holdout-fact-link-trunk | single_fact | answer | any of: link_and_co_01 / מה נותר כשהיה: 5 (car rank 5); link_and_co_01 / סביבת נהג, נוסעים: 1 (car rank 1) | 0.897 | pass |
| holdout-fact-elantra-power | single_fact | answer | any of: hyundai_elantra_n / מבחן דרכים: 1 (car rank 1); hyundai_elantra_n / איזה מנוע וביצועים: 3 (car rank 3) | 0.887 | pass |
| holdout-compare-topspeed-mg-aion | comparison | answer | mg_s6 / מה הממדים והביצועים: miss (car rank 4)<br>aion_ht / איזה נתונים עושים את HT: 5 (car rank 2) | 0.861 | FAIL |
| holdout-compare-economy-c3-elantra | comparison | answer | citroen_c3 / הרכב הנבחן: 1 (car rank 1)<br>hyundai_elantra_n / הרכב הנבחן: 2 (car rank 1) | 0.865 | pass |
| holdout-rank-most-expensive | ranking | answer | genesis_gv80 / הרכב הנבחן: 6 (car rank 2) | 0.848 | pass |

## Negative probes (no article answers these)

Behavior probes must get the out-of-scope reply; threshold probes are not graded
here, they supply the score distribution above.

| Probe | Purpose | Behavior | Intent | Best score | Pass |
|---|---|---|---|---|---|
