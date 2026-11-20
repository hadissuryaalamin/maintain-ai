"""Network-free tests for the Anthropic Messages API (Claude) adapter."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from itertools import pairwise
from typing import Any

import anthropic
import httpx
import pytest

from app.config import Settings
from app.llm.anthropic_provider import FINAL_TOOL, AnthropicMessagesProvider
from app.llm.base import (
    AssistantMessage,
    ConversationItem,
    ProviderError,
    ProviderRequest,
    ProviderTimeoutError,
    ProviderTransientError,
    ToolCall,
    ToolResult,
    ToolSpec,
    UserMessage,
)
from app.llm.factory import build_provider

OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"incident_summary": {"type": "string"}},
    "required": ["incident_summary"],
    "additionalProperties": False,
}
PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {"machine_id": {"type": "string"}},
    "required": ["machine_id"],
    "additionalProperties": False,
}
SPEC = ToolSpec(name="get_machine_status", description="Read status.", parameters=PARAMETERS)


@dataclass
class _Block:
    type: str
    text: str | None = None
    id: str | None = None
    name: str | None = None
    input: Any = None


@dataclass
class _Usage:
    input_tokens: int = 100
    output_tokens: int = 20
    cache_read_input_tokens: int | None = 7
    cache_creation_input_tokens: int | None = 3


@dataclass
class _Message:
    id: str
    content: list[_Block]
    usage: _Usage = field(default_factory=_Usage)


@dataclass
class _Messages:
    replies: list[Any]
    calls: list[dict[str, Any]] = field(default_factory=list)

    async def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


@dataclass
class _Client:
    messages: _Messages


def _settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "_env_file": None,
        "llm_provider": "anthropic",
        "anthropic_api_key": "test-key",
    }
    values.update(overrides)
    return Settings(**values)


def _provider(*replies: Any) -> tuple[AnthropicMessagesProvider, _Messages]:
    messages = _Messages(list(replies))
    return AnthropicMessagesProvider(_settings(), client=_Client(messages)), messages


def _request(
    conversation: list[ConversationItem], tools: list[ToolSpec] | None = None
) -> ProviderRequest:
    return ProviderRequest(
        model="claude-sonnet-5-5",
        instructions="System safety policy.",
        conversation=conversation,
        tools=[SPEC] if tools is None else tools,
        output_schema=OUTPUT_SCHEMA,
        max_output_tokens=432,
        trusted_tenant_id="company-a",
    )


def _final(payload: Any) -> _Message:
    return _Message(
        id="msg-final", content=[_Block(type="tool_use", id="tu-f", name=FINAL_TOOL, input=payload)]
    )


@pytest.mark.asyncio
async def test_tools_include_final_answer_tool_and_force_tool_use() -> None:
    provider, messages = _provider(_final({"incident_summary": "ok"}))
    await provider.generate(_request([UserMessage(text="Check A2")]))
    call = messages.calls[0]
    assert call["model"] == "claude-sonnet-5-5"
    assert call["system"].startswith("System safety policy.")
    assert FINAL_TOOL in call["system"]
    assert call["max_tokens"] == 432
    # Forced tool choice ("any"/"tool") is rejected by current Claude models; the adapter
    # lets the model choose and instructs it to answer through the final-answer tool.
    assert call["tool_choice"] == {"type": "auto"}
    assert call["tools"] == [
        {"name": "get_machine_status", "description": "Read status.", "input_schema": PARAMETERS},
        {
            "name": FINAL_TOOL,
            "description": call["tools"][1]["description"],
            "input_schema": OUTPUT_SCHEMA,
        },
    ]
    assert FINAL_TOOL == "submit_diagnostic"
    assert "company-a" not in json.dumps(call)


@pytest.mark.asyncio
async def test_messages_batch_tool_calls_and_results() -> None:
    provider, messages = _provider(_final({"incident_summary": "ok"}))
    await provider.generate(
        _request(
            [
                UserMessage(text="Check A2"),
                ToolCall(call_id="a", name="get_machine_status", arguments='{"machine_id":"A2"}'),
                ToolCall(call_id="b", name="get_machine_status", arguments='{"machine_id":"A1"}'),
                ToolResult(call_id="a", output='{"ok":true}'),
                ToolResult(call_id="b", output='{"ok":false}'),
            ]
        )
    )
    assert messages.calls[0]["messages"] == [
        {"role": "user", "content": [{"type": "text", "text": "Check A2"}]},
        {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": "a",
                    "name": "get_machine_status",
                    "input": {"machine_id": "A2"},
                },
                {
                    "type": "tool_use",
                    "id": "b",
                    "name": "get_machine_status",
                    "input": {"machine_id": "A1"},
                },
            ],
        },
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "a", "content": '{"ok":true}'},
                {"type": "tool_result", "tool_use_id": "b", "content": '{"ok":false}'},
            ],
        },
    ]


@pytest.mark.asyncio
async def test_adjacent_same_role_messages_merge() -> None:
    provider, messages = _provider(_final({"incident_summary": "ok"}))
    await provider.generate(
        _request(
            [
                UserMessage(text="one"),
                AssistantMessage(text="two"),
                AssistantMessage(text="three"),
                UserMessage(text="four"),
            ]
        )
    )
    sent = messages.calls[0]["messages"]
    assert [message["role"] for message in sent] == ["user", "assistant", "user"]
    assert sent[1]["content"] == [
        {"type": "text", "text": "two"},
        {"type": "text", "text": "three"},
    ]


@pytest.mark.asyncio
async def test_leading_assistant_message_is_preceded_by_user() -> None:
    provider, messages = _provider(_final({"incident_summary": "ok"}))
    await provider.generate(
        _request(
            [
                AssistantMessage(text="[Context policy omitted 3 older messages]"),
                UserMessage(text="Now?"),
            ]
        )
    )
    sent = messages.calls[0]["messages"]
    assert sent[0]["role"] == "user"
    roles = [message["role"] for message in sent]
    assert all(first != second for first, second in pairwise(roles))
    assert sent[-1] == {"role": "user", "content": [{"type": "text", "text": "Now?"}]}


@pytest.mark.asyncio
async def test_final_answer_becomes_output_text() -> None:
    provider, _ = _provider(_final({"incident_summary": "ok"}))
    result = await provider.generate(_request([UserMessage(text="Check A2")]))
    assert result.output_text == json.dumps({"incident_summary": "ok"})
    assert result.tool_calls == []
    assert result.items == [AssistantMessage(text=result.output_text)]
    assert result.request_id == "msg-final"


@pytest.mark.asyncio
async def test_final_answer_passes_raw_json_through() -> None:
    provider, _ = _provider(_final("not an object"))
    result = await provider.generate(_request([UserMessage(text="Check A2")]))
    assert result.output_text == json.dumps("not an object")


@pytest.mark.asyncio
async def test_real_tools_win_over_final_answer() -> None:
    reply = _Message(
        id="msg-mixed",
        content=[
            _Block(type="text", text="Let me check."),
            _Block(
                type="tool_use", id="tu-1", name="get_machine_status", input={"machine_id": "A2"}
            ),
            _Block(
                type="tool_use", id="tu-f", name=FINAL_TOOL, input={"incident_summary": "early"}
            ),
        ],
    )
    provider, _ = _provider(reply)
    result = await provider.generate(_request([UserMessage(text="Check A2")]))
    assert result.output_text == ""
    assert result.tool_calls == [
        ToolCall(call_id="tu-1", name="get_machine_status", arguments='{"machine_id": "A2"}')
    ]
    assert result.items == result.tool_calls


@pytest.mark.asyncio
async def test_text_only_reply_has_no_output_text() -> None:
    provider, _ = _provider(
        _Message(id="msg-text", content=[_Block(type="text", text="Here is my answer...")])
    )
    result = await provider.generate(_request([UserMessage(text="Check A2")]))
    assert result.output_text == ""
    assert result.tool_calls == []
    assert result.items == []


@pytest.mark.asyncio
async def test_replayed_final_answer_is_plain_assistant_text() -> None:
    provider, messages = _provider(_final({"incident_summary": "ok"}))
    await provider.generate(
        _request(
            [
                UserMessage(text="First"),
                AssistantMessage(text='{"incident_summary":"before"}'),
                UserMessage(text="Again"),
            ]
        )
    )
    assert messages.calls[0]["messages"][1] == {
        "role": "assistant",
        "content": [{"type": "text", "text": '{"incident_summary":"before"}'}],
    }


@pytest.mark.asyncio
async def test_usage_mapping() -> None:
    provider, _ = _provider(_final({"incident_summary": "ok"}))
    result = await provider.generate(_request([UserMessage(text="Check A2")]))
    assert result.usage.input_tokens == 100
    assert result.usage.output_tokens == 20
    assert result.usage.cached_input_tokens == 7
    assert result.usage.cache_write_tokens == 3
    assert result.usage.estimated is False


def _status_error(
    cls: type[anthropic.APIStatusError], status: int, message: str
) -> anthropic.APIStatusError:
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx.Response(status, request=request, json={"error": {"message": message}})
    return cls(message, response=response, body={"error": {"message": message}})


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "expected", "fragment"),
    [
        (
            anthropic.APITimeoutError(request=httpx.Request("POST", "https://x")),
            ProviderTimeoutError,
            "timed out",
        ),
        (
            anthropic.APIConnectionError(request=httpx.Request("POST", "https://x")),
            ProviderTransientError,
            "temporary",
        ),
        (
            _status_error(anthropic.RateLimitError, 429, "rate limited"),
            ProviderTransientError,
            "temporary",
        ),
        (
            _status_error(anthropic.InternalServerError, 500, "boom"),
            ProviderTransientError,
            "temporary",
        ),
        (
            _status_error(anthropic.APIStatusError, 529, "Overloaded"),
            ProviderTransientError,
            "temporary",
        ),
        (
            _status_error(
                anthropic.BadRequestError,
                400,
                "Your credit balance is too low to access the Anthropic API.",
            ),
            ProviderError,
            "insufficient credit",
        ),
        (
            _status_error(anthropic.AuthenticationError, 401, "invalid x-api-key"),
            ProviderError,
            "authentication failed",
        ),
        (
            _status_error(anthropic.BadRequestError, 400, "bad schema"),
            ProviderError,
            "rejected the request",
        ),
    ],
)
async def test_error_mapping(
    error: Exception, expected: type[ProviderError], fragment: str
) -> None:
    provider, _ = _provider(error)
    with pytest.raises(expected) as raised:
        await provider.generate(_request([UserMessage(text="Check A2")]))
    assert fragment in str(raised.value)
    if expected is ProviderError:
        assert not raised.value.retryable


def test_factory_builds_anthropic_provider() -> None:
    provider = build_provider(_settings())
    assert isinstance(provider, AnthropicMessagesProvider)
    assert provider.name == "anthropic"


def test_missing_key_is_rejected() -> None:
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY is required"):
        AnthropicMessagesProvider(_settings(anthropic_api_key=None))


def test_claude_models_are_priced() -> None:
    from datetime import UTC, datetime
    from decimal import Decimal
    from pathlib import Path

    from app.llm.base import ProviderUsage
    from app.telemetry.pricing import PricingCatalog

    catalog = PricingCatalog.load(Path("config/model_pricing.yaml"))
    usage = ProviderUsage(
        input_tokens=1000, output_tokens=500, cached_input_tokens=0, cache_write_tokens=0
    )
    at = datetime(2026, 11, 22, tzinfo=UTC)
    sonnet = catalog.calculate(provider="anthropic", model="claude-sonnet-5-5", usage=usage, at=at)
    haiku = catalog.calculate(provider="anthropic", model="claude-haiku-5-5", usage=usage, at=at)
    assert sonnet.total_cost == Decimal("0.007")
    assert haiku.total_cost == Decimal("0.00035")


@pytest.mark.asyncio
async def test_truncated_reply_is_a_clear_provider_error() -> None:
    reply = _final({"incident_summary": "cut"})
    reply.stop_reason = "max_tokens"  # type: ignore[attr-defined]
    provider, _ = _provider(reply)
    with pytest.raises(ProviderError) as raised:
        await provider.generate(_request([UserMessage(text="Check A2")]))
    assert "MAX_OUTPUT_TOKENS" in str(raised.value)
    assert not raised.value.retryable
