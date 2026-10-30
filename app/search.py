"""`python -m app search "<query>"`: inspect retrieval without an LLM.

Why it exists: to check what the retriever returns for a question (and for
README demos) at no cost. Why it prints metadata only: the output may land in
public logs or the README, and the article text belongs to the publisher.
"""

from __future__ import annotations

import argparse

from carwise.config import load_settings
from carwise.retrieval.retriever import open_retriever
from carwise.retrieval.store import IndexNotReadyError
from carwise.schemas import RetrievedChunk


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("query", help="the question, in Hebrew")
    parser.add_argument(
        "--car", action="append", dest="cars", metavar="ID", help="registry id; repeatable"
    )
    parser.add_argument("--top-k", type=int, default=None, help="default: retrieval.top_k")


def format_hits(hits: list[RetrievedChunk]) -> str:
    if not hits:
        return "no results"
    id_width = max(len("chunk_id"), *(len(hit.chunk.chunk_id) for hit in hits))
    car_width = max(len("car"), *(len(hit.chunk.car) for hit in hits))
    lines = [f"{'rank':>4}  {'score':>6}  {'chunk_id':<{id_width}}  {'car':<{car_width}}  section"]
    lines += [
        f"{rank:>4}  {hit.score:>6.3f}  {hit.chunk.chunk_id:<{id_width}}  "
        f"{hit.chunk.car:<{car_width}}  {hit.chunk.section}"
        for rank, hit in enumerate(hits, start=1)
    ]
    return "\n".join(lines)


def run(args: argparse.Namespace) -> int:
    try:
        retriever = open_retriever(load_settings())
    except IndexNotReadyError as error:
        print(error)
        return 1
    print(format_hits(retriever.search(args.query, car_ids=args.cars, top_k=args.top_k)))
    return 0
