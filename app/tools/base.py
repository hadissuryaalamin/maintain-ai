"""Tool definition primitives."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from app.llm.base import ToolSpec


class TransientToolError(RuntimeError):
    """A tool error which may be retried within the configured small limit."""


# Concrete handlers deliberately accept their own Pydantic input subtype. The registry
# validates against ``input_model`` before dispatch and validates the returned output again.
# ``Any`` here avoids pretending every handler can accept every BaseModel subtype.
ToolHandler = Callable[[Any, str | None], BaseModel]


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    name: str
    description: str
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    handler: ToolHandler
    read_only: bool = True
    requires_approval: bool = False

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            parameters=_strict_provider_schema(self.input_model.model_json_schema()),
        )


def _strict_provider_schema(value: Any) -> Any:
    """Normalize Pydantic JSON Schema for strict native function calling.

    Strict provider schemas require every property name in ``required``. Nullable input
    fields remain nullable through Pydantic's ``anyOf`` representation; the model must send
    the field explicitly as ``null`` when it has no value.
    """

    if isinstance(value, dict):
        normalized = {key: _strict_provider_schema(item) for key, item in value.items()}
        properties = normalized.get("properties")
        if isinstance(properties, dict):
            normalized["required"] = list(properties)
            normalized["additionalProperties"] = False
        return normalized
    if isinstance(value, list):
        return [_strict_provider_schema(item) for item in value]
    return value
