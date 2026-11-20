"""Offline prediction contracts and transport behavior; no AWS or model API calls."""

from __future__ import annotations

import json

import httpx
import pytest
from pydantic import ValidationError

from app.schemas.prediction import FailurePredictionInput
from app.tools.prediction import (
    FailurePredictionClient,
    PredictionResponseError,
    PredictionUnavailable,
)

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


def test_valid_request_sends_only_raw_measurements_and_sets_timeout() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert str(request.url) == "http://127.0.0.1:8003/predict"
        assert json.loads(request.content) == INPUT
        assert request.extensions["timeout"] == dict.fromkeys(
            ["connect", "read", "write", "pool"], 2.0
        )
        return httpx.Response(200, json=OUTPUT)

    client = FailurePredictionClient(transport=httpx.MockTransport(handle), timeout_seconds=2)
    assert client.predict(FailurePredictionInput(**INPUT)).model_dump() == OUTPUT


@pytest.mark.parametrize(
    "change",
    [
        {"type": "INVALID"},
        {"rpm": 0},
        {"air_temp_k": -1},
        {"process_temp_k": float("nan")},
        {"torque_nm": -1},
        {"tool_wear_min": float("inf")},
        {"rpm": "1500"},
        {"rpm": True},
        {"torque_nm": 1e308, "tool_wear_min": 1e308},
        {"tenant_id": "another-tenant"},
        {"Machine failure": 1},
        {"RNF": 1},
    ],
)
def test_invalid_measurements_and_extra_fields_are_rejected(change: dict) -> None:
    with pytest.raises(ValidationError):
        FailurePredictionInput(**(INPUT | change))


def test_missing_measurement_is_not_fabricated() -> None:
    with pytest.raises(ValidationError):
        FailurePredictionInput(**{key: value for key, value in INPUT.items() if key != "rpm"})


@pytest.mark.parametrize("error_type", [httpx.ConnectError, httpx.ReadTimeout])
def test_transport_failures_are_explicit_and_not_retried(error_type: type) -> None:
    calls = []

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        raise error_type("private upstream error", request=request)

    client = FailurePredictionClient(transport=httpx.MockTransport(handle))
    with pytest.raises(PredictionUnavailable) as exc:
        client.predict(FailurePredictionInput(**INPUT))
    assert "private" not in str(exc.value)
    assert len(calls) == 1


@pytest.mark.parametrize("status", [429, 500, 503])
def test_transient_http_failures(status: int) -> None:
    client = FailurePredictionClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(status))
    )
    with pytest.raises(PredictionUnavailable):
        client.predict(FailurePredictionInput(**INPUT))


@pytest.mark.parametrize("status", [302, 401, 404, 422])
def test_other_statuses_fail_without_following_redirects(status: int) -> None:
    calls = []

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(status, headers={"location": "https://other.example"})

    client = FailurePredictionClient(transport=httpx.MockTransport(handle))
    with pytest.raises(PredictionResponseError):
        client.predict(FailurePredictionInput(**INPUT))
    assert len(calls) == 1


@pytest.mark.parametrize(
    "payload",
    [
        OUTPUT | {"failure_score": 1.2},
        OUTPUT | {"failure_score": float("nan")},
        OUTPUT | {"threshold": 0.7},
        OUTPUT | {"target_policy": "unknown"},
        OUTPUT | {"predicted_label": True},
        OUTPUT | {"predicted_label": 1},
        OUTPUT | {"extra": "unexpected"},
        {"failure_score": 0.1},
        [],
    ],
)
def test_invalid_service_results_are_never_accepted(payload: object) -> None:
    # NaN is intentionally malformed semantic JSON evidence for the parser test.
    raw = json.dumps(payload).encode()
    client = FailurePredictionClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, content=raw))
    )
    with pytest.raises(PredictionResponseError):
        client.predict(FailurePredictionInput(**INPUT))


def test_non_json_result_is_rejected() -> None:
    client = FailurePredictionClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, text="not JSON"))
    )
    with pytest.raises(PredictionResponseError):
        client.predict(FailurePredictionInput(**INPUT))


@pytest.mark.parametrize("score,label", [(0.5, 1), (0.9, 1), (0.49, 0)])
def test_threshold_boundary(score: float, label: int) -> None:
    client = FailurePredictionClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json=OUTPUT
                | {
                    "failure_score": score,
                    "predicted_label": label,
                },
            )
        )
    )
    assert client.predict(FailurePredictionInput(**INPUT)).predicted_label == label


@pytest.mark.parametrize("timeout", [0, -1, float("inf"), float("nan"), 31])
def test_invalid_timeout_is_rejected(timeout: float) -> None:
    with pytest.raises(ValueError):
        FailurePredictionClient(timeout_seconds=timeout)


@pytest.mark.parametrize(
    "url",
    [
        "ftp://host",
        "http://host/path",
        "http://u:p@host",
        "http://host?token=secret",
        "http://host#fragment",
    ],
)
def test_invalid_endpoint_configuration_is_rejected(url: str) -> None:
    with pytest.raises(ValueError):
        FailurePredictionClient(base_url=url)
