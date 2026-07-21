"""Minimal provider-neutral interface used by the orchestration loop."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class ProviderUsage:
    input_tokens: int | None
    output_tokens: int | None
    cached_input_tokens: int | None = None
    cache_write_tokens: int | None = None
    estimated: bool = False


@dataclass(frozen=True, slots=True)
class ProviderToolCall:
    call_id: str
    name: str
    arguments: str


@dataclass(frozen=True, slots=True)
class ProviderRequest:
    model: str
    instructions: str
    input_items: list[dict[str, Any]]
    tools: list[dict[str, Any]]
    output_schema: dict[str, Any]
    max_output_tokens: int
    # Internal authorization context for local providers. Adapters must never transmit it.
    trusted_tenant_id: str | None = None


@dataclass(frozen=True, slots=True)
class ProviderResponse:
    request_id: str
    output_text: str
    tool_calls: list[ProviderToolCall]
    output_items: list[dict[str, Any]]
    usage: ProviderUsage
    metadata: dict[str, Any] = field(default_factory=dict)


class ProviderError(RuntimeError):
    category = "provider_error"
    retryable = False


class ProviderTransientError(ProviderError):
    category = "transient_provider"
    retryable = True


class ProviderTimeoutError(ProviderTransientError):
    category = "timeout"


class LLMProvider(Protocol):
    name: str

    async def generate(self, request: ProviderRequest) -> ProviderResponse: ...
