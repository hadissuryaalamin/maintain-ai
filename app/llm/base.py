"""Minimal provider-neutral interface used by the orchestration loop."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class ProviderUsage:
    input_tokens: int | None
    output_tokens: int | None
    cached_input_tokens: int | None = None
    cache_write_tokens: int | None = None
    estimated: bool = False


# --- Provider-neutral conversation -------------------------------------------------------
# The agent loop, the demo provider and the evaluation harness speak only these types. Each
# vendor adapter translates them to and from its own API shape.


@dataclass(frozen=True, slots=True)
class UserMessage:
    text: str


@dataclass(frozen=True, slots=True)
class AssistantMessage:
    text: str


@dataclass(frozen=True, slots=True)
class ToolCall:
    call_id: str
    name: str
    arguments: str  # JSON object text, exactly as the model produced it


@dataclass(frozen=True, slots=True)
class ToolResult:
    call_id: str
    output: str  # JSON envelope text produced by the application


ConversationItem = UserMessage | AssistantMessage | ToolCall | ToolResult

# Backwards-compatible name used across the codebase.
ProviderToolCall = ToolCall


@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]


_KINDS: dict[type, str] = {
    UserMessage: "user_message",
    AssistantMessage: "assistant_message",
    ToolCall: "tool_call",
    ToolResult: "tool_result",
}


def conversation_to_jsonable(items: Sequence[ConversationItem]) -> list[dict[str, Any]]:
    """Plain-dict view for budgets, token estimates and evaluation inspection."""

    return [{"kind": _KINDS[type(item)], **asdict(item)} for item in items]


def conversation_characters(items: Sequence[ConversationItem]) -> int:
    return len(json.dumps(conversation_to_jsonable(items), ensure_ascii=False))


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
