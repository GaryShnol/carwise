# ADR 0003: Retrieval tuning (chunk window, spec boxes, k and caps, threshold)

- **Status:** Accepted for steps 1 and 2; steps 3 to 5 follow in the same ticket
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
