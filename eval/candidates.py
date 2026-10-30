"""Retrieval candidates for the embedding comparison (CW-305).

Why candidates are config overrides and not code: every candidate must run the
same pipeline code on the same recorded understand outputs, so the only thing
that differs between two reports is the embedding model (or the lexical flag).
Why each candidate builds its own index in a fresh directory: the build time is
part of the comparison, and the production index in data/index stays untouched.
Why one process per candidate: peak memory would otherwise mix two models.
"""

from __future__ import annotations

import shutil
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict

from carwise.config import Settings
from carwise.ingest.chunk import chunk_document
from carwise.ingest.clean import clean_html
from carwise.ingest.fetch import cache_path
from carwise.registry import Registry
from carwise.retrieval.embedder import SentenceTransformerEmbedder
from carwise.retrieval.retriever import Retriever, open_retriever
from carwise.retrieval.store import build_index
from carwise.schemas import Chunk

CANDIDATES_PATH = Path(__file__).with_name("candidates.yaml")
CANDIDATES_DIR = Path("data/candidates")
MB = 1024 * 1024


class Candidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    embeddings: dict[str, str]
    lexical: bool = False


def load_candidates(path: Path = CANDIDATES_PATH) -> dict[str, Candidate]:
    raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    return {name: Candidate.model_validate(item) for name, item in raw["candidates"].items()}


def apply(settings: Settings, name: str, candidate: Candidate) -> Settings:
    """The settings with this candidate's embedder, lexical flag and own index directory."""
    lexical = settings.retrieval.lexical.model_copy(update={"enabled": candidate.lexical})
    return settings.model_copy(
        update={
            "embeddings": settings.embeddings.model_copy(update=candidate.embeddings),
            "retrieval": settings.retrieval.model_copy(update={"lexical": lexical}),
            "paths": settings.paths.model_copy(
                update={"index_dir": str(CANDIDATES_DIR / name / "index")}
            ),
        }
    )


def cached_chunks(settings: Settings, registry: Registry) -> list[Chunk]:
    """Clean and chunk the cached articles exactly as ingest does, without fetching."""
    raw_dir = Path(settings.paths.raw_dir)
    chunks: list[Chunk] = []
    for car in registry.cars:
        path = cache_path(raw_dir, car)
        if not path.exists():
            raise FileNotFoundError(f"{path} is missing; run `python -m app ingest` first")
        document = clean_html(path.read_text(encoding="utf-8"), car_id=car.id, source_url=car.url)
        chunks += chunk_document(document, car, settings.chunking)
    return chunks


@dataclass(frozen=True)
class Prepared:
    settings: Settings
    retriever: Retriever
    resources: dict[str, float | int | str | None]


def prepare(settings: Settings, registry: Registry, name: str) -> Prepared:
    """Load the model, build a fresh index, and measure what CW-305 compares besides quality."""
    candidate = load_candidates()[name]
    settings = apply(settings, name, candidate)
    embedder = SentenceTransformerEmbedder(settings.embeddings)
    started = time.perf_counter()
    embedder.warm_up()  # downloads the pinned revision on the first run (only the files it uses)
    load_s = time.perf_counter() - started
    chunks = cached_chunks(settings, registry)
    index_dir = Path(settings.paths.index_dir)
    shutil.rmtree(index_dir, ignore_errors=True)  # generated; a fresh build is what is timed
    build = build_index(chunks, embedder, settings.chunking, index_dir)
    started = time.perf_counter()
    retriever = open_retriever(settings, embedder)  # includes the BM25 index when enabled
    open_s = time.perf_counter() - started
    lengths, window = embedder.passage_token_lengths([c.embed_text for c in chunks])
    return Prepared(
        settings=settings,
        retriever=retriever,
        resources={
            "candidate": name,
            "chunks": len(chunks),
            "token_window": window,
            "chunks_over_window": sum(length > window for length in lengths),
            "max_chunk_tokens": max(lengths),
            "model_load_s": round(load_s, 2),
            "index_build_s": round(build.seconds, 2),
            "retriever_open_s": round(open_s, 3),
            "disk_mb": disk_mb(settings.embeddings.model, settings.embeddings.revision),
            "weights_mb": round(embedder.weight_bytes() / MB),
        },
    )


def disk_mb(repo_id: str, revision: str | None) -> int | None:
    """Size of the pinned revision in the Hugging Face cache (what was downloaded)."""
    from huggingface_hub import scan_cache_dir

    for repo in scan_cache_dir().repos:
        if repo.repo_id == repo_id:
            for rev in repo.revisions:
                if revision is None or rev.commit_hash == revision:
                    return round(rev.size_on_disk / MB)
    return None


def peak_memory_mb() -> int | None:
    """Peak resident memory of this process: model, torch and the eval together."""
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        class Counters(ctypes.Structure):
            _fields_ = [  # noqa: RUF012  # ctypes needs a plain class attribute
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        counters = Counters()
        counters.cb = ctypes.sizeof(Counters)
        kernel32 = ctypes.windll.kernel32
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        kernel32.K32GetProcessMemoryInfo.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(Counters),
            wintypes.DWORD,
        ]
        process = kernel32.GetCurrentProcess()
        if not kernel32.K32GetProcessMemoryInfo(process, ctypes.byref(counters), counters.cb):
            return None
        peak_bytes: int = counters.PeakWorkingSetSize
        return round(peak_bytes / MB)
    import resource

    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss  # KiB on Linux, bytes on macOS
    return round(peak / (MB if sys.platform == "darwin" else 1024))
