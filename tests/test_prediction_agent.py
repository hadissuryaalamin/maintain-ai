"""Offline agent scenarios with a real app/registry and a mocked prediction endpoint."""

from __future__ import annotations

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.llm.demo_provider import DemoProvider
from app.main import create_app
from app.prediction_requests import is_prediction_request, parse_prediction_inputs
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


def run_request(
    settings, database, headers, message, *, enabled=True, unavailable=False, score=None
):
    calls = []

    def handle(request):
        calls.append(request)
        assert json.loads(request.content) == INPUT
        if unavailable:
            raise httpx.ConnectError("tunnel closed", request=request)
        output = (
            OUTPUT
            if score is None
            else OUTPUT
            | {
                "failure_score": score,
                "predicted_label": int(score >= 0.5),
            }
        )
        return httpx.Response(200, json=output)

    def factory(session, context, registry_settings):
        return build_tool_registry(
            session,
            context,
            registry_settings,
            prediction_client=FailurePredictionClient(transport=httpx.MockTransport(handle)),
        )

    configured = settings.model_copy(
        update={
            "failure_prediction_enabled": enabled,
            "auto_seed": True,
            "provider_max_retries": 0,
            "request_timeout_seconds": 10,
        }
    )
    app = create_app(
        settings=configured, database=database, provider=DemoProvider(), registry_factory=factory
    )
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/incidents/diagnose", headers=headers, json={"message": message}
        )
        assert response.status_code == 200
        return response.json(), calls


@pytest.mark.parametrize(
    "prefix", ["Prediksi kegagalan", "Predict failure", "predict_failure_risk"]
)
def test_agent_selects_prediction_and_returns_only_grounded_evidence(
    settings, database, headers_a, prefix
):
    result, calls = run_request(settings, database, headers_a, prefix + ":\n" + json.dumps(INPUT))
    assert result["status"] == "completed"
    assert len(calls) == 1
    assert [item["tool_name"] for item in result["tool_trace"]] == ["predict_failure_risk"]
    observations = result["diagnostic"]["observations"]
    evidence = [item for item in observations if item["source_type"] == "tool"]
    assert len(evidence) == 1
    assert evidence[0]["source_reference"].startswith("tool:predict_failure_risk:")
    assert "failure-evidence score" in evidence[0]["statement"]
    assert "not a calibrated physical" in evidence[0]["statement"]
    assert result["diagnostic"]["possible_causes"] == []
    assert not any(
        item["requires_shutdown"] for item in result["diagnostic"]["recommended_actions"]
    )
    assert result["usage"]["provider"] == "demo"


@pytest.mark.parametrize(
    "message",
    [
        "Predict failure",
        "Predict failure: {}",
        "Predict failure: " + json.dumps(INPUT | {"type": "UNKNOWN"}),
        "Predict failure: " + json.dumps(INPUT | {"rpm": "1500"}),
        "Predict failure: " + json.dumps(INPUT | {"RNF": 1}),
        "Predict failure: " + json.dumps(INPUT | {"endpoint": "https://other.example"}),
    ],
)
def test_missing_or_invalid_inputs_request_clarification_without_http(
    settings, database, headers_a, message
):
    result, calls = run_request(settings, database, headers_a, message)
    assert result["status"] == "needs_clarification"
    assert not calls
    assert not result["tool_trace"]
    assert "air_temp_k" in " ".join(result["diagnostic"]["missing_information"])


def test_disabled_tool_is_not_called(settings, database, headers_a):
    result, calls = run_request(
        settings, database, headers_a, "Predict failure: " + json.dumps(INPUT), enabled=False
    )
    assert result["status"] == "needs_clarification"
    assert not calls
    assert not result["tool_trace"]
    assert "enable" in " ".join(result["diagnostic"]["missing_information"])


def test_closed_tunnel_produces_no_prediction_or_fault_hypothesis(settings, database, headers_a):
    result, calls = run_request(
        settings, database, headers_a, "Predict failure: " + json.dumps(INPUT), unavailable=True
    )
    assert result["status"] == "failed"
    assert len(calls) == 1
    assert result["tool_trace"][0]["status"] == "failed"
    assert not any(item["source_type"] == "tool" for item in result["diagnostic"]["observations"])
    assert result["diagnostic"]["possible_causes"] == []
    assert "No failure-evidence score" in " ".join(result["diagnostic"]["missing_information"])


def test_high_score_does_not_become_a_machine_diagnosis(settings, database, headers_a):
    result, calls = run_request(
        settings, database, headers_a, "Predict failure: " + json.dumps(INPUT), score=0.9
    )
    assert result["status"] == "completed"
    assert len(calls) == 1
    assert result["diagnostic"]["possible_causes"] == []
    assert any(
        "predicted class 1" in item["statement"] for item in result["diagnostic"]["observations"]
    )


@pytest.mark.parametrize(
    "suffix",
    [
        json.dumps(INPUT) + ' {"type":"H"}',
        json.dumps(INPUT).replace('"type": "L"', '"type": "L", "type": "H"'),
        json.dumps(INPUT).replace('"rpm": 1500', '"rpm": NaN'),
    ],
)
def test_parser_rejects_ambiguous_or_nonfinite_json(suffix):
    with pytest.raises(ValueError):
        parse_prediction_inputs("Predict failure: " + suffix)


@pytest.mark.parametrize("prefix", ["Do not predict failure", "The manual says predict failure"])
def test_mentioning_prediction_is_not_a_standalone_request(prefix):
    assert not is_prediction_request(prefix + ": " + json.dumps(INPUT))
