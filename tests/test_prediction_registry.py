"""Optional prediction tool registration, grounding, and failure behavior offline."""

from __future__ import annotations

from uuid import uuid4

import httpx
import pytest
from pydantic import ValidationError

from app.agent.grounding import observations_from_tool_result
from app.config import Settings
from app.schemas.common import ToolStatus
from app.tools.prediction import FailurePredictionClient
from app.tools.registry import build_tool_registry

INPUT = {
    "type": "L",
    "air_temp_k": 300,
    "process_temp_k": 310,
    "rpm": 1500,
    "torque_nm": 40,
    "tool_wear_min": 100,
}
OUTPUT = {
    "failure_score": 0.0005919649847783148,
    "predicted_label": 0,
    "threshold": 0.5,
    "target_policy": "failure_evidence_or_v1",
}


def configured_registry(session, context_a, settings, handler):
    enabled = settings.model_copy(update={"failure_prediction_enabled": True})
    client = FailurePredictionClient(transport=httpx.MockTransport(handler))
    return build_tool_registry(session, context_a, enabled, prediction_client=client)


def test_prediction_is_disabled_by_default(registry):
    assert "predict_failure_risk" not in registry.names


@pytest.mark.asyncio
async def test_enabled_tool_returns_prediction_and_grounded_source(session, context_a, settings):
    registry = configured_registry(
        session, context_a, settings, lambda request: httpx.Response(200, json=OUTPUT)
    )
    definition = registry.definition("predict_failure_risk")
    assert definition is not None
    assert definition.read_only and not definition.requires_approval
    schema = definition.provider_schema()["parameters"]
    assert set(schema["required"]) == set(INPUT)
    assert schema["additionalProperties"] is False
    assert len(registry.names) == 7

    invocation = await registry.execute(
        name="predict_failure_risk", arguments=INPUT, run_id=str(uuid4())
    )
    assert invocation.status == ToolStatus.SUCCEEDED
    data = invocation.result.data
    assert data is not None
    assert {key: data[key] for key in OUTPUT} == OUTPUT
    assert data["source_reference"].startswith("tool:predict_failure_risk:")
    assert data["model_scope"] == "synthetic_ai4i_demo"
    observations = observations_from_tool_result("predict_failure_risk", data)
    assert len(observations) == 1
    assert observations[0].source_reference == data["source_reference"]
    assert "not a calibrated physical" in observations[0].statement
    assert "supplied inputs" in observations[0].statement


@pytest.mark.asyncio
@pytest.mark.parametrize("change", [{"tenant_id": "company-b"}, {"RNF": 1}, {"rpm": -1}])
async def test_invalid_tool_arguments_never_reach_http(session, context_a, settings, change):
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(200, json=OUTPUT)

    registry = configured_registry(session, context_a, settings, handle)
    invocation = await registry.execute(
        name="predict_failure_risk", arguments=INPUT | change, run_id=str(uuid4())
    )
    assert invocation.status == ToolStatus.REJECTED
    assert invocation.result.data is None
    assert not calls


@pytest.mark.asyncio
async def test_connection_failure_has_bounded_retries_and_no_score(session, context_a, settings):
    calls = []

    def handle(request):
        calls.append(request)
        raise httpx.ConnectError("tunnel stopped", request=request)

    registry = configured_registry(session, context_a, settings, handle)
    invocation = await registry.execute(
        name="predict_failure_risk", arguments=INPUT, run_id=str(uuid4())
    )
    assert invocation.status == ToolStatus.FAILED
    assert invocation.result.data is None
    assert invocation.result.error.retryable
    assert len(calls) == settings.provider_max_retries + 1


@pytest.mark.asyncio
async def test_invalid_service_response_is_not_retried(session, context_a, settings):
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(200, json=OUTPUT | {"threshold": 0.9})

    registry = configured_registry(session, context_a, settings, handle)
    invocation = await registry.execute(
        name="predict_failure_risk", arguments=INPUT, run_id=str(uuid4())
    )
    assert invocation.status == ToolStatus.FAILED
    assert invocation.result.data is None
    assert len(calls) == 1


@pytest.mark.parametrize("timeout", [0, -1, float("nan"), float("inf"), 31])
def test_config_rejects_invalid_prediction_timeout(timeout):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, failure_prediction_timeout_seconds=timeout)


def test_prediction_provenance_is_not_accepted_without_valid_contract():
    assert observations_from_tool_result("predict_failure_risk", OUTPUT) == []
