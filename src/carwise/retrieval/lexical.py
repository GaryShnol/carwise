"""BM25 over chunk text, fused with the dense ranking by reciprocal rank fusion.

Why a lexical ranking at all: spec-box chunks ("הרכב הנבחן") are mostly labels and
numbers, which a sentence embedding represents poorly, while a question about price
or 0-100 shares exact words with them ("מחיר", "100"). Why pure Python: 75 chunks need
no search engine, and a small, readable BM25 keeps the dependency list short.

Why RRF and not a weighted sum of scores: cosine and BM25 scores live on different
scales, and RRF uses ranks only, so nothing needs calibrating. The fused order decides
which chunks are retrieved; each chunk keeps its cosine score, so the relevance gate
and the eval's score distributions mean the same thing with or without fusion.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Sequence

from carwise.config import LexicalConfig
from carwise.guardrails import HEBREW_PREFIXES, normalize
from carwise.schemas import Chunk, RetrievedChunk

_WORD = re.compile(r"\w+")
_HEBREW_WORD = re.compile(r"[א-ת]+")
_MAX_PREFIXES = 3  # same bound as the car-name matching in guardrails
_MIN_STEM = 3  # "במחיר" -> "מחיר", but "מה" is not stripped to "ה"


def terms(text: str) -> list[str]:
    """Words of the text, plus each Hebrew word without its one-letter prefixes.

    Stripping is ambiguous ("מחיר" begins with the prefix letter מ), so the original
    word is always kept and the stripped forms are added next to it. Single letters
    are dropped unless they are digits ("0" in "0-100" matters, "ל" does not).
    """
    found = []
    for word in _WORD.findall(normalize(text)):
        if len(word) == 1 and not word.isdigit():
            continue
        found.append(word)
        if _HEBREW_WORD.fullmatch(word):
            for cut in range(1, _MAX_PREFIXES + 1):
                if word[cut - 1] not in HEBREW_PREFIXES or len(word) - cut < _MIN_STEM:
                    break
                found.append(word[cut:])
    return found


class LexicalIndex:
    """Okapi BM25 with corpus-wide statistics, so a car filter does not change the scores."""

    def __init__(self, chunks: Sequence[Chunk], config: LexicalConfig) -> None:
        self._k1 = config.bm25_k1
        self._b = config.bm25_b
        self._docs = {chunk.chunk_id: Counter(terms(chunk.embed_text)) for chunk in chunks}
        lengths = [sum(counts.values()) for counts in self._docs.values()]
        self._avg_length = sum(lengths) / len(lengths) if lengths else 0.0
        frequency: Counter[str] = Counter()
        for counts in self._docs.values():
            frequency.update(counts.keys())
        total = len(self._docs)
        self._idf = {
            term: math.log((total - n + 0.5) / (n + 0.5) + 1.0) for term, n in frequency.items()
        }

    def score(self, query: str, chunk_id: str) -> float:
        counts = self._docs.get(chunk_id)
        if not counts or not self._avg_length:
            return 0.0
        length = sum(counts.values())
        norm = self._k1 * (1 - self._b + self._b * length / self._avg_length)
        total = 0.0
        for term in set(terms(query)):
            tf = counts.get(term, 0)
            if tf:
                total += self._idf[term] * tf * (self._k1 + 1) / (tf + norm)
        return total


def fuse(
    query: str, dense: Sequence[RetrievedChunk], index: LexicalIndex, rrf_k: int
) -> list[RetrievedChunk]:
    """Reciprocal rank fusion of the dense order with the BM25 order of the same chunks.

    `dense` must already be sorted. A chunk with no query word gets no lexical share
    (otherwise an arbitrary tie order would hand out points). Ties fall back to the
    cosine score, then the chunk id: the same index and query give the same order.
    """
    fused = {hit.chunk.chunk_id: 1.0 / (rrf_k + rank) for rank, hit in enumerate(dense, 1)}
    lexical = [(index.score(query, hit.chunk.chunk_id), hit.chunk.chunk_id) for hit in dense]
    ranked = sorted(((s, cid) for s, cid in lexical if s > 0), key=lambda item: (-item[0], item[1]))
    for rank, (_, chunk_id) in enumerate(ranked, 1):
        fused[chunk_id] += 1.0 / (rrf_k + rank)
    return sorted(
        dense, key=lambda hit: (-fused[hit.chunk.chunk_id], -hit.score, hit.chunk.chunk_id)
    )
