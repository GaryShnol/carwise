"""One real call through OpenAIClient: a short Hebrew question, a valid JSON reply.

Marked live (deselected by default); run with `uv run --env-file .env pytest -m live`.
Costs a fraction of a cent. Skipped when OPENAI_API_KEY is not set.
"""

import os
import re

import pytest
from pydantic import BaseModel

from carwise.config import load_settings
from carwise.llm.openai_client import OpenAIClient

HEBREW = re.compile("[֐-׿]")

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not os.environ.get("OPENAI_API_KEY"), reason="OPENAI_API_KEY is not set"),
]


class ShortAnswer(BaseModel):
    answer: str
    mentions_numbers: bool


def test_hebrew_question_gets_valid_json() -> None:
    settings = load_settings()
    model = settings.profile().understand_model
    client = OpenAIClient(settings)
    result = client.complete_json(
        "Answer in Hebrew, in one short sentence, using only the context given by the user.",
        [{"role": "user", "content": "הקשר: לרכב הבדיקה יש 150 כוח סוס. שאלה: כמה כוח סוס יש לו?"}],
        ShortAnswer,
        model=model,
    )
    assert HEBREW.search(result.parsed.answer)
    assert "150" in result.parsed.answer and result.parsed.mentions_numbers
    assert result.usage.input_tokens > 0 and result.usage.output_tokens > 0
    assert 0 < result.cost_usd < 0.01 and result.model == model
