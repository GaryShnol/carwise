"""One JSON line per turn in logs/turns.jsonl.

Why these fields: they are what answers "why did the bot say that, and what
did it cost?" afterwards: intent, cars, chunk ids with scores, which ids the
answer used, the gate decision, flags, tokens, cost and latency per stage.
Why no text: the user's message is theirs and the chunk text is the
publisher's, so the log keeps lengths and ids only. Secrets never pass through
here (the API key lives inside the SDK client).
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from carwise.prompts import PROMPT_VERSION
from carwise.schemas import Answer

LOG_FILE = "turns.jsonl"


def turn_record(
    answer: Answer, *, message_chars: int, profile: str, models: dict[str, str]
) -> dict[str, object]:
    return {
        "ts": datetime.now(UTC).isoformat(timespec="seconds"),
        "profile": profile,
        "models": models,
        "prompt_version": PROMPT_VERSION,
        "message_chars": message_chars,
        "intent": answer.intent.value if answer.intent else None,
        "cars": answer.cars,
        "not_covered": answer.not_covered,
        "suggested_cars": answer.suggested_cars,
        "refusal": answer.refusal.value if answer.refusal else None,
        "retrieved": [
            {"chunk_id": hit.chunk.chunk_id, "score": hit.score} for hit in answer.retrieved
        ],
        "used_chunk_ids": [source.chunk_id for source in answer.sources],
        "dropped_chunk_ids": answer.dropped_chunk_ids,
        "flags": answer.flags,
        "llm_calls": answer.llm_calls,
        "tokens": asdict(answer.usage),
        "cost_usd": round(answer.cost_usd, 8),
        "latency_ms": {stage: round(ms, 1) for stage, ms in answer.latency_ms.items()},
        "answer_chars": len(answer.text),
    }


class TurnLogger:
    def __init__(self, log_dir: Path, *, profile: str, models: dict[str, str]) -> None:
        self.path = log_dir / LOG_FILE
        self._profile = profile
        self._models = models

    def log(self, answer: Answer, *, message_chars: int) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        record = turn_record(
            answer, message_chars=message_chars, profile=self._profile, models=self._models
        )
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
