"""Network-free tests for the direct OpenAI Responses API adapter."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from app.llm.base import ProviderRequest
from app.llm.openai_provider import OpenAIResponsesProvider


@dataclass
class _FakeOutput:
    type: str
    call_id: str | None = None
    name: str | None = None
    arguments: str | None = None

    def model_dump(self, **_: Any) -> dict[str, Any]:
        return {
            key: value
            for key, value in {
                "type": self.type,
                "call_id": self.call_id,
                "name": self.name,
                "arguments": self.arguments,
            }.items()
            if value is not None
        }


@dataclass
class _FakeInputDetails:
    cached_tokens: int
    cache_write_tokens: int


@dataclass
class _FakeUsage:
    input_tokens: int
    output_tokens: int
    input_tokens_details: _FakeInputDetails


@dataclass
class _FakeResponse:
    id: str
    output_text: str
    output: list[_FakeOutput]
    usage: _FakeUsage


@dataclass
class _FakeResponsesEndpoint:
    response: _FakeResponse
    calls: list[dict[str, Any]] = field(default_factory=list)

    async def create(self, **kwargs: Any) -> _FakeResponse:
        self.calls.append(kwargs)
        return self.response


@dataclass
class _FakeClient:
    responses: _FakeResponsesEndpoint


@pytest.mark.asyncio
async def test_openai_adapter_sends_strict_responses_request_and_normalizes_result() -> None:
    endpoint = _FakeResponsesEndpoint(
        _FakeResponse(
            id="response-123",
            output_text="",
            output=[
                _FakeOutput(
                    type="function_call",
                    call_id="call-123",
                    name="get_machine_status",
                    arguments='{"machine_id":"A1"}',
                )
            ],
            usage=_FakeUsage(
                input_tokens=120,
                output_tokens=30,
                input_tokens_details=_FakeInputDetails(
                    cached_tokens=20,
                    cache_write_tokens=5,
                ),
            ),
        )
    )
    provider = OpenAIResponsesProvider.__new__(OpenAIResponsesProvider)
    provider.client = _FakeClient(endpoint)  # type: ignore[assignment]
    tool_schema = {
        "type": "function",
        "name": "get_machine_status",
        "description": "Read status.",
        "parameters": {
            "type": "object",
            "properties": {"machine_id": {"type": "string"}},
            "required": ["machine_id"],
            "additionalProperties": False,
        },
        "strict": True,
    }
    output_schema = {
        "type": "object",
        "properties": {"incident_summary": {"type": "string"}},
        "required": ["incident_summary"],
        "additionalProperties": False,
    }
    request = ProviderRequest(
        model="configured-model",
        instructions="System safety policy.",
        input_items=[{"role": "user", "content": "Check A1"}],
        tools=[tool_schema],
        output_schema=output_schema,
        max_output_tokens=432,
        trusted_tenant_id="company-a",
    )

    result = await provider.generate(request)

    assert endpoint.calls == [
        {
            "model": "configured-model",
            "instructions": "System safety policy.",
            "input": request.input_items,
            "tools": [tool_schema],
            "max_output_tokens": 432,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "maintenance_diagnostic",
                    "schema": output_schema,
                    "strict": True,
                }
            },
            "store": False,
        }
    ]
    assert result.request_id == "response-123"
    assert result.output_items == [
        {
            "type": "function_call",
            "call_id": "call-123",
            "name": "get_machine_status",
            "arguments": '{"machine_id":"A1"}',
        }
    ]
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].call_id == "call-123"
    assert result.tool_calls[0].name == "get_machine_status"
    assert result.usage.input_tokens == 120
    assert result.usage.output_tokens == 30
    assert result.usage.cached_input_tokens == 20
    assert result.usage.cache_write_tokens == 5
    assert result.usage.estimated is False
