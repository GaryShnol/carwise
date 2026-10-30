"""Real model, real articles: does a question naming a car and a topic find that car?

Marked slow (it loads the embedding model) and skipped when data/raw/ is empty.
Assertions are counts and booleans with car ids only, so a failure never prints
article text: the repository and CI logs are public.
"""

from pathlib import Path

import pytest

from carwise.config import load_settings
from carwise.ingest.chunk import chunk_document
from carwise.ingest.clean import clean_html
from carwise.ingest.fetch import cache_path
from carwise.registry import load_registry
from carwise.retrieval.embedder import SentenceTransformerEmbedder
from carwise.retrieval.retriever import Retriever
from carwise.retrieval.store import ChunkStore, build_index

SETTINGS = load_settings()
REGISTRY = load_registry()
RAW_DIR = Path(SETTINGS.paths.raw_dir)

# Written for this test, not taken from the articles: a car name plus a topic.
QUERIES = {
    "citroen_c3": "כמה עולה סיטרואן C3?",
    "audi_rs3": "איך מתנהג אודי RS3 על הכביש?",
    "kia_ev9": "מה הטווח של קיה EV9 בשימוש יומיומי?",
    "hyundai_elantra_n": "איך תיבת ההילוכים הידנית באלנטרה N?",
    "link_and_co_01": "כמה מקום יש מאחור בלינק אנד קו 01?",
    "genesis_gv80": "איך תא הנוסעים של ג'נסיס GV80?",
}

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(
        not all(cache_path(RAW_DIR, car).exists() for car in REGISTRY.cars),
        reason="data/raw/ is not populated; run `python -m app ingest` first",
    ),
]


@pytest.fixture(scope="module")
def retriever(tmp_path_factory: pytest.TempPathFactory) -> Retriever:
    chunks = []
    for car in REGISTRY.cars:
        html = cache_path(RAW_DIR, car).read_text(encoding="utf-8")
        document = clean_html(html, car_id=car.id, source_url=car.url)
        chunks += chunk_document(document, car, SETTINGS.chunking)
    embedder = SentenceTransformerEmbedder(SETTINGS.embeddings)
    index_dir = tmp_path_factory.mktemp("index")
    build_index(chunks, embedder, SETTINGS.chunking, index_dir)
    return Retriever(ChunkStore(index_dir, embedder), embedder, SETTINGS.retrieval)


def test_query_naming_a_car_finds_that_car_first(retriever: Retriever) -> None:
    misses = [
        car_id
        for car_id, query in QUERIES.items()
        if retriever.search(query, top_k=1)[0].chunk.car != car_id
    ]
    assert misses == []


def test_real_retrieval_is_deterministic(retriever: Retriever) -> None:
    query = QUERIES["kia_ev9"]
    first = [(hit.chunk.chunk_id, hit.score) for hit in retriever.search(query, top_k=5)]
    second = [(hit.chunk.chunk_id, hit.score) for hit in retriever.search(query, top_k=5)]
    same = first == second
    assert same
