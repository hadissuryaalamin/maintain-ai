"""Explicitly opt-in paid provider smoke test; never enabled by the normal test command."""

from __future__ import annotations

import os

import pytest

from app.config import Settings
from app.llm.base import ProviderRequest, UserMessage
from app.llm.openai_provider import OpenAIResponsesProvider
from app.schemas.diagnostic import DiagnosticResult

pytestmark = pytest.mark.live


@pytest.mark.asyncio
async def test_live_openai_structured_response_smoke() -> None:
    if os.getenv("RUN_LIVE_TESTS") != "1" or not os.getenv("OPENAI_API_KEY"):
        pytest.skip("set RUN_LIVE_TESTS=1 and OPENAI_API_KEY to enable the paid smoke test")

    settings = Settings(_env_file=None, llm_provider="openai")
    provider = OpenAIResponsesProvider(settings)
    response = await provider.generate(
        ProviderRequest(
            model=settings.default_model,
            instructions=(
                "Return a short maintenance diagnostic in the supplied JSON schema. "
                "Do not call tools and do not claim any machine observation."
            ),
            conversation=[
                UserMessage(text="A synthetic machine has an unspecified unusual noise.")
            ],
            tools=[],
            output_schema=DiagnosticResult.model_json_schema(),
            max_output_tokens=600,
        )
    )

    assert response.request_id
    assert response.tool_calls == []
    assert response.usage.estimated is False
    DiagnosticResult.model_validate_json(response.output_text)
