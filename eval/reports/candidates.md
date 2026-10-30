# Retrieval candidates (CW-305)

Same recorded understand outputs for every candidate; untuned settings. Cells: questions passed · expected sources hit · MRR.

| Category | e5-base | e5-large | bge-m3 | e5-base-lexical |
|---|---|---|---|---|
| single_fact | 4/4 · 4/4 · 0.875 | 4/4 · 4/4 · 1.000 | 4/4 · 4/4 · 1.000 | 4/4 · 4/4 · 0.875 |
| comparison | 2/6 · 8/12 · 0.447 | 5/6 · 11/12 · 0.374 | 4/6 · 9/12 · 0.335 | 3/6 · 9/12 · 0.336 |
| recommendation | 1/2 · 1/2 · 0.500 | 1/2 · 1/2 · 0.250 | 1/2 · 1/2 · 0.125 | 1/2 · 1/2 · 0.500 |
| ranking | 1/2 · 1/2 · 0.045 | 2/2 · 2/2 · 0.350 | 2/2 · 2/2 · 0.500 | 1/2 · 1/2 · 0.036 |
| follow_up | 2/2 · 2/2 · 0.625 | 2/2 · 2/2 · 0.750 | 2/2 · 2/2 · 0.750 | 2/2 · 2/2 · 0.750 |
| trap | 7/7 · 4/4 · 0.633 | 7/7 · 4/4 · 0.633 | 6/7 · 3/4 · 0.583 | 7/7 · 4/4 · 0.646 |
| **total** | 17/23 · 20/26 · 0.553 | 21/23 · 24/26 · 0.574 | 19/23 · 21/26 · 0.555 | 18/23 · 21/26 · 0.534 |

## Misses (rank within the car)

| Candidate | Question | Failure |
|---|---|---|
| e5-base | compare-mg-aion-range | missed aion_ht / הטווח בפועל (car rank 4) |
| e5-base | compare-cheaper-mg-aion | missed mg_s6 / הרכב הנבחן (car rank 5) |
| e5-base | compare-pricier-elantra-link | missed link_and_co_01 / הרכב הנבחן (car rank 8) |
| e5-base | compare-faster-genesis-link | missed link_and_co_01 / הרכב הנבחן (car rank 11) |
| e5-base | rec-family-electric-scenario | missed every sources_any alternative (car ranks: mg_s6 / הרכב הנבחן 10, aion_ht / הרכב הנבחן 2, mg_s6 / הכי מתאים 8, aion_ht / מה קורה מאחור 10) |
| e5-base | rank-cheapest | missed citroen_c3 / הרכב הנבחן (car rank 6) |
| e5-large | compare-cheaper-mg-aion | missed mg_s6 / הרכב הנבחן (car rank 7) |
| e5-large | rec-family-electric-scenario | missed every sources_any alternative (car ranks: mg_s6 / הרכב הנבחן 6, aion_ht / הרכב הנבחן 1, mg_s6 / הכי מתאים 7, aion_ht / מה קורה מאחור 9) |
| bge-m3 | compare-pricier-elantra-link | missed link_and_co_01 / הרכב הנבחן (car rank 8) |
| bge-m3 | compare-faster-genesis-link | missed genesis_gv80 / הרכב הנבחן (car rank 4) |
| bge-m3 | compare-faster-genesis-link | missed link_and_co_01 / הרכב הנבחן (car rank 11) |
| bge-m3 | rec-family-electric-scenario | missed every sources_any alternative (car ranks: mg_s6 / הרכב הנבחן 2, aion_ht / הרכב הנבחן 2, mg_s6 / הכי מתאים 7, aion_ht / מה קורה מאחור 11) |
| bge-m3 | trap-mixing-specs | missed mg_s6 / מה המחיר של MG S6 (car rank 7) |
| e5-base-lexical | compare-cheaper-mg-aion | missed mg_s6 / הרכב הנבחן (car rank 7) |
| e5-base-lexical | compare-pricier-elantra-link | missed link_and_co_01 / הרכב הנבחן (car rank 10) |
| e5-base-lexical | compare-faster-genesis-link | missed link_and_co_01 / הרכב הנבחן (car rank 10) |
| e5-base-lexical | rec-family-electric-scenario | missed every sources_any alternative (car ranks: mg_s6 / הרכב הנבחן 12, aion_ht / הרכב הנבחן 2, mg_s6 / הכי מתאים 2, aion_ht / מה קורה מאחור 9) |
| e5-base-lexical | rank-cheapest | missed citroen_c3 / הרכב הנבחן (car rank 6) |

## Score separation: answerable questions vs threshold probes

Best cosine score per case. Overlap: threshold probes scoring above the answerable
median (0 is ideal). Gap: answerable median minus probe median.

| Candidate | Answerable min / Q1 / median / Q3 / max | Probes min / Q1 / median / Q3 / max | Probes above answerable median | Gap |
|---|---|---|---|---|
| e5-base | 0.848 / 0.868 / 0.872 / 0.880 / 0.907 | 0.845 / 0.857 / 0.870 / 0.875 / 0.895 | 4/8 | 0.002 |
| e5-large | 0.846 / 0.866 / 0.876 / 0.886 / 0.914 | 0.847 / 0.855 / 0.861 / 0.871 / 0.896 | 2/8 | 0.015 |
| bge-m3 | 0.581 / 0.612 / 0.627 / 0.723 / 0.793 | 0.591 / 0.598 / 0.647 / 0.675 / 0.693 | 5/8 | -0.020 |
| e5-base-lexical | 0.848 / 0.868 / 0.872 / 0.880 / 0.907 | 0.845 / 0.857 / 0.870 / 0.875 / 0.895 | 4/8 | 0.002 |

## Cost and size (CPU)

| Candidate | Token window | Chunks over window (max tokens) | Model load s | Index build s (75 chunks) | Query p50 / p95 ms | Disk MB | Weights MB | Peak RSS MB |
|---|---|---|---|---|---|---|---|---|
| e5-base | 512 | 5 (647) | 9.54 | 15.61 | 38 / 79 | 1082 | 1061 | 2211 |
| e5-large | 512 | 5 (647) | 10.58 | 57.59 | 96 / 206 | 2157 | 2136 | 3377 |
| bge-m3 | 8192 | 0 (645) | 9.57 | 87.47 | 114 / 297 | 2187 | 2166 | 2439 |
| e5-base-lexical | 512 | 5 (647) | 9.8 | 24.48 | 51 / 99 | 1082 | 1061 | 2199 |
