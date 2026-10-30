# CW-303 step 3: top_k and caps, one at a time

Same recording, e5-large, spec boxes forced (step 2), 1 run per setting (retrieval is deterministic). Chars are chunk text sent to generation.

| Setting | Passed | Sources hit | MRR | Failing questions | Mean chunks / chars per answer |
|---|---|---|---|---|---|
| current | 22/23 | 25/26 | 0.631 | rec-family-electric-scenario | 8.50 / 8160 |
| per_car_cap 2 | 22/23 | 25/26 | 0.636 | rec-family-electric-scenario | 7.05 / 6791 |
| per_car_cap 4 | 22/23 | 25/26 | 0.626 | rec-family-electric-scenario | 10.15 / 9513 |
| top_k 3 | 22/23 | 25/26 | 0.631 | rec-family-electric-scenario | 7.70 / 7557 |
| top_k 4 | 22/23 | 25/26 | 0.631 | rec-family-electric-scenario | 8.10 / 7867 |
| top_k 7 | 22/23 | 25/26 | 0.631 | rec-family-electric-scenario | 9.30 / 8848 |
| cross_car_per_car_cap 3 | 22/23 | 25/26 | 0.631 | rec-family-electric-scenario | 8.50 / 8160 |
| cross_car_top_k 16 | 22/23 | 25/26 | 0.631 | rec-family-electric-scenario | 8.50 / 8160 |
