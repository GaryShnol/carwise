# ADR 0003: Retrieval tuning (chunk window, spec boxes, k and caps, threshold)

- **Status:** Accepted (2026-10-30)
- **Date:** 2026-10-30
- **Ticket:** CW-303
- **Evidence:** `eval/reports/cw303/step<N>/`; every number below is on the same recorded
  understand outputs (gpt-5.4-nano, 37 cases), multilingual-e5-large, 3 runs per question, all runs
  identical.

Starting point (ADR 0002): 21/23 questions, 24/26 expected sources, MRR 0.574; 5 of 75 chunks over
e5's 512-token window.

**This set is now a tuning set.** Every step below was chosen by looking at `eval/questions.yaml`,
so its numbers after CW-303 are training numbers. The hold-out estimate is the separate set of
questions written after the settings were frozen (step 5).

## Step 1: fit every chunk in the window

Two changes, in the agreed order. First, the embedded header carries the section as the
60-character label users already see (`chunking.embed_section_chars`; citations keep the full
name). That left 3 chunks over the window (longest 543 tokens with the real tokenizer), so,
second, `chunking.max_chars` went from 1500 to 1400, the largest value with none over (78 chunks,
longest exactly 512).

| e5-large | Passed | Sources hit | MRR | Chunks over 512 (max tokens) |
|---|---|---|---|---|
| before | 21/23 | 24/26 | 0.574 | 5 (647) |
| 60-character label only | 19/23 | 22/26 | 0.596 | 3 (543) |
| label + max_chars 1400 | 20/23 | 23/26 | 0.624 | 0 (512) |

The label alone cost two questions: it cut "מה המחיר של MG S6 בישראל?" off the header of a chunk
that merged five short sections, and that heading was what the mixing-trap question matched. The
smaller `max_chars` splits that merged section again and the question passes. The one question
still lost, `compare-faster-genesis-link`, is a spec-box miss (step 2). The trade is accepted: no
chunk is silently truncated any more, and MRR rose. e5-large still leads e5-base after the change
(17/23, MRR 0.554), recorded in ADR 0002.

## Step 2: the spec-box misses

Every remaining comparison miss was the car's spec box ("הרכב הנבחן": price, 0-100, range, as
label and number), which the question's wording ("זול", "מאיצה מהר") does not resemble. Each
article has exactly one chunk with table rows, and it is that box (for the Kia long-term report,
its statistics table), so "the chunk with the most table rows" identifies it deterministically.
Two options were built behind flags and measured separately:

- **A, document-side enrichment** (`chunking.spec_header`): the spec box's embedded header gets one
  more line, "נתונים:" followed by the labels of its own table rows. No model knowledge, and the
  text the model reads is unchanged.
- **B, forced inclusion** (`retrieval.force_spec_box`): for compare and recommend intents (rankings
  arrive as recommend), each named car's spec box is added to the retrieved set if the normal
  retrieval did not already return it. It keeps its real cosine score.

| e5-large | Passed | Sources hit | MRR | Comparison | Chunks over window | Chunk tokens per answer, mean / max | Extra tokens |
|---|---|---|---|---|---|---|---|
| step 1, no option | 20/23 | 23/26 | 0.624 | 4/6 | 0 | 3260 / 9990 | - |
| A, spec header | 21/23 | 24/26 | 0.613 | 5/6 | 2 (523) | 3250 / 9990 | -10 mean |
| **B, forced spec box** | **22/23** | **25/26** | **0.631** | **6/6** | 0 | 3372 / 11052 | +112 mean; +447 on the 5 answers it changes, at most +1062 |

Tokens are the chunk text sent to generation, counted with OpenAI's `o200k_base` encoding (an
estimate for gpt-5.4; prompt and question excluded).

**Chosen: B.** It fixes every comparison with no regression and keeps every chunk inside the
window, and it targets the cause: comparisons and rankings need the figures, wherever the
question's wording points. Its cost is about 450 input tokens on the answers it touches (about
$0.0003 per answer at gpt-5.4-mini's input price), and nothing elsewhere. A helped only one of the
three questions, lowered MRR, and pushed two chunks back over the window, because the extra
header line lengthens the longest spec boxes. A stays in the code, off, so the comparison can be
repeated.

The one question still missing, `rec-family-electric-scenario`, is not a retrieval miss: for its
last turn the understand step named Kia EV9, Link & Co 01 and Genesis GV80 (cars from the earlier
answers), so retrieval searched only those three, and the MG S6 and Aion HT chunks were never
candidates. ADR 0002 attributed it to the cross-car cap; that was wrong and is corrected there.

## Step 3: top_k and the caps

One knob at a time from the current values (`uv run python -m eval.sweep`, table in
`eval/reports/cw303/step3/sweep.md`; spec boxes forced as chosen in step 2):

| Setting | Passed | Sources hit | MRR | Mean chunks / characters per answer |
|---|---|---|---|---|
| **current: top_k 5, per_car_cap 3, cross_car_top_k 12, cross_car_per_car_cap 2** | **22/23** | **25/26** | **0.631** | **8.50 / 8160** |
| per_car_cap 2 | 22/23 | 25/26 | 0.636 | 7.05 / 6791 |
| per_car_cap 4 | 22/23 | 25/26 | 0.626 | 10.15 / 9513 |
| top_k 3 | 22/23 | 25/26 | 0.631 | 7.70 / 7557 |
| top_k 4 | 22/23 | 25/26 | 0.631 | 8.10 / 7867 |
| top_k 7 | 22/23 | 25/26 | 0.631 | 9.30 / 8848 |
| cross_car_per_car_cap 3 | 22/23 | 25/26 | 0.631 | 8.50 / 8160 |
| cross_car_top_k 16 | 22/23 | 25/26 | 0.631 | 8.50 / 8160 |

**Decision: no change.** Every setting passes the same 22 questions, and the one miss
(`rec-family-electric-scenario`) is not reachable by any k or cap, because its recorded plan names
other cars (step 2). The cross-car settings change nothing here because only one question in the
set names no car (`rec-manual-sport`); rankings name all eight and use per-car retrieval.

`per_car_cap 2` would send about 17% less chunk text at equal hits. It is not taken: picking
inside a flat region on 23 questions fits noise, and with the spec box forced, cap 2 leaves only
two prose chunks per car for the "closest related facts" a comparison answer offers when a detail
is missing. It is the first lever if generation cost matters (README cost section).

The recommendation miss belongs to the plan, not retrieval: when the understand step names cars
taken from earlier answers, a recommendation is searched only among them. Logged in the Backlog.

## Step 4: relevance threshold

Best cosine score per case after steps 1 to 3 (`eval/reports/cw303/step4/`):

| Best score (e5-large) | n | min | Q1 | median | Q3 | max |
|---|---|---|---|---|---|---|
| answerable questions | 20 | 0.846 | 0.867 | 0.877 | 0.886 | 0.911 |
| threshold probes (one of the eight cars, a topic its article lacks) | 8 | 0.847 | 0.855 | 0.871 | 0.881 | 0.896 |
| off-topic texts, scored directly across all cars (scratch measurement) | 7 | 0.760 | | 0.814 | | 0.823 |

The overlap is complete: the lowest probe (0.847) scores above the lowest answerable question
(`trap-missing-detail`, 0.846), and 4 of 8 probes score above the answerable Q1. A question about
a car's warranty or insurance looks, to an embedding, like the real questions about that car. No
threshold can separate them without refusing answerable questions.

The off-topic row is the six behavior probes plus "תכתוב לי שיר על הים" (write me a poem about
the sea), embedded as typed and scored against all chunks. In the pipeline they never reach
retrieval (the understand step sends them to the out-of-scope reply), so this row only shows
where a threshold could matter: if the intent check ever let one through.

**Decision: `relevance_threshold` 0.80.** It refuses none of the 20 answerable questions and none
of the probes (the eval is unchanged: 22/23, no new refusal), sits 0.046 below the lowest
answerable score (more than twice the answerable interquartile range, as margin for questions not
yet seen), and would catch 3 of the 7 off-topic texts as a backstop.

**What does the refusing.** Not the threshold. Three mechanisms, in order:

1. The registry gate: a car outside the eight is refused in code, before generation, with
   suggestions from the corpus. This is the primary mechanism.
2. The intent check: chitchat and off-topic requests get the fixed out-of-scope reply, with no
   retrieval.
3. The generation rule "not mentioned in the articles": a known car with a detail its article
   lacks (all eight threshold probes) reaches generation, which must say the detail is missing
   and offer the closest facts the retrieved chunks contain. The post-check then verifies cars
   and numbers. Whether the model follows the rule is measured by the answer eval (CW-302), not
   here.

## Step 5: hold-out questions, written after the settings were frozen

Six new questions in `eval/questions.yaml` (version 3, `holdout: true`, marked "added after
tuning"): three single facts (C3 power, Link & Co 01 boot volume, Elantra N power), two
comparisons (top speed MG S6 vs Aion HT, fuel economy C3 vs Elantra N) and one ranking (most
expensive of the eight, naming no car). Three ask for facts that are only in prose, not in a spec
box. Their understand outputs were recorded alone and merged into the recording (6 nano calls,
$0.0016); the hold-out was run once (`python -m app eval --holdout`,
`eval/reports/cw303/step5/holdout/`).

| Hold-out | Passed | Sources hit | MRR |
|---|---|---|---|
| single_fact | 3/3 | 3/3 | 1.000 |
| comparison | 1/2 | 3/4 | 0.425 |
| ranking | 1/1 | 1/1 | 0.167 |
| **total** | **5/6** | **7/8** | **0.669** |

The miss, `holdout-compare-topspeed-mg-aion`: the MG S6 top speed is in a prose chunk that ranks
fourth within its car, against `per_car_cap` 3. The forced spec box does not help, because top
speed is not in the spec table. The step 3 sweep suggests `per_car_cap` 4 would retrieve it, but
the cap is not changed now: choosing it from this result would turn the hold-out into tuning data.
It is the known weak spot of comparisons: a figure that only the prose states, ranked just
below the cap. The lowest hold-out score (0.848) is well above the 0.80 threshold, so nothing was
refused.

Six questions is a very small hold-out (one question is 17 points). It is a sanity check that the
tuned settings did not only fit the tuning set, not a precise estimate.

## Known weakness (accepted)

Comparisons can miss a figure that only the prose states. The forced spec box covers price,
0-100, range and consumption, but not, for example, top speed, which several articles give
only in the text. In the hold-out, the MG S6 top speed ranks fourth within its car against
`per_car_cap` 3, so it is not retrieved. The cap stays 3: raising it on the strength of the
hold-out result would make the hold-out a tuning set. The hold-out result (5/6) is reported
separately, as a small sanity check, never folded into the tuning numbers.

## Summary: before and after CW-303

| e5-large, same recording | Passed | Sources hit | MRR | Chunks over window | Threshold |
|---|---|---|---|---|---|
| before CW-303 (tuning set) | 21/23 | 24/26 | 0.574 | 5 | 0 (off) |
| after CW-303 (tuning set) | 22/23 | 25/26 | 0.631 | 0 | 0.80 |
| after CW-303 (hold-out, run once) | 5/6 | 7/8 | 0.669 | 0 | 0.80 |

Settings now: `chunking.max_chars` 1400, `chunking.embed_section_chars` 60, `chunking.spec_header`
false, `retrieval.force_spec_box` true, `top_k` 5, `per_car_cap` 3, `cross_car_top_k` 12,
`cross_car_per_car_cap` 2, `relevance_threshold` 0.80, lexical fusion off.

## Follow-up: CW-306, recommendations search all cars

The step 3 miss was fixed in its own ticket, not by tuning: for intent `recommend` (which also
carries rankings), retrieval now runs across all cars with the cross-car caps, and the cars the
plan names are only a hint whose spec boxes are added. On the same recording the tuning set is
23/23, 26/26, MRR 0.631; `rec-family-electric-scenario` passes (the Aion HT spec box, first within
its car); no other question regressed; recommendation and ranking questions send 12 to 19 chunks
instead of 24 to 27. The hold-out, re-run as a regression check only, is unchanged at 5/6.
(`eval/reports/cw306/`)
