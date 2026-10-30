# ADR 0002: Embedding model for retrieval

- **Status:** Accepted (2026-10-30; `config/settings.yaml` uses e5-large)
- **Date:** 2026-10-30
- **Ticket:** CW-305 (board decision D3)
- **Evidence:** `eval/reports/candidates.md` and `eval/reports/retrieval-<candidate>.{md,json}`;
  rerun with `uv run python -m app eval --candidate <name> --runs 3`, then
  `uv run python -m app eval --compare`

## Context

Retrieval is the stage the generation step depends on: a chunk that is not retrieved cannot be
cited. The provisional model, `intfloat/multilingual-e5-base`, passed 17 of 23 questions on the
CW-302 retrieval eval. Its misses were mostly the spec box of a car ("הרכב הנבחן": price, 0-100,
range as label and number), which comparison and ranking questions need.

Candidates, each pinned to a Hugging Face commit in `eval/candidates.yaml`, with the prefix rules
of its model card:

| Candidate | Model | Revision | Query / passage prefix |
|---|---|---|---|
| e5-base | intfloat/multilingual-e5-base | `d1287505…` | `query: ` / `passage: ` |
| e5-large | intfloat/multilingual-e5-large | `3d7cfbda…` | `query: ` / `passage: ` |
| bge-m3 | BAAI/bge-m3, dense output only | `5617a9f6…` | none / none |
| e5-base-lexical | e5-base, plus BM25 fused by reciprocal rank fusion (k 60) | as e5-base | as e5-base |

All four ran on the same recorded understand outputs (gpt-5.4-nano, 37 cases), so the plans
(intent, cars, rewritten question) were identical, and only retrieval differed. k, the per-car
caps and the threshold stayed at the CW-302 values (top_k 5, per_car_cap 3, cross_car_top_k 12,
cross_car_per_car_cap 2, threshold 0). Three runs per question; every candidate returned
identical chunks and scores in all three.

## Results

Cells: questions passed · expected sources hit · MRR.

| Category | e5-base | e5-large | bge-m3 | e5-base-lexical |
|---|---|---|---|---|
| single_fact | 4/4 · 4/4 · 0.875 | 4/4 · 4/4 · 1.000 | 4/4 · 4/4 · 1.000 | 4/4 · 4/4 · 0.875 |
| comparison | 2/6 · 8/12 · 0.447 | 5/6 · 11/12 · 0.374 | 4/6 · 9/12 · 0.335 | 3/6 · 9/12 · 0.336 |
| recommendation | 1/2 · 1/2 · 0.500 | 1/2 · 1/2 · 0.250 | 1/2 · 1/2 · 0.125 | 1/2 · 1/2 · 0.500 |
| ranking | 1/2 · 1/2 · 0.045 | 2/2 · 2/2 · 0.350 | 2/2 · 2/2 · 0.500 | 1/2 · 1/2 · 0.036 |
| follow_up | 2/2 · 2/2 · 0.625 | 2/2 · 2/2 · 0.750 | 2/2 · 2/2 · 0.750 | 2/2 · 2/2 · 0.750 |
| trap | 7/7 · 4/4 · 0.633 | 7/7 · 4/4 · 0.633 | 6/7 · 3/4 · 0.583 | 7/7 · 4/4 · 0.646 |
| **total** | **17/23 · 20/26 · 0.553** | **21/23 · 24/26 · 0.574** | **19/23 · 21/26 · 0.555** | **18/23 · 21/26 · 0.534** |

### Misses, with the expected chunk's rank among all chunks of its car

| Question | e5-base | e5-large | bge-m3 | e5-base-lexical |
|---|---|---|---|---|
| compare-mg-aion-range (Aion "הטווח בפועל") | 4 | hit | hit | hit |
| compare-cheaper-mg-aion (MG S6 spec box) | 5 | 7 | hit | 7 |
| compare-pricier-elantra-link (Link & Co spec box) | 8 | hit | 8 | 10 |
| compare-faster-genesis-link (Link & Co spec box) | 11 | hit | 11, and GV80 spec box 4 | 10 |
| rec-family-electric-scenario (best of four alternatives) | 2 | 1 | 2 | 2 |
| rank-cheapest (C3 spec box) | 6 | hit | hit | 6 |
| trap-mixing-specs (MG S6 price section) | hit | hit | 7 | hit |

e5-large has no regression against e5-base: its two misses are a subset of e5-base's six.
bge-m3 introduces one (`trap-mixing-specs`). The lexical fusion fixes one question and breaks
none, but lowers MRR overall.

The recommendation scenario misses for every candidate although an acceptable chunk ranks first
or second within its car. Correction (CW-303): this is not a cap problem. For its last turn the
recorded understand output names Kia EV9, Link & Co 01 and Genesis GV80, so retrieval searches
only those cars and never sees the MG S6 or Aion HT chunks; see ADR 0003.

### Score separation: answerable questions (20) vs threshold probes (8)

Best cosine score per case. Overlap: threshold probes scoring above the answerable median (0 is
ideal). Gap: answerable median minus probe median.

| Candidate | Answerable min / Q1 / median / Q3 / max | Probes min / Q1 / median / Q3 / max | Probes above answerable median | Gap |
|---|---|---|---|---|
| e5-base | 0.848 / 0.868 / 0.872 / 0.880 / 0.907 | 0.845 / 0.857 / 0.870 / 0.875 / 0.895 | 4/8 | 0.002 |
| e5-large | 0.846 / 0.866 / 0.876 / 0.886 / 0.914 | 0.847 / 0.855 / 0.861 / 0.871 / 0.896 | 2/8 | 0.015 |
| bge-m3 | 0.581 / 0.612 / 0.627 / 0.723 / 0.793 | 0.591 / 0.598 / 0.647 / 0.675 / 0.693 | 5/8 | -0.020 |
| e5-base-lexical | identical to e5-base (fusion reorders; scores stay cosine) | | 4/8 | 0.002 |

No candidate separates the two groups: every probe minimum sits at or above the answerable
minimum. e5-large separates least badly. bge-m3 has the widest answerable spread (its top
quartile is clearly higher), but its probe median is above its answerable median.

### Cost and size (CPU, this laptop)

| Candidate | Token window | Chunks over window (max tokens) | Model load s | Index build s (75 chunks) | Query p50 / p95 ms | Disk MB | Weights MB | Peak RSS MB |
|---|---|---|---|---|---|---|---|---|
| e5-base | 512 | 5 (647) | 9.5 | 15.6 | 38 / 79 | 1082 | 1061 | 2211 |
| e5-large | 512 | 5 (647) | 10.6 | 57.6 | 96 / 206 | 2157 | 2136 | 3377 |
| bge-m3 | 8192 | 0 (645) | 9.6 | 87.5 | 114 / 297 | 2187 | 2166 | 2439 |
| e5-base-lexical | 512 | 5 (647) | 9.8 | 24.5 | 51 / 99 | 1082 | 1061 | 2199 |

Load times are from a warm Hugging Face cache (the first download of e5-large took about three
minutes, bge-m3 about eight). Disk is the pinned revision in the cache: only the weight file the
loader uses is downloaded (no ONNX or OpenVINO copies). Query latency is the whole retrieve
stage (query embedding plus scoring), p50/p95 over the 60 replays that reach retrieval (20
questions x 3; gate refusals have no retrieve stage). It moved by up to 2x between identical
runs of e5-base, so read it as an order of magnitude.

## Decision

**Use `intfloat/multilingual-e5-large` at revision `3d7cfbdacd47fdda877c5cd8a79fbcc4f2a574f3`,
with the `query: ` / `passage: ` prefixes. Keep the lexical fusion in the code, off by default.**

By the agreed order:

1. **Hit rate and MRR.** e5-large is first on both totals: 21/23 questions and 24/26 sources,
   against 19/23 and 21/26 for the next candidates. The gap (four questions, three sources) is not
   "close", so the "prefer the smaller model" rule does not apply. It also fixes two of the three
   spec-box comparisons and `rank-cheapest`, with no regression.
2. **Threshold separation.** e5-large again leads (2/8 probes above the answerable median, gap
   0.015), but the separation is weak for every candidate. The registry gate stays the primary
   refusal mechanism, as CLAUDE.md section 3.2 already assumes; CW-303 decides whether a
   threshold adds anything.
3. **Cost and size.** e5-large costs about 1.1 GB more on disk and in the Docker image,
   1.2 GB more peak memory, about 4x the index build time (58 s, once per ingest) and about 2.5x
   the query latency (p95 about 0.2 s, small next to an LLM call of 1 to 3 s). Acceptable for a
   proof of concept; it would matter at scale (see below).

Why not the others:

- **bge-m3**: second on hits but worse than e5-large everywhere that counts, adds a trap
  regression, and has the worst score separation. Its 8192-token window (no truncated chunks) is
  its one real advantage, and the CW-303 header fix removes most of that need.
- **e5-base + lexical**: the question it was built to answer, "do the three spec-box comparisons
  get fixed?", is answered **no**: all three still miss, with the spec chunk at car rank 7 to 10.
  A diagnostic on the recorded queries shows why: the questions say "זול" / "יקרה" / "מאיצה מהר"
  (cheap, expensive, accelerates fast), while the spec box says "מחיר" and "0 ל-100". BM25
  cannot bridge a vocabulary gap, and prose chunks that repeat the car name outscore the
  label-and-number spec box. It is kept behind `retrieval.lexical.enabled` (default off) because
  it costs nothing when off and is the natural place for a later query-expansion experiment.
- **e5-base**: smallest and fastest, but six misses.

## Caveats

- **Weak score separation, for every candidate.** No embedding model separates answerable
  questions from the threshold probes: every probe minimum sits at or above the answerable
  minimum, and even e5-large has 2 of 8 probes above the answerable median. The registry gate
  (a car outside the eight) stays the main refusal mechanism, together with the generation
  rule "not mentioned in the articles"; a similarity threshold can at most catch the clearly
  off-topic case.
- **Not a hold-out after tuning.** CW-303 tunes chunking, k, caps and the threshold on this same
  question set, so after CW-303 its numbers are training numbers, not a hold-out estimate. The
  hold-out result is the separate set of questions written after tuning (CW-303 step 5).

- **Small sample.** 23 questions and 26 expected sources: one question is 4 points of pass rate.
  The ranking between e5-large and the rest is clear; finer differences (bge-m3 vs lexical) are
  within noise.
- **One recording.** The plans come from one gpt-5.4-nano run. A different rewrite of the same
  question can move a chunk's rank (seen in CW-302 for the recommendation scenario between two
  recordings). Every candidate saw the same plans, so the comparison is fair, but absolute numbers
  could shift with a new recording.
- **e5 prefixes.** Both e5 models were run with the `query: ` / `passage: ` prefixes their model
  cards require; bge-m3 without instructions, as its card recommends for dense retrieval. No
  prefix variants were tried.
- **No tuning yet.** k, caps, threshold and chunk size are the CW-302 values. Tuning (CW-303) may
  narrow or widen the gaps; it should be run on the chosen model.
- **Truncation.** Both e5 models silently truncate 5 of 75 chunks (up to 647 tokens against 512).
  The CW-303 plan shortens the section header in the embedded text first; until then, the tails
  of those chunks are invisible to e5.
- **MRR on comparisons** rewards the first car's chunks: per-car results are concatenated, so the
  second car's chunks start at rank 4 at best. Comparison MRR therefore reads lower for a model
  that hits more second-car sources (e5-large: 0.374 against 0.447 for e5-base).
- **Latency and memory** were measured on one Windows laptop, CPU only, in separate processes;
  peak memory includes torch and the eval itself.

## Consequences

- On approval: change `embeddings.model` and `embeddings.revision` in `config/settings.yaml`,
  rerun `python -m app ingest` (one-time build, about one minute), and set D3 to DECIDED. The CW-302
  baseline report for e5-base stays as the "before" number.
- CW-303 tunes on e5-large. The spec-box problem that remains (`compare-cheaper-mg-aion`) is a
  retrieval-design issue, not an embedding one. A candidate fix for the backlog: for compare and
  rank intents, always include each named car's spec-box chunk, because it is structured data
  that every such question needs. It is not built here.
- At scale (many teams, many corpora), the extra 1 GB per replica and the 2.5x query time are the
  first things to revisit: a hosted embedding endpoint (for example Bedrock) behind the same
  `Embedder` protocol, or e5-base with the spec-box fix, measured on this same eval.

## Re-check after the CW-303 window fix

CW-303 step 1 shortened the section part of the embedded header to the 60-character label and
lowered `chunking.max_chars` from 1500 to 1400, the largest value at which no chunk exceeds
e5's 512-token window with the real tokenizer (78 chunks, longest exactly 512 tokens, against 5
over the window before). Both e5 models were re-run on the same recording
(`eval/reports/cw303/step1/`):

| Candidate | Passed | Sources hit | MRR |
|---|---|---|---|
| e5-large, before (above) | 21/23 | 24/26 | 0.574 |
| e5-large, after | 20/23 | 23/26 | 0.624 |
| e5-base, after | 17/23 | 20/26 | 0.554 |

e5-large still leads, so the decision stands. Its one lost question
(`compare-faster-genesis-link`: the Link & Co 01 spec box moved from third to fifth within its
car, against a cap of 3) is a spec-box miss, handled in CW-303 step 2.

## README note (for CW-501)

> **Embedding model.** Four retrieval set-ups were compared on the same recorded plans
> (23 questions, 8 "no answer here" probes; no tuning): multilingual-e5-base, multilingual-e5-large,
> bge-m3 (dense), and e5-base with BM25 fused by reciprocal rank fusion. e5-large retrieved the
> expected chunks for 21 of 23 questions (e5-base: 17, bge-m3: 19, e5-base + BM25: 18) with no
> regression, at the cost of about 1 GB more memory and disk and about 0.1 to 0.2 s per query on
> CPU. BM25 did not fix the comparisons it targeted: users ask "which is cheaper", the spec box says
> "price", and keyword matching cannot bridge that. No model separates answerable questions from
> unanswerable ones by similarity score, so the car-registry gate, not a score threshold, does the
> refusing, with the "not mentioned in the articles" rule in generation. The sample is small
> (23 questions; one question is 4 points), and because the same questions are later used
> for tuning, the published hold-out number comes from questions written after tuning.
> Details: `docs/decisions/0002-embedding-model.md`.
