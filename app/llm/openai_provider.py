"""Direct OpenAI Responses API adapter.

The orchestration remains application code: this adapter only translates the provider-neutral
conversation to the Responses API and back. It deliberately does not use an agent framework.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    RateLimitError,
)

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
    ToolSpec,
    UserMessage,
)


def to_responses_input(items: Sequence[ConversationItem]) -> list[dict[str, Any]]:
    converted: list[dict[str, Any]] = []
    for item in items:
        if isinstance(item, UserMessage):
            converted.append({"role": "user", "content": item.text})
        elif isinstance(item, AssistantMessage):
            converted.append({"role": "assistant", "content": item.text})
        elif isinstance(item, ToolCall):
            converted.append(
                {
                    "type": "function_call",
                    "call_id": item.call_id,
                    "name": item.name,
                    "arguments": item.arguments,
                }
            )
        else:  # ToolResult
            converted.append(
                {"type": "function_call_output", "call_id": item.call_id, "output": item.output}
            )
    return converted


def to_responses_tools(specs: Sequence[ToolSpec]) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "name": spec.name,
            "description": spec.description,
            "parameters": spec.parameters,
            "strict": True,
        }
        for spec in specs
    ]


class OpenAIResponsesProvider:
    name = "openai"

    def __init__(self, settings: Settings) -> None:
        secret = settings.openai_api_key
        if secret is None or not secret.get_secret_value():
            raise ValueError("OPENAI_API_KEY is required when LLM_PROVIDER=openai")
        client_args: dict[str, Any] = {
            "api_key": secret.get_secret_value(),
            "timeout": settings.request_timeout_seconds,
            "max_retries": 0,  # Retries are observable and bounded in the orchestration layer.
        }
        if settings.openai_base_url:
            client_args["base_url"] = settings.openai_base_url
        self.client = AsyncOpenAI(**client_args)

    async def generate(self, request: ProviderRequest) -> ProviderResponse:
        try:
            # The provider-neutral structures have already been schema-validated. Keep the
            # SDK's large version-specific parameter union contained at this adapter boundary.
            request_payload: Any = {
                "model": request.model,
                "instructions": request.instructions,
                "input": to_responses_input(request.conversation),
                "tools": to_responses_tools(request.tools),
                "max_output_tokens": request.max_output_tokens,
                "text": {
                    "format": {
                        "type": "json_schema",
                        "name": "maintenance_diagnostic",
                        "schema": request.output_schema,
                        "strict": True,
                    }
                },
                "store": False,
            }
            response = await self.client.responses.create(**request_payload)
        except APITimeoutError as exc:
            raise ProviderTimeoutError("model request timed out") from exc
        except (APIConnectionError, RateLimitError) as exc:
            raise ProviderTransientError("temporary model provider failure") from exc
        except APIStatusError as exc:
            if exc.status_code >= 500:
                raise ProviderTransientError("temporary model provider failure") from exc
            raise ProviderError("model provider rejected the request") from exc
        except Exception as exc:
            raise ProviderError("model provider request failed") from exc

        tool_calls = [
            ToolCall(call_id=item.call_id, name=item.name, arguments=item.arguments)
            for item in response.output
            if item.type == "function_call"
        ]
        output_text = response.output_text or ""
        items: list[ConversationItem] = list(tool_calls)
        if output_text and not tool_calls:
            items.append(AssistantMessage(text=output_text))
        usage = response.usage
        details = getattr(usage, "input_tokens_details", None) if usage else None
        return ProviderResponse(
            request_id=response.id,
            output_text=output_text,
            tool_calls=tool_calls,
            items=items,
            usage=ProviderUsage(
                input_tokens=getattr(usage, "input_tokens", None),
                output_tokens=getattr(usage, "output_tokens", None),
                cached_input_tokens=getattr(details, "cached_tokens", None),
                cache_write_tokens=getattr(details, "cache_write_tokens", None),
                estimated=False,
            ),
        )
