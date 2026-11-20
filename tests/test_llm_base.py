"""Provider-neutral conversation items and tool specifications."""

from __future__ import annotations

import json

from app.llm.base import (
    AssistantMessage,
    ProviderToolCall,
    ToolCall,
    ToolResult,
    UserMessage,
    conversation_characters,
    conversation_to_jsonable,
)
from app.tools.registry import ToolRegistry


def test_conversation_to_jsonable_kinds() -> None:
    items = [
        UserMessage(text="Pump A2 noise"),
        ToolCall(call_id="c1", name="get_machine_status", arguments='{"machine_id":"A2"}'),
        ToolResult(call_id="c1", output='{"ok":true}'),
        AssistantMessage(text="{}"),
    ]
    assert conversation_to_jsonable(items) == [
        {"kind": "user_message", "text": "Pump A2 noise"},
        {
            "kind": "tool_call",
            "call_id": "c1",
            "name": "get_machine_status",
            "arguments": '{"machine_id":"A2"}',
        },
        {"kind": "tool_result", "call_id": "c1", "output": '{"ok":true}'},
        {"kind": "assistant_message", "text": "{}"},
    ]


def test_conversation_characters_counts_serialized_length() -> None:
    items = [UserMessage(text="héllo"), AssistantMessage(text="ok")]
    expected = len(json.dumps(conversation_to_jsonable(items), ensure_ascii=False))
    assert conversation_characters(items) == expected


def test_provider_tool_call_is_tool_call() -> None:
    assert ProviderToolCall is ToolCall


def test_tool_spec_matches_strict_schema(registry: ToolRegistry) -> None:
    specs = {spec.name: spec for spec in registry.tool_specs}
    assert specs
    for name, spec in specs.items():
        definition = registry.definition(name)
        assert definition is not None
        assert spec.description == definition.description
        assert spec.parameters == definition.provider_schema()["parameters"]
