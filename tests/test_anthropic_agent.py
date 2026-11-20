"""End-to-end proof: the agent loop completes a diagnosis on a scripted Claude client."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.agent.orchestrator import MaintenanceAgent
from app.config import Settings
from app.llm.anthropic_provider import FINAL_TOOL, AnthropicMessagesProvider
from app.schemas.api import DiagnoseRequest
from app.schemas.common import RunStatus
from app.security.context import AuthContext
from app.telemetry.pricing import PricingCatalog
from app.telemetry.service import TelemetryService
from app.tools.registry import build_tool_registry


@dataclass
class _Block:
    type: str
    id: str
    name: str
    input: Any


@dataclass
class _Usage:
    input_tokens: int = 900
    output_tokens: int = 120
    cache_read_input_tokens: int | None = 0
    cache_creation_input_tokens: int | None = 0


@dataclass
class _Message:
    id: str
    content: list[_Block]
    usage: _Usage = field(default_factory=_Usage)


@dataclass
class _Messages:
    replies: list[_Message]
    calls: list[dict[str, Any]] = field(default_factory=list)

    async def create(self, **kwargs: Any) -> _Message:
        self.calls.append(kwargs)
        return self.replies.pop(0)


@dataclass
class _Client:
    messages: _Messages


FINAL_DIAGNOSTIC = {
    "incident_summary": "A2 reports VIB-HI; inspect inlet conditions before drawing conclusions.",
    "observations": [
        {
            "statement": "Machine A2 is running with alarm VIB-HI.",
            "source_type": "tool",
            "source_reference": "tool:get_machine_status:A2",
        }
    ],
    "possible_causes": [
        {
            "cause": "Restricted inlet flow",
            "confidence": "medium",
            "reasoning_summary": "The status lookup shows VIB-HI on a centrifugal pump.",
        }
    ],
    "recommended_actions": [
        {
            "step": 1,
            "action": "Apply site lockout/tagout before any invasive inspection.",
            "requires_shutdown": True,
            "requires_approval": False,
        }
    ],
    "missing_information": [],
    "safety_notice": "Decision support only; a qualified person must follow site procedure.",
}


@pytest.mark.asyncio
async def test_orchestrator_completes_with_scripted_claude(
    session: Session, context_a: AuthContext, settings: Settings
) -> None:
    messages = _Messages(
        [
            _Message(
                id="msg-1",
                content=[
                    _Block(
                        type="tool_use",
                        id="toolu-1",
                        name="get_machine_status",
                        input={"machine_id": "A2"},
                    )
                ],
            ),
            _Message(
                id="msg-2",
                content=[
                    _Block(type="tool_use", id="toolu-2", name=FINAL_TOOL, input=FINAL_DIAGNOSTIC)
                ],
            ),
        ]
    )
    claude_settings = settings.model_copy(
        update={"llm_provider": "anthropic", "default_model": "claude-sonnet-5-5"}
    )
    provider = AnthropicMessagesProvider(claude_settings, client=_Client(messages))
    agent = MaintenanceAgent(
        session=session,
        context=context_a,
        settings=claude_settings,
        provider=provider,
        registry=build_tool_registry(session, context_a, claude_settings),
        telemetry=TelemetryService(
            session, context_a, claude_settings, pricing=PricingCatalog(None)
        ),
    )

    result = await agent.diagnose(
        DiagnoseRequest(message="Pump A2 grinding noise with VIB-HI. What should I check first?")
    )

    assert result.status == RunStatus.COMPLETED, result.error
    assert [item.tool_name for item in result.tool_trace] == ["get_machine_status"]
    assert result.usage.provider == "anthropic"
    assert result.diagnostic is not None
    # Claude's answer went through the same grounding policy as every provider: the cited
    # status observation survives because the tool really ran in this run.
    references = {item.source_reference for item in result.diagnostic.observations}
    assert "tool:get_machine_status:A2" in references
    assert result.diagnostic.safety_notice

    second = messages.calls[1]["messages"]
    assert second[1]["content"][0]["type"] == "tool_use"
    tool_result = second[2]["content"][0]
    assert tool_result["type"] == "tool_result"
    assert tool_result["tool_use_id"] == "toolu-1"
    assert "untrusted_tool_result" in tool_result["content"]
    assert all("company-a" not in str(call) for call in messages.calls)
