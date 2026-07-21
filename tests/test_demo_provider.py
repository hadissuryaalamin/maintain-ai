"""Deterministic behavior tests for the offline demo provider."""

from __future__ import annotations

import json
from dataclasses import replace
from typing import Any

import pytest

from app.llm.base import ProviderRequest, ProviderResponse
from app.llm.demo_provider import DemoProvider
from app.schemas.diagnostic import DiagnosticResult


def _request(
    message: str,
    *,
    prior: list[dict[str, Any]] | None = None,
    trusted_tenant_id: str | None = "company-a",
) -> ProviderRequest:
    return ProviderRequest(
        model="demo",
        instructions="Test instructions",
        input_items=[*(prior or []), {"role": "user", "content": message}],
        tools=[],
        output_schema=DiagnosticResult.model_json_schema(),
        max_output_tokens=1000,
        trusted_tenant_id=trusted_tenant_id,
    )


def _arguments(response: ProviderResponse) -> dict[str, dict[str, Any]]:
    return {call.name: json.loads(call.arguments) for call in response.tool_calls}


def _tool_output(
    *, name: str, data: dict[str, Any] | None = None, error: str | None = None
) -> dict[str, Any]:
    result: dict[str, Any] = {"ok": error is None, "tool_name": name}
    if error is None:
        result["data"] = data or {}
        result["error"] = None
    else:
        result["data"] = None
        result["error"] = {"category": error, "message": "safe error", "retryable": False}
    return {
        "type": "function_call_output",
        "call_id": f"result-{name}",
        "output": json.dumps({"trust_boundary": "untrusted_tool_result", "tool_result": result}),
    }


def _status_output(
    machine_id: str,
    model: str,
    *,
    status: str = "running",
    alarm_code: str | None = None,
) -> dict[str, Any]:
    return _tool_output(
        name="get_machine_status",
        data={
            "machine_id": machine_id,
            "model": model,
            "status": status,
            "alarm_code": alarm_code,
            "source_reference": f"tool:get_machine_status:{machine_id}",
        },
    )


@pytest.mark.asyncio
async def test_ambiguous_equipment_requests_clarification_without_tools() -> None:
    response = await DemoProvider().generate(
        _request("The A unit is overheating again; tell me the likely cause.")
    )
    line_only = await DemoProvider().generate(
        _request("The machine on Line 3 stopped after changeover.")
    )

    assert response.tool_calls == []
    assert response.metadata["terminal_status"] == "needs_clarification"
    assert line_only.tool_calls == []
    assert line_only.metadata["terminal_status"] == "needs_clarification"
    diagnostic = DiagnosticResult.model_validate_json(response.output_text)
    assert "machine ID" in diagnostic.missing_information[0]
    assert "No machine was assumed" in diagnostic.safety_notice


@pytest.mark.asyncio
async def test_specific_equipment_descriptor_is_resolved_without_a_default() -> None:
    provider = DemoProvider()
    request = _request("Servo press on Line 3 stopped with overload after changeover.")
    first = await provider.generate(request)
    response = await provider.generate(
        replace(
            request,
            input_items=request.input_items
            + first.output_items
            + [_status_output("A1", "SP-400", status="stopped", alarm_code="E217")],
        )
    )
    arguments = _arguments(response)

    assert set(_arguments(first)) == {"get_machine_status"}
    assert set(arguments) == {
        "get_sensor_history",
        "search_manual",
        "search_incident_history",
    }
    assert {value.get("machine_id") for value in arguments.values()} <= {None, "A1"}


@pytest.mark.asyncio
async def test_narrow_intents_call_only_relevant_tools_and_parse_sensor_window() -> None:
    provider = DemoProvider()
    manual_request = _request("Use the A1 manual to explain E217.")
    manual_status = await provider.generate(manual_request)
    manual = await provider.generate(
        replace(
            manual_request,
            input_items=manual_request.input_items
            + manual_status.output_items
            + [_status_output("A1", "SP-400", status="stopped", alarm_code="E217")],
        )
    )
    history = await provider.generate(
        _request("Summarize all incidents for A1 for a reliability benchmark.")
    )
    sensor_request = _request("Was A2 vibration high between 08:00 and 10:00 UTC?")
    sensor_status = await provider.generate(sensor_request)
    sensor = await provider.generate(
        replace(
            sensor_request,
            input_items=sensor_request.input_items
            + sensor_status.output_items
            + [_status_output("A2", "CP-200", alarm_code="VIB-HI")],
        )
    )

    assert set(_arguments(manual_status)) == {"get_machine_status"}
    assert set(_arguments(manual)) == {"search_manual"}
    assert set(_arguments(history)) == {"search_incident_history"}
    assert set(_arguments(sensor_status)) == {"get_machine_status"}
    assert set(_arguments(sensor)) == {"get_sensor_history"}
    sensor_arguments = _arguments(sensor)["get_sensor_history"]
    assert sensor_arguments == {
        "machine_id": "A2",
        "metric": "vibration_rms",
        "start_time": "2026-07-21T08:00:00Z",
        "end_time": "2026-07-21T10:00:00Z",
    }


@pytest.mark.asyncio
async def test_work_order_fields_are_preserved_for_the_approval_proposal() -> None:
    response = await DemoProvider().generate(
        _request(
            "Create a high-priority work order for A1 titled Inspect overload, "
            "with description Check die alignment after E217."
        )
    )

    assert len(response.tool_calls) == 1
    assert response.tool_calls[0].name == "create_work_order"
    assert json.loads(response.tool_calls[0].arguments) == {
        "machine_id": "A1",
        "title": "Inspect overload",
        "description": "Check die alignment after E217",
        "priority": "high",
    }


@pytest.mark.asyncio
async def test_alarm_comparison_discloses_mismatch_without_confirming_cause() -> None:
    provider = DemoProvider()
    request = _request("B1 displayed TRK-99. What does that code mean?")
    first = await provider.generate(request)
    status_items = (
        request.input_items
        + first.output_items
        + [_status_output("B1", "CV-120", status="stopped", alarm_code="TRK-04")]
    )
    manual_call = await provider.generate(replace(request, input_items=status_items))
    follow_up = (
        status_items
        + manual_call.output_items
        + [_tool_output(name="search_manual", data={"matches": [], "returned_chunks": 0})]
    )
    response = await provider.generate(replace(request, input_items=follow_up))

    diagnostic = DiagnosticResult.model_validate_json(response.output_text)
    combined = " ".join(diagnostic.missing_information).lower()
    assert "alarm mismatch" in combined
    assert "trk-99" in combined
    assert "trk-04" in combined
    assert all(cause.confidence != "high" for cause in diagnostic.possible_causes)


@pytest.mark.asyncio
async def test_empty_sensor_result_distinguishes_missing_from_unsupported_metric() -> None:
    provider = DemoProvider()

    supported_request = _request("Compare A1 motor current for the last hour.")
    supported_first = await provider.generate(supported_request)
    supported_status_items = (
        supported_request.input_items
        + supported_first.output_items
        + [_status_output("A1", "SP-400", status="stopped", alarm_code="E217")]
    )
    supported_sensor = await provider.generate(
        replace(supported_request, input_items=supported_status_items)
    )
    supported_arguments = _arguments(supported_sensor)["get_sensor_history"]
    assert supported_arguments["start_time"] == "2026-07-21T09:15:00Z"
    assert supported_arguments["end_time"] == "2026-07-21T10:15:00Z"
    supported = await provider.generate(
        replace(
            supported_request,
            input_items=supported_status_items
            + supported_sensor.output_items
            + [
                _tool_output(
                    name="get_sensor_history",
                    data={
                        "machine_id": "A1",
                        "metric": "servo_motor_current_rms",
                        "readings": [],
                        "source_reference": "tool:get_sensor_history:A1:servo_motor_current_rms",
                        "data_complete": False,
                    },
                )
            ],
        )
    )
    unsupported_request = _request("Show B2 acoustic emission for today.")
    unsupported_first = await provider.generate(unsupported_request)
    unsupported_status_items = (
        unsupported_request.input_items
        + unsupported_first.output_items
        + [_status_output("B2", "CNC-500")]
    )
    unsupported_sensor = await provider.generate(
        replace(unsupported_request, input_items=unsupported_status_items)
    )
    unsupported = await provider.generate(
        replace(
            unsupported_request,
            input_items=unsupported_status_items
            + unsupported_sensor.output_items
            + [
                _tool_output(
                    name="get_sensor_history",
                    data={
                        "machine_id": "B2",
                        "metric": "acoustic_emission",
                        "readings": [],
                        "source_reference": "tool:get_sensor_history:B2:acoustic_emission",
                        "data_complete": False,
                    },
                )
            ],
        )
    )

    assert supported.metadata["terminal_status"] == "completed"
    assert "Motor current history unavailable" in supported.output_text
    assert unsupported.metadata["terminal_status"] == "failed"
    assert "Acoustic emission is unavailable" in unsupported.output_text


@pytest.mark.asyncio
async def test_current_condition_uses_machine_default_not_bare_word_current() -> None:
    provider = DemoProvider()
    request = _request("Summarize B2's current condition using the relevant recent context.")
    first = await provider.generate(request)
    response = await provider.generate(
        replace(
            request,
            input_items=request.input_items
            + first.output_items
            + [_status_output("B2", "CNC-500")],
        )
    )

    assert _arguments(response)["get_sensor_history"]["metric"] == "spindle_vibration_rms"


def test_assessment_uses_only_relevant_recent_context_when_requested() -> None:
    items = [
        {"role": "user", "content": "Old routine lubrication note."},
        {"role": "assistant", "content": "B2 operator reports rough finish but no alarm."},
        {
            "role": "user",
            "content": "Summarize B2's current condition using relevant recent context.",
        },
    ]

    assessment = DemoProvider._assessment_text(items)

    assert "rough finish" in assessment
    assert "lubrication note" not in assessment
    assert DemoProvider._alarm_codes("[conversation:item-298] no alarm") == set()


@pytest.mark.asyncio
async def test_known_scoped_resource_failure_returns_access_denied_without_data() -> None:
    request = _request("Get the live status for B1.")
    first = await DemoProvider().generate(request)
    response = await DemoProvider().generate(
        replace(
            request,
            input_items=request.input_items
            + first.output_items
            + [_tool_output(name="get_machine_status", error="tenant_access_denied")],
        )
    )

    diagnostic = DiagnosticResult.model_validate_json(response.output_text)
    assert response.metadata["terminal_status"] == "access_denied"
    assert diagnostic.observations == []
    assert "authenticated tenant scope" in " ".join(diagnostic.missing_information)


@pytest.mark.asyncio
async def test_denied_machine_does_not_expose_derived_model_or_metric_arguments() -> None:
    provider = DemoProvider()
    request = _request("Show B1 status, sensors, manuals, and incidents.")
    first = await provider.generate(request)
    serialized_first = json.dumps(
        [json.loads(call.arguments) for call in first.tool_calls], sort_keys=True
    )

    assert [(call.name, json.loads(call.arguments)) for call in first.tool_calls] == [
        ("get_machine_status", {"machine_id": "B1"})
    ]
    assert "CV-120" not in serialized_first
    assert "belt_tracking_offset" not in serialized_first

    denied = await provider.generate(
        replace(
            request,
            input_items=request.input_items
            + first.output_items
            + [_tool_output(name="get_machine_status", error="tenant_access_denied")],
        )
    )

    assert denied.tool_calls == []
    assert denied.metadata["terminal_status"] == "access_denied"


@pytest.mark.asyncio
async def test_equipment_aliases_resolve_only_within_trusted_tenant() -> None:
    provider = DemoProvider()
    foreign_description = await provider.generate(
        _request("Get the packaging conveyor status.", trusted_tenant_id="company-a")
    )
    foreign_model = await provider.generate(
        _request("Get the CV-120 status.", trusted_tenant_id="company-a")
    )

    for response in (foreign_description, foreign_model):
        assert response.tool_calls == []
        assert response.metadata["terminal_status"] == "needs_clarification"
        assert "B1" not in response.output_text

    own_press = await provider.generate(
        _request("Get the servo press status.", trusted_tenant_id="company-a")
    )
    own_conveyor = await provider.generate(
        _request("Get the packaging conveyor status.", trusted_tenant_id="company-b")
    )
    assert json.loads(own_press.tool_calls[0].arguments) == {"machine_id": "A1"}
    assert json.loads(own_conveyor.tool_calls[0].arguments) == {"machine_id": "B1"}
