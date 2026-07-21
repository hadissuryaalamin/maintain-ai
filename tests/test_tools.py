"""Tool contracts, allowlisting, validation, retry, and state-change safety tests."""

from __future__ import annotations

import json
from collections.abc import Callable
from uuid import uuid4

import pytest
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import AgentRun, ApprovalRequest, SecurityEvent, WorkOrder
from app.db.repositories import IdempotencyConflict, MaintenanceRepository
from app.schemas.common import ErrorCategory, RunStatus, ToolStatus
from app.schemas.tools import MachineStatusInput, MachineStatusOutput
from app.security.context import AuthContext
from app.tools.base import ToolDefinition, TransientToolError
from app.tools.registry import ToolRegistry

EXPECTED_TOOLS = {
    "search_manual",
    "get_machine_status",
    "get_sensor_history",
    "search_incident_history",
    "calculate_downtime_cost",
    "create_work_order",
}


def _add_run(session: Session, context: AuthContext) -> AgentRun:
    run = AgentRun(
        id=str(uuid4()),
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        task_type="diagnostic",
        optimization_mode="optimized",
        model="fake-model",
        provider="fake",
        status=RunStatus.RUNNING,
    )
    session.add(run)
    session.flush()
    return run


def test_provider_tool_schemas_are_strict_and_exclude_authority(
    registry: ToolRegistry,
) -> None:
    schemas = registry.provider_schemas

    assert {schema["name"] for schema in schemas} == EXPECTED_TOOLS
    assert all(schema["type"] == "function" for schema in schemas)
    assert all(schema["strict"] is True for schema in schemas)
    assert all(schema["parameters"]["additionalProperties"] is False for schema in schemas)

    serialized = json.dumps(schemas)
    for forbidden in ("tenant_id", "user_id", "approval_granted", "idempotency_key"):
        assert forbidden not in serialized


@pytest.mark.asyncio
async def test_unregistered_tool_is_rejected_and_audited(
    registry: ToolRegistry, session: Session
) -> None:
    invocation = await registry.execute(
        name="run_shell_command",
        arguments={"command": "whoami"},
        run_id="unused",
    )

    assert invocation.status == ToolStatus.REJECTED
    assert invocation.result.ok is False
    assert invocation.result.error is not None
    assert invocation.result.error.category == ErrorCategory.INVALID_TOOL
    assert "run_shell_command" not in invocation.result.error.message

    event = session.scalar(
        select(SecurityEvent).where(SecurityEvent.event_type == "unregistered_tool_rejected")
    )
    assert event is not None
    assert event.target_id == "run_shell_command"
    assert event.tenant_id == "company-a"


@pytest.mark.asyncio
@pytest.mark.parametrize("forbidden", ["tenant_id", "user_id", "approval_granted"])
async def test_model_cannot_supply_authoritative_tool_arguments(
    registry: ToolRegistry, session: Session, forbidden: str
) -> None:
    invocation = await registry.execute(
        name="get_machine_status",
        arguments={"machine_id": "A1", forbidden: "attacker-controlled"},
        run_id="unused",
    )

    assert invocation.status == ToolStatus.REJECTED
    assert invocation.result.error is not None
    assert invocation.result.error.category == ErrorCategory.INVALID_ARGUMENTS
    assert invocation.result.data is None
    events = list(
        session.scalars(
            select(SecurityEvent).where(
                SecurityEvent.event_type == "authoritative_argument_override_rejected"
            )
        )
    )
    assert events[-1].target_id == "get_machine_status"
    assert forbidden in events[-1].detail


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("arguments", "expected_field"),
    [
        (
            {
                "machine_id": "A1",
                "metric": "current",
                "start_time": "2026-07-20T02:00:00Z",
                "end_time": "2026-07-20T01:00:00Z",
            },
            "request",
        ),
        (
            {
                "machine_id": "A1",
                "metric": "current",
                "start_time": "2026-07-20T01:00:00Z",
                "end_time": "2026-07-20T02:00:00Z",
                "unexpected": "do-not-echo-this-value",
            },
            "unexpected",
        ),
    ],
)
async def test_invalid_arguments_fail_with_a_controlled_field_only_message(
    registry: ToolRegistry,
    arguments: dict[str, str],
    expected_field: str,
) -> None:
    secret_like_value = "do-not-echo-this-value"
    invocation = await registry.execute(
        name="get_sensor_history",
        arguments=arguments,
        run_id="unused",
    )

    assert invocation.status == ToolStatus.REJECTED
    assert invocation.result.error is not None
    assert invocation.result.error.category == ErrorCategory.INVALID_ARGUMENTS
    assert expected_field in invocation.result.error.message
    assert secret_like_value not in invocation.result.error.message


class _EmptyInput(BaseModel):
    pass


class _StringOutput(BaseModel):
    value: str


def _custom_registry(
    session: Session,
    context: AuthContext,
    handler: Callable[[BaseModel, str | None], BaseModel],
    *,
    retries: int,
) -> ToolRegistry:
    return ToolRegistry(
        session=session,
        context=context,
        definitions=[
            ToolDefinition(
                name="custom_tool",
                description="A deterministic test tool.",
                input_model=_EmptyInput,
                output_model=_StringOutput,
                handler=handler,
            )
        ],
        max_retries=retries,
    )


@pytest.mark.asyncio
async def test_tool_retries_only_transient_failures(
    session: Session, context_a: AuthContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = 0
    delays: list[float] = []

    def handler(_: BaseModel, __: str | None) -> _StringOutput:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise TransientToolError("temporary")
        return _StringOutput(value="recovered")

    async def fake_sleep(delay: float) -> None:
        delays.append(delay)

    monkeypatch.setattr("app.tools.registry.asyncio.sleep", fake_sleep)
    value = _custom_registry(session, context_a, handler, retries=2)

    invocation = await value.execute(name="custom_tool", arguments={}, run_id="unused")

    assert invocation.result.ok is True
    assert invocation.result.data == {"value": "recovered"}
    assert calls == 3
    assert delays == [0.05, 0.1]


@pytest.mark.asyncio
async def test_tool_does_not_retry_permanent_or_invalid_output_failures(
    session: Session, context_a: AuthContext
) -> None:
    calls = 0

    def handler(_: BaseModel, __: str | None) -> BaseModel:
        nonlocal calls
        calls += 1
        return MachineStatusInput(machine_id="A1")

    value = _custom_registry(session, context_a, handler, retries=3)
    invocation = await value.execute(name="custom_tool", arguments={}, run_id="unused")

    assert calls == 1
    assert invocation.status == ToolStatus.FAILED
    assert invocation.result.error is not None
    assert invocation.result.error.category == ErrorCategory.INTERNAL
    assert invocation.result.error.message == "Tool execution failed safely."


@pytest.mark.asyncio
async def test_state_change_creates_approval_but_not_work_order(
    registry: ToolRegistry, session: Session, context_a: AuthContext
) -> None:
    run = _add_run(session, context_a)
    arguments = {
        "machine_id": "A1",
        "title": "Inspect servo press",
        "description": "Investigate E217 after the product changeover.",
        "priority": "high",
    }

    invocation = await registry.execute(
        name="create_work_order",
        arguments=arguments,
        run_id=run.id,
    )

    assert invocation.status == ToolStatus.APPROVAL_REQUIRED
    assert invocation.result.error is not None
    assert invocation.result.error.category == ErrorCategory.APPROVAL_REQUIRED
    assert invocation.result.proposed_action == arguments
    assert invocation.result.approval_id
    assert session.scalar(select(func.count()).select_from(WorkOrder)) == 0
    approval = session.get(ApprovalRequest, invocation.result.approval_id)
    assert approval is not None
    assert approval.arguments_json == arguments
    assert approval.status == "pending"


def test_repository_work_order_idempotent_replay_and_conflict(
    session: Session, context_a: AuthContext
) -> None:
    repository = MaintenanceRepository(session, context_a)
    arguments = {
        "machine_id": "A1",
        "title": "Inspect servo press",
        "description": "Investigate the overload alarm.",
        "priority": "high",
        "idempotency_key": "same-operation-key",
    }

    first, first_replay = repository.create_work_order(**arguments)
    replay, second_replay = repository.create_work_order(**arguments)

    assert first_replay is False
    assert second_replay is True
    assert replay.id == first.id
    assert session.scalar(select(func.count()).select_from(WorkOrder)) == 1

    with pytest.raises(IdempotencyConflict, match="different work order"):
        repository.create_work_order(
            **{**arguments, "title": "A different operation"},
        )
    assert session.scalar(select(func.count()).select_from(WorkOrder)) == 1


def test_all_tool_definitions_use_typed_input_and_output_models(
    registry: ToolRegistry,
) -> None:
    for name in registry.names:
        definition = registry.definition(name)
        assert definition is not None
        assert issubclass(definition.input_model, BaseModel)
        assert issubclass(definition.output_model, BaseModel)
        if definition.requires_approval:
            assert definition.read_only is False
            assert name == "create_work_order"


def test_machine_status_output_rejects_extra_fields() -> None:
    with pytest.raises(ValueError):
        MachineStatusOutput.model_validate(
            {
                "machine_id": "A1",
                "name": "Press",
                "model": "SP-400",
                "line": "Line 3",
                "status": "stopped",
                "alarm_code": "E217",
                "last_maintenance_at": None,
                "source_reference": "tool:get_machine_status:A1",
                "tenant_id": "company-b",
            }
        )
