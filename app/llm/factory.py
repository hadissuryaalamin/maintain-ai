"""Provider construction."""

from __future__ import annotations

from app.config import Settings
from app.llm.anthropic_provider import AnthropicMessagesProvider
from app.llm.base import LLMProvider
from app.llm.demo_provider import DemoProvider
from app.llm.openai_provider import OpenAIResponsesProvider


def build_provider(settings: Settings) -> LLMProvider:
    if settings.llm_provider == "openai":
        return OpenAIResponsesProvider(settings)
    if settings.llm_provider == "anthropic":
        return AnthropicMessagesProvider(settings)
    return DemoProvider()
