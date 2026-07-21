"""Bounded orchestration, provider resilience, deduplication, and grounding tests."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.orchestrator import MaintenanceAgent
from app.config import Settings
from app.db.models import AgentRun, ApprovalRequest, ModelUsage, SecurityEvent, WorkOrder
from app.llm.base import (
    ProviderError,
    ProviderRequest,
    ProviderResponse,
    ProviderToolCall,
    ProviderTransientError,
    ProviderUsage,
)
from app.schemas.api import ConversationMessage, DiagnoseRequest
from app.schemas.common import ErrorCategory, RunStatus, ToolStatus
from app.schemas.tools import ToolError, ToolExecutionResult
from app.security.context import AuthContext
from app.telemetry.pricing import PricingCatalog
from app.telemetry.service import TelemetryService
from app.tools.registry import ToolInvocation, build_tool_registry


def _response(
    request_id: str,
    *,
    tool_calls: list[ProviderToolCall] | None = None,
    diagnostic: dict[str, Any] | None = None,
    input_tokens: int = 40,
    output_tokens: int = 10,
    metadata: dict[str, Any] | None = None,
) -> ProviderResponse:
    calls = tool_calls or []
    output_items: list[dict[str, Any]]
    if calls:
        output_items = [
            {
                "type": "function_call",
                "call_id": call.call_id,
                "name": call.name,
                "arguments": call.arguments,
            }
            for call in calls
        ]
        output_text = ""
    else:
        output_text = json.dumps(diagnostic) if diagnostic is not None else ""
        output_items = (
            [
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": output_text}],
                }
            ]
            if output_text
            else []
        )
    return ProviderResponse(
        request_id=request_id,
        output_text=output_text,
        tool_calls=calls,
        output_items=output_items,
        usage=ProviderUsage(input_tokens=input_tokens, output_tokens=output_tokens),
        metadata=metadata or {},
    )


def _diagnostic(
    *,
    observations: list[dict[str, Any]] | None = None,
    confidence: str = "medium",
) -> dict[str, Any]:
    return {
        "incident_summary": "A bounded preliminary diagnostic.",
        "observations": observations or [],
        "possible_causes": [
            {
                "cause": "Mechanical load or alignment condition",
                "confidence": confidence,
                "reasoning_summary": "The available evidence warrants an on-site inspection.",
            }
        ],
        "recommended_actions": [
            {
                "step": 1,
                "action": "Apply site lockout/tagout before an invasive inspection.",
                "requires_shutdown": True,
                "requires_approval": False,
            }
        ],
        "missing_information": [],
        "safety_notice": "Decision support only; a qualified person must follow site procedure.",
    }


@dataclass
class ScriptedProvider:
    events: list[ProviderResponse | ProviderError]
    name: str = "fake"
    requests: list[ProviderRequest] = field(default_factory=list)

    async def generate(self, request: ProviderRequest) -> ProviderResponse:
        self.requests.append(request)
        if not self.events:
            raise AssertionError("provider script exhausted")
        event = self.events.pop(0)
        if isinstance(event, ProviderError):
            raise event
        return event


@dataclass
class RepeatingToolProvider:
    name: str = "fake"
    requests: list[ProviderRequest] = field(default_factory=list)

    async def generate(self, request: ProviderRequest) -> ProviderResponse:
        self.requests.append(request)
        index = len(self.requests)
        return _response(
            f"repeat-{index}",
            tool_calls=[
                ProviderToolCall(
                    call_id=f"call-{index}",
                    name="get_machine_status",
                    arguments=json.dumps({"machine_id": "A1"}),
                )
            ],
        )


@dataclass
class BlockingProvider:
    started: asyncio.Event = field(default_factory=asyncio.Event)
    name: str = "fake"

    async def generate(self, _: ProviderRequest) -> ProviderResponse:
        self.started.set()
        await asyncio.Event().wait()
        raise AssertionError("unreachable")


def _agent(
    *,
    session: Session,
    context: AuthContext,
    settings: Settings,
    provider: Any,
) -> MaintenanceAgent:
    registry = build_tool_registry(session, context, settings)
    telemetry = TelemetryService(
        session,
        context,
        settings,
        pricing=PricingCatalog(None),
    )
    return MaintenanceAgent(
        session=session,
        context=context,
        settings=settings,
        provider=provider,
        registry=registry,
        telemetry=telemetry,
    )


def _single_run(session: Session) -> AgentRun:
    runs = list(session.scalars(select(AgentRun)))
    assert len(runs) == 1
    return runs[0]


@pytest.mark.asyncio
async def test_agent_executes_native_calls_deduplicates_and_enforces_grounding(
    session: Session, context_a: AuthContext, settings: Settings
) -> None:
    calls = [
        ProviderToolCall(
            call_id="machine-1",
            name="get_machine_status",
            arguments='{"machine_id":"A1"}',
        ),
        ProviderToolCall(
            call_id="machine-duplicate",
            name="get_machine_status",
            arguments='{ "machine_id": "A1" }',
        ),
    ]
    observations = [
        {
            "statement": "The stored machine state is stopped with E217.",
            "source_type": "tool",
            "source_reference": "tool:get_machine_status:A1",
        },
        {
            "statement": "A fabricated manual claim.",
            "source_type": "manual",
            "source_reference": "manual:not-retrieved",
        },
        {
            "statement": "The user reported an overload after changeover.",
            "source_type": "user",
            "source_reference": "user:current-message",
        },
    ]
    provider = ScriptedProvider(
        [
            _response("req-tools", tool_calls=calls),
            _response("req-final", diagnostic=_diagnostic(observations=observations)),
        ]
    )
    agent_settings = settings.model_copy(update={"max_output_tokens": 777})

    result = await _agent(
        session=session,
        context=context_a,
        settings=agent_settings,
        provider=provider,
    ).diagnose(DiagnoseRequest(message="A1 stopped with E217 after changeover"))

    assert result.status == RunStatus.COMPLETED
    assert result.diagnostic is not None
    assert [item.source_reference for item in result.diagnostic.observations] == [
        "user:current-message",
        "tool:get_machine_status:A1",
    ]
    assert result.diagnostic.observations[0].statement == (
        "The current incident description was supplied by the user."
    )
    assert "Machine 'A1'" in result.diagnostic.observations[1].statement
    assert "status 'stopped'" in result.diagnostic.observations[1].statement
    assert "fabricated" not in result.diagnostic.model_dump_json().lower()
    assert result.diagnostic.missing_information == [
        ("3 provider-authored observation(s) were replaced with application-grounded evidence."),
        (
            "1 model-authored cause hypothesis(es) were replaced with low-confidence, "
            "evidence-bounded hypotheses."
        ),
        (
            "1 model-authored recommended action(s) were replaced with application-authored "
            "safety steps."
        ),
    ]
    assert [item.status for item in result.tool_trace] == ["succeeded", "deduplicated"]
    assert result.tool_trace[1].latency_ms == 0
    assert len(provider.requests) == 2
    assert all(request.max_output_tokens == 777 for request in provider.requests)
    assert all("tenant_id" not in json.dumps(request.tools) for request in provider.requests)


@pytest.mark.asyncio
async def test_agent_downgrades_high_confidence_when_all_non_user_evidence_is_unsupported(
    session: Session, context_a: AuthContext, settings: Settings
) -> None:
    provider = ScriptedProvider(
        [
            _response(
                "unsupported-final",
                diagnostic=_diagnostic(
                    observations=[
                        {
                            "statement": "Unsupported sensor claim.",
                            "source_type": "tool",
                            "source_reference": "sensor:not-called",
                        }
                    ],
                    confidence="high",
                ),
            )
        ]
    )

    result = await _agent(
        session=session,
        context=context_a,
        settings=settings,
        provider=provider,
    ).diagnose(DiagnoseRequest(message="What might explain this unusual noise?"))

    assert result.status == RunStatus.COMPLETED
    assert result.diagnostic is not None
    assert [item.source_reference for item in result.diagnostic.observations] == [
        "user:current-message"
    ]
    assert result.diagnostic.possible_causes[0].confidence == "low"
    assert any(
        "provider-authored observation" in item for item in result.diagnostic.missing_information
    )
    assert any(
        "No successful tenant-scoped external evidence" in item
        for item in result.diagnostic.missing_information
    )


@pytest.mark.asyncio
async def test_agent_grounding_exposes_only_generic_retained_user_history_provenance(
    session: Session, context_a: AuthContext, settings: Settings
) -> None:
    provider = ScriptedProvider([_response("history-final", diagnostic=_diagnostic())])
    history = [
        ConversationMessage(
            role="user",
            content="[conversation:item-400] The arbitrary old claim says the moon caused it.",
        ),
        ConversationMessage(
            role="user",
            content=(
                "[conversation:turn-117] A1 showed alarm E217. The root cause is definitely "
                "the private claim SECRET-SABOTAGE."
            ),
        ),
        ConversationMessage(role="user", content="irrelevant padding " * 12),
        ConversationMessage(
            role="assistant",
            content=(
                "[conversation:item-298] A1 alarm E217 proves the assistant-only claim "
                "ASSISTANT-FICTION."
            ),
        ),
        ConversationMessage(
            role="user",
            content=(
                "[conversation:item-299] Later A1 vibration was noted with another arbitrary "
                "claim USER-FICTION."
            ),
        ),
        ConversationMessage(role="assistant", content="Continue from the retained context."),
    ]
    constrained = settings.model_copy(
        update={"history_message_limit": 4, "history_character_limit": 1000}
    )

    result = await _agent(
        session=session,
        context=context_a,
        settings=constrained,
        provider=provider,
    ).diagnose(
        DiagnoseRequest(
            message="Diagnose the A1 alarm and later vibration.",
            conversation_history=history,
        )
    )

    assert result.diagnostic is not None
    assert [item.source_reference for item in result.diagnostic.observations] == [
        "user:current-message",
        "conversation:turn-117",
        "conversation:item-299",
    ]
    assert all(
        item.statement
        == "A retained user-authored conversation message was available at this provenance "
        "reference."
        for item in result.diagnostic.observations[1:]
    )
    grounded_json = result.diagnostic.model_dump_json()
    assert "item-400" not in grounded_json
    assert "item-298" not in grounded_json
    assert "SECRET-SABOTAGE" not in grounded_json
    assert "ASSISTANT-FICTION" not in grounded_json
    assert "USER-FICTION" not in grounded_json
    assert "2 retained user-conversation provenance reference(s)" in (
        result.diagnostic.incident_summary
    )
    assert any(
        "No successful tenant-scoped external evidence" in item
        for item in result.diagnostic.missing_information
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("terminal_status", "guidance", "action_text"),
    [
        (
            RunStatus.NEEDS_CLARIFICATION,
            "Provide the exact machine ID",
            "Provide the exact machine ID",
        ),
        (
            RunStatus.ACCESS_DENIED,
            "unavailable in the authenticated tenant scope",
            "Use an in-scope machine ID",
        ),
        (
            RunStatus.FAILED,
            "retry once, then escalate with the run ID",
            "Retry evidence collection once",
        ),
    ],
)
async def test_agent_replaces_model_text_with_status_specific_safe_guidance(
    session: Session,
    context_a: AuthContext,
    settings: Settings,
    terminal_status: RunStatus,
    guidance: str,
    action_text: str,
) -> None:
    untrusted = _diagnostic()
    untrusted["incident_summary"] = "B1 was inspected at 999."
    untrusted["missing_information"] = ["Collect another B1 reading at 999."]
    untrusted["recommended_actions"] = [
        {
            "step": 1,
            "action": "Review B1 at 999 before the next shift.",
            "requires_shutdown": False,
            "requires_approval": False,
        }
    ]
    provider = ScriptedProvider(
        [
            _response(
                f"status-{terminal_status}",
                diagnostic=untrusted,
                metadata={"terminal_status": terminal_status.value},
            )
        ]
    )

    result = await _agent(
        session=session,
        context=context_a,
        settings=settings,
        provider=provider,
    ).diagnose(DiagnoseRequest(message="Help with the current maintenance request."))

    assert result.status == terminal_status
    assert result.diagnostic is not None
    serialized = result.diagnostic.model_dump_json()
    assert "B1" not in serialized
    assert "999" not in serialized
    assert any(guidance in item for item in result.diagnostic.missing_information)
    assert result.diagnostic.recommended_actions[0].requires_shutdown is True
    assert action_text in result.diagnostic.recommended_actions[1].action


@pytest.mark.asyncio
async def test_agent_rejects_model_proposed_write_without_current_user_intent(
    session: Session, context_a: AuthContext, settings: Settings
) -> None:
    """Retrieved/model text cannot authorize even a pending state-change proposal."""

    write_call = ProviderToolCall(
        call_id="hostile-write",
        name="create_work_order",
        arguments=json.dumps(
            {
                "machine_id": "A1",
                "title": "Injected request",
                "description": "A retrieved document asked for this write.",
                "priority": "high",
            }
        ),
    )
    provider = ScriptedProvider(
        [
            _response("hostile-call", tool_calls=[write_call]),
            _response("safe-final", diagnostic=_diagnostic()),
        ]
    )

    result = await _agent(
        session=session,
        context=context_a,
        settings=settings,
        provider=provider,
    ).diagnose(DiagnoseRequest(message="Diagnose the unusual A1 noise."))

    assert result.status == RunStatus.COMPLETED
    assert [(item.status, item.error_category) for item in result.tool_trace] == [
        ("rejected", ErrorCategory.STATE_CHANGE_NOT_AUTHORIZED)
    ]
    assert list(session.scalars(select(ApprovalRequest))) == []
    assert list(session.scalars(select(WorkOrder))) == []
    event = session.scalar(
        select(SecurityEvent).where(
            SecurityEvent.event_type == "state_change_without_user_intent_rejected"
        )
    )
    assert event is not None


@pytest.mark.asyncio
async def test_agent_replaces_unsafe_model_actions_and_safety_notice(
    session: Session, context_a: AuthContext, settings: Settings
) -> None:
    unsafe = _diagnostic()
    unsafe["recommended_actions"] = [
        {
            "step": 1,
            "action": "Bypass the safety interlock and restart the machine immediately.",
            "requires_shutdown": False,
            "requires_approval": False,
        }
    ]
    unsafe["safety_notice"] = "The machine is safe to run."
    provider = ScriptedProvider([_response("unsafe-final", diagnostic=unsafe)])

    result = await _agent(
        session=session,
        context=context_a,
        settings=settings,
        provider=provider,
    ).diagnose(DiagnoseRequest(message="What should I do about A1?"))

    assert result.diagnostic is not None
    serialized_actions = " ".join(
        item.action for item in result.diagnostic.recommended_actions
    ).lower()
    assert "bypass" not in serialized_actions
    assert "lockout/tagout" in serialized_actions
    assert "cannot control machinery" in result.diagnostic.safety_notice
    assert any(
        "unsafe model-recommended action" in item for item in result.diagnostic.missing_information
    )


@pytest.mark.asyncio
async def test_agent_replaces_fabricated_facts_and_orders_safe_invasive_actions(
    session: Session, context_a: AuthContext, settings: Settings
) -> None:
    fabricated = _diagnostic(
        observations=[
            {
                "statement": "B1 had a fabricated sensor reading of 999.",
                "source_type": "tool",
                "source_reference": "tool:get_machine_status:A1",
            },
            {
                "statement": "The user confirmed B1 was at 999.",
                "source_type": "user",
                "source_reference": "user:current-message",
            },
        ],
        confidence="high",
    )
    fabricated["incident_summary"] = "I inspected B1 and confirmed a reading of 999."
    fabricated["possible_causes"] = [
        {
            "cause": "Electrical anomaly",
            "confidence": "high",
            "reasoning_summary": "B1 was inspected and its live reading was 999.",
        }
    ]
    fabricated["missing_information"] = ["B1 still needs a second 999 reading."]
    fabricated["recommended_actions"] = [
        {
            "step": 1,
            "action": "Open the electrical cabinet and check live terminals on B1 at 999 volts.",
            "requires_shutdown": False,
            "requires_approval": False,
        },
        {
            "step": 2,
            "action": "Apply site lockout/tagout before invasive inspection.",
            "requires_shutdown": True,
            "requires_approval": False,
        },
        {
            "step": 3,
            "action": "Remove the de-energized guard for a visual inspection.",
            "requires_shutdown": False,
            "requires_approval": False,
        },
        {
            "step": 4,
            "action": "Restart the machine to confirm the fault.",
            "requires_shutdown": False,
            "requires_approval": False,
        },
    ]
    provider = ScriptedProvider(
        [
            _response(
                "grounded-tool",
                tool_calls=[
                    ProviderToolCall(
                        call_id="machine-a1",
                        name="get_machine_status",
                        arguments='{"machine_id":"A1"}',
                    )
                ],
            ),
            _response("fabricated-final", diagnostic=fabricated),
        ]
    )

    result = await _agent(
        session=session,
        context=context_a,
        settings=settings,
        provider=provider,
    ).diagnose(DiagnoseRequest(message="Diagnose the stopped A1 press."))

    assert result.diagnostic is not None
    serialized = result.diagnostic.model_dump_json()
    assert "B1" not in serialized
    assert "999" not in serialized
    assert [item.source_reference for item in result.diagnostic.observations] == [
        "user:current-message",
        "tool:get_machine_status:A1",
    ]
    assert "Machine 'A1'" in result.diagnostic.observations[1].statement
    assert all(cause.confidence == "low" for cause in result.diagnostic.possible_causes)
    assert all(
        cause.cause.startswith("Unconfirmed hypothesis:")
        for cause in result.diagnostic.possible_causes
    )
    assert result.diagnostic.recommended_actions[0].action == (
        "Follow site lockout/tagout and verify a zero-energy state before opening guards or "
        "beginning invasive inspection."
    )
    assert result.diagnostic.recommended_actions[0].requires_shutdown is True
    assert len(result.diagnostic.recommended_actions) == 4
    assert "grounded machine-state" in result.diagnostic.recommended_actions[1].action
    invasive = result.diagnostic.recommended_actions[2]
    assert invasive.action.startswith("Have a qualified person inspect the de-energized motor")
    assert invasive.requires_shutdown is True
    work_order = result.diagnostic.recommended_actions[3]
    assert "No work order is created without a separate explicit confirmation" in work_order.action
    assert work_order.requires_approval is True
    assert [item.step for item in result.diagnostic.recommended_actions] == [1, 2, 3, 4]
    assert any(
        "2 unsafe model-recommended action(s)" in item
        for item in result.diagnostic.missing_information
    )


@pytest.mark.asyncio
async def test_agent_stops_at_maximum_steps_with_clear_error(
    session: Session, context_a: AuthContext, settings: Settings
) -> None:
    provider = RepeatingToolProvider()
    bounded = settings.model_copy(update={"max_agent_steps": 2, "max_tool_calls": 5})

    result = await _agent(
        session=session,
        context=context_a,
        settings=bounded,
        provider=provider,
    ).diagnose(DiagnoseRequest(message="Diagnose A1 overload"))

    assert result.status == RunStatus.FAILED
    assert result.error == "Maximum agent steps (2) reached."
    assert [item.status for item in result.tool_trace] == ["succeeded", "deduplicated"]
    assert result.usage.model_requests == 2
    run = _single_run(session)
    assert run.error_category == ErrorCategory.LIMIT_REACHED


@pytest.mark.asyncio
async def test_agent_rejects_request_that_exceeds_input_budget_before_provider_call(
    session: Session, context_a: AuthContext, settings: Settings
) -> None:
    provider = ScriptedProvider([])
    bounded = settings.model_copy(update={"max_request_input_characters": 1000})

    result = await _agent(
        session=session,
        context=context_a,
        settings=bounded,
        provider=provider,
    ).diagnose(
        DiagnoseRequest(
            message="Check A1",
            conversation_history=[ConversationMessage(role="user", content="x" * 1000)],
        )
    )

    assert result.status == RunStatus.FAILED
    assert result.error == "Request input exceeds the configured character budget (1000)."
    assert provider.requests == []


@pytest.mark.asyncio
async def test_agent_rejects_oversized_provider_envelope_before_paid_call(
    session: Session, context_a: AuthContext, settings: Settings
) -> None:
    provider = ScriptedProvider([])
    bounded = settings.model_copy(update={"max_provider_input_characters": 1000})

    result = await _agent(
        session=session,
        context=context_a,
        settings=bounded,
        provider=provider,
    ).diagnose(DiagnoseRequest(message="Check A1"))

    assert result.status == RunStatus.FAILED
    assert result.error == "Provider input exceeds the configured character budget (1000)."
    assert provider.requests == []


@pytest.mark.asyncio
async def test_agent_rejects_a_batch_that_would_exceed_tool_call_limit(
    session: Session, context_a: AuthContext, settings: Settings
) -> None:
    provider = ScriptedProvider(
        [
            _response(
                "too-many-tools",
                tool_calls=[
                    ProviderToolCall("call-1", "get_machine_status", '{"machine_id":"A1"}'),
                    ProviderToolCall("call-2", "get_machine_status", '{"machine_id":"A2"}'),
                ],
            )
        ]
    )
    bounded = settings.model_copy(update={"max_tool_calls": 1})

    result = await _agent(
        session=session,
        context=context_a,
        settings=bounded,
        provider=provider,
    ).diagnose(DiagnoseRequest(message="Compare A1 and A2"))

    assert result.status == RunStatus.FAILED
    assert result.error == "Maximum tool calls (1) reached."
    assert result.tool_trace == []
    assert _single_run(session).error_category == ErrorCategory.LIMIT_REACHED


@pytest.mark.asyncio
async def test_agent_retries_transient_provider_errors_and_records_each_attempt(
    session: Session,
    context_a: AuthContext,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    delays: list[float] = []

    async def fake_sleep(delay: float) -> None:
        delays.append(delay)

    monkeypatch.setattr("app.agent.orchestrator.asyncio.sleep", fake_sleep)
    provider = ScriptedProvider(
        [
            ProviderTransientError("temporary one"),
            ProviderTransientError("temporary two"),
            _response("recovered", diagnostic=_diagnostic()),
        ]
    )
    retrying = settings.model_copy(update={"provider_max_retries": 2})

    result = await _agent(
        session=session,
        context=context_a,
        settings=retrying,
        provider=provider,
    ).diagnose(DiagnoseRequest(message="Review a minor unusual noise"))

    assert result.status == RunStatus.COMPLETED
    assert len(provider.requests) == 3
    assert delays == [0.1, 0.2]
    events = list(session.scalars(select(ModelUsage).order_by(ModelUsage.created_at)))
    assert [event.status for event in events] == ["failed", "failed", "succeeded"]
    assert [event.error_category for event in events[:2]] == [
        "transient_provider",
        "transient_provider",
    ]
    assert result.usage.model_requests == 3
    assert result.usage.input_tokens is None


@pytest.mark.asyncio
async def test_agent_does_not_retry_non_transient_provider_error(
    session: Session, context_a: AuthContext, settings: Settings
) -> None:
    provider = ScriptedProvider([ProviderError("provider rejected request")])
    retrying = settings.model_copy(update={"provider_max_retries": 3})

    result = await _agent(
        session=session,
        context=context_a,
        settings=retrying,
        provider=provider,
    ).diagnose(DiagnoseRequest(message="Review this maintenance note"))

    assert result.status == RunStatus.FAILED
    assert result.error == "provider rejected request"
    assert len(provider.requests) == 1
    assert _single_run(session).error_category == ErrorCategory.PROVIDER_ERROR


@pytest.mark.asyncio
async def test_agent_times_out_provider_request_without_live_network(
    session: Session, context_a: AuthContext, settings: Settings
) -> None:
    provider = BlockingProvider()
    timeout_settings = settings.model_copy(
        update={"request_timeout_seconds": 0.01, "provider_max_retries": 0}
    )

    result = await _agent(
        session=session,
        context=context_a,
        settings=timeout_settings,
        provider=provider,
    ).diagnose(DiagnoseRequest(message="Review this maintenance note"))

    assert result.status == RunStatus.FAILED
    assert result.error == "model request timed out"
    assert _single_run(session).error_category == ErrorCategory.TIMEOUT
    event = session.scalar(select(ModelUsage))
    assert event is not None
    assert event.status == "failed"
    assert event.error_category == ErrorCategory.TIMEOUT


@pytest.mark.asyncio
async def test_agent_safely_returns_invalid_tool_name_and_arguments_to_model(
    session: Session, context_a: AuthContext, settings: Settings
) -> None:
    provider = ScriptedProvider(
        [
            _response(
                "bad-tools",
                tool_calls=[
                    ProviderToolCall("bad-name", "delete_database", "{}"),
                    ProviderToolCall("bad-json", "get_machine_status", "[not-an-object]"),
                ],
            ),
            _response("safe-final", diagnostic=_diagnostic()),
        ]
    )

    result = await _agent(
        session=session,
        context=context_a,
        settings=settings,
        provider=provider,
    ).diagnose(DiagnoseRequest(message="Please diagnose A1"))

    assert result.status == RunStatus.COMPLETED
    assert [(item.tool_name, item.status, item.error_category) for item in result.tool_trace] == [
        ("delete_database", "rejected", "invalid_tool"),
        ("get_machine_status", "rejected", "invalid_arguments"),
    ]
    final_request_items: Sequence[dict[str, Any]] = provider.requests[-1].input_items
    tool_outputs = [
        item for item in final_request_items if item.get("type") == "function_call_output"
    ]
    assert len(tool_outputs) == 2
    assert all("Traceback" not in item["output"] for item in tool_outputs)


@pytest.mark.asyncio
async def test_agent_discloses_current_message_alarm_mismatch_from_validated_status(
    session: Session, context_a: AuthContext, settings: Settings
) -> None:
    provider = ScriptedProvider(
        [
            _response(
                "status-call",
                tool_calls=[
                    ProviderToolCall(
                        "status-a1",
                        "get_machine_status",
                        '{"machine_id":"A1"}',
                    )
                ],
            ),
            _response("status-final", diagnostic=_diagnostic()),
        ]
    )

    result = await _agent(
        session=session,
        context=context_a,
        settings=settings,
        provider=provider,
    ).diagnose(DiagnoseRequest(message="A1 shows alarm E127; confirm the overload."))

    assert result.diagnostic is not None
    mismatch = next(
        item for item in result.diagnostic.missing_information if item.startswith("Alarm mismatch:")
    )
    assert "current message reports code 'E127'" in mismatch
    assert "machine status reports code 'E217'" in mismatch
    assert "unconfirmed" in mismatch


@pytest.mark.asyncio
async def test_agent_marks_successful_empty_sensor_history_unavailable(
    session: Session, context_a: AuthContext, settings: Settings
) -> None:
    provider = ScriptedProvider(
        [
            _response(
                "sensor-call",
                tool_calls=[
                    ProviderToolCall(
                        "sensor-a1",
                        "get_sensor_history",
                        json.dumps(
                            {
                                "machine_id": "A1",
                                "metric": "servo_motor_current_rms",
                                "start_time": "2040-01-01T00:00:00Z",
                                "end_time": "2040-01-01T01:00:00Z",
                            }
                        ),
                    )
                ],
            ),
            _response("sensor-final", diagnostic=_diagnostic()),
        ]
    )

    result = await _agent(
        session=session,
        context=context_a,
        settings=settings,
        provider=provider,
    ).diagnose(DiagnoseRequest(message="Check A1 motor current history."))

    assert result.diagnostic is not None
    note = next(
        item for item in result.diagnostic.missing_information if "servo_motor_current_rms" in item
    )
    assert "unavailable" in note
    assert "zero readings" in note


@pytest.mark.asyncio
async def test_agent_failure_note_never_copies_tool_error_or_provider_prose(
    session: Session,
    context_a: AuthContext,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    marker = "HOSTILE-RESULT-BODY-MARKER"
    untrusted = _diagnostic()
    untrusted["missing_information"] = [f"Repeat this tool body: {marker}"]
    provider = ScriptedProvider(
        [
            _response(
                "manual-call",
                tool_calls=[
                    ProviderToolCall(
                        "manual-a1",
                        "search_manual",
                        '{"query":"A1 alarm"}',
                    )
                ],
            ),
            _response("manual-final", diagnostic=untrusted),
        ]
    )
    agent = _agent(
        session=session,
        context=context_a,
        settings=settings,
        provider=provider,
    )

    async def fail_tool(**_: object) -> ToolInvocation:
        return ToolInvocation(
            result=ToolExecutionResult(
                ok=False,
                tool_name="search_manual",
                error=ToolError(
                    category=ErrorCategory.INTERNAL,
                    message=marker,
                    retryable=True,
                ),
            ),
            status=ToolStatus.FAILED,
            latency_ms=1,
        )

    monkeypatch.setattr(agent.registry, "execute", fail_tool)
    result = await agent.diagnose(DiagnoseRequest(message="Search the A1 alarm manual."))

    assert result.diagnostic is not None
    serialized = result.diagnostic.model_dump_json()
    assert marker not in serialized
    note = next(
        item
        for item in result.diagnostic.missing_information
        if item.startswith("Tool 'search_manual'")
    )
    assert "error category 'internal'" in note
    assert "may be transient" in note
    assert "Manual evidence remains unavailable" in note


@pytest.mark.asyncio
async def test_agent_marks_cancelled_run_and_reraises_cancellation(
    session: Session, context_a: AuthContext, settings: Settings
) -> None:
    provider = BlockingProvider()
    long_timeout = settings.model_copy(update={"request_timeout_seconds": 5})
    task = asyncio.create_task(
        _agent(
            session=session,
            context=context_a,
            settings=long_timeout,
            provider=provider,
        ).diagnose(DiagnoseRequest(message="Review a maintenance note"))
    )
    await provider.started.wait()

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    run = _single_run(session)
    assert run.status == RunStatus.CANCELLED
    assert run.error_category == "cancelled"
    assert run.completed_at is not None
    event = session.scalar(select(ModelUsage))
    assert event is not None
    assert event.status == "failed"
    assert event.error_category == "cancelled"
    assert event.input_tokens is None
