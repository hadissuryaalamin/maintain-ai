"""Direct Anthropic Messages API (Claude) adapter.

Translates the provider-neutral conversation to Claude's ``messages`` / ``tool_use`` /
``tool_result`` shape and back. Claude returns the final ``DiagnosticResult`` through a
``submit_diagnostic`` tool whose input schema is the output schema. Tool choice stays "auto"
because current Claude models reject forced tool choice; the system prompt states the protocol.
The adapter turns that call into ``output_text`` so the agent loop validates it exactly like any
other provider's answer.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

import anthropic

from app.config import Settings
from app.llm.base import (
    AssistantMessage,
    ConversationItem,
    ProviderError,
    ProviderRequest,
    ProviderResponse,
    ProviderTimeoutError,
    ProviderTransientError,
    ProviderUsage,
    ToolCall,
    ToolResult,
    ToolSpec,
    UserMessage,
)

FINAL_TOOL = "submit_diagnostic"
# Current Claude models reject forced tool choice, so the adapter states the protocol in the
# system prompt and lets the model choose ("auto"). A reply without the final-answer tool has no
# output_text and fails the loop's normal invalid-output check; nothing is guessed from prose.
_FINAL_TOOL_INSTRUCTION = (
    "\n\nResponse protocol: use the available tools to gather evidence. When you are ready to "
    f"answer, call the `{FINAL_TOOL}` tool exactly once with the complete diagnostic as its "
    "input. Never write the final answer as plain text."
)
_FINAL_TOOL_DESCRIPTION = (
    "Submit the final maintenance diagnostic. Call this exactly once, only after gathering "
    "the evidence you need with the other tools. Its input is the complete answer."
)


def to_anthropic_tools(
    specs: Sequence[ToolSpec], output_schema: dict[str, Any]
) -> list[dict[str, Any]]:
    tools = [
        {"name": spec.name, "description": spec.description, "input_schema": spec.parameters}
        for spec in specs
    ]
    tools.append(
        {"name": FINAL_TOOL, "description": _FINAL_TOOL_DESCRIPTION, "input_schema": output_schema}
    )
    return tools


def _tool_input(arguments: str) -> Any:
    try:
        return json.loads(arguments)
    except json.JSONDecodeError:
        # Replaying a malformed call verbatim keeps the transcript honest; the loop already
        # answered it with an invalid-arguments tool result.
        return {"_unparsed_arguments": arguments}


def _block(item: ConversationItem) -> tuple[str, dict[str, Any]]:
    if isinstance(item, UserMessage):
        return "user", {"type": "text", "text": item.text}
    if isinstance(item, AssistantMessage):
        return "assistant", {"type": "text", "text": item.text}
    if isinstance(item, ToolCall):
        return "assistant", {
            "type": "tool_use",
            "id": item.call_id,
            "name": item.name,
            "input": _tool_input(item.arguments),
        }
    if isinstance(item, ToolResult):
        return "user", {"type": "tool_result", "tool_use_id": item.call_id, "content": item.output}
    raise TypeError(f"Unsupported conversation item: {type(item).__name__}")


def to_anthropic_messages(items: Sequence[ConversationItem]) -> list[dict[str, Any]]:
    """Group items into strictly alternating user/assistant messages starting with user."""

    messages: list[dict[str, Any]] = []
    for item in items:
        role, block = _block(item)
        if messages and messages[-1]["role"] == role:
            messages[-1]["content"].append(block)
        else:
            messages.append({"role": role, "content": [block]})
    if messages and messages[0]["role"] != "user":
        # Claude requires the first turn to come from the user (e.g. a context-omission notice).
        messages.insert(
            0, {"role": "user", "content": [{"type": "text", "text": "[Conversation context]"}]}
        )
    return messages


class AnthropicMessagesProvider:
    name = "anthropic"

    def __init__(self, settings: Settings, client: Any | None = None) -> None:
        if client is not None:
            self.client = client
            return
        secret = settings.anthropic_api_key
        if secret is None or not secret.get_secret_value():
            raise ValueError("ANTHROPIC_API_KEY is required when LLM_PROVIDER=anthropic")
        client_args: dict[str, Any] = {
            "api_key": secret.get_secret_value(),
            "timeout": settings.request_timeout_seconds,
            "max_retries": 0,  # Retries are observable and bounded in the orchestration layer.
        }
        if settings.anthropic_base_url:
            client_args["base_url"] = settings.anthropic_base_url
        self.client = anthropic.AsyncAnthropic(**client_args)

    async def generate(self, request: ProviderRequest) -> ProviderResponse:
        try:
            response = await self.client.messages.create(
                model=request.model,
                system=request.instructions + _FINAL_TOOL_INSTRUCTION,
                messages=to_anthropic_messages(request.conversation),
                tools=to_anthropic_tools(request.tools, request.output_schema),
                tool_choice={"type": "auto"},
                max_tokens=request.max_output_tokens,
            )
        except anthropic.APITimeoutError as exc:
            raise ProviderTimeoutError("model request timed out") from exc
        except (anthropic.APIConnectionError, anthropic.RateLimitError) as exc:
            raise ProviderTransientError("temporary model provider failure") from exc
        except anthropic.APIStatusError as exc:
            raise _status_error(exc) from exc
        except Exception as exc:
            raise ProviderError("model provider request failed") from exc

        if getattr(response, "stop_reason", None) == "max_tokens":
            # A cut-off reply carries partial tool input; never pass it on as an answer.
            raise ProviderError(
                "model output was cut off by the output token limit; raise MAX_OUTPUT_TOKENS"
            )

        tool_calls: list[ToolCall] = []
        final_input: Any = None
        has_final = False
        for block in response.content:
            if getattr(block, "type", None) != "tool_use":
                continue
            if block.name == FINAL_TOOL:
                has_final, final_input = True, block.input
            else:
                tool_calls.append(
                    ToolCall(call_id=block.id, name=block.name, arguments=json.dumps(block.input))
                )

        items: list[ConversationItem]
        if tool_calls:
            # Evidence first: a final answer offered alongside new tool calls is dropped and the
            # loop asks again once the tool results are in.
            output_text = ""
            items = list(tool_calls)
        elif has_final:
            output_text = json.dumps(final_input)
            items = [AssistantMessage(text=output_text)]
        else:
            output_text = ""
            items = []

        usage = response.usage
        return ProviderResponse(
            request_id=response.id,
            output_text=output_text,
            tool_calls=tool_calls,
            items=items,
            usage=ProviderUsage(
                input_tokens=getattr(usage, "input_tokens", None),
                output_tokens=getattr(usage, "output_tokens", None),
                cached_input_tokens=getattr(usage, "cache_read_input_tokens", None),
                cache_write_tokens=getattr(usage, "cache_creation_input_tokens", None),
                estimated=False,
            ),
        )


def _status_error(exc: anthropic.APIStatusError) -> ProviderError:
    status = exc.status_code
    if status >= 500:  # includes 529 "overloaded"
        return ProviderTransientError("temporary model provider failure")
    detail = str(exc).lower()
    if "credit balance" in detail or "billing" in detail:
        return ProviderError("model provider rejected the request: insufficient credit")
    if status in (401, 403):
        return ProviderError("model provider rejected the request: authentication failed")
    if status == 404:
        # Usually a model name from another vendor after switching LLM_PROVIDER.
        return ProviderError(
            "model provider rejected the request: model not found; "
            "check DEFAULT_MODEL and SMALL_MODEL"
        )
    return ProviderError("model provider rejected the request")
