"""HTTP adapter for maintain-predict; endpoint configuration belongs to the operator.

The registry optionally exposes this adapter as a read-only tool. It does not
retrieve tenant sensor data or start an AWS resource or Session Manager tunnel.
"""

from __future__ import annotations

import hashlib
import math

import httpx

from app.schemas.prediction import (
    FailurePredictionInput,
    FailurePredictionOutput,
    FailureRiskToolOutput,
)
from app.tools.base import TransientToolError


class PredictionUnavailable(TransientToolError):
    """A timeout, transport failure, or temporarily unavailable prediction service."""


class PredictionResponseError(RuntimeError):
    """The service returned an unexpected status or violated its response contract."""


class FailurePredictionClient:
    """Synchronous adapter matching the existing synchronous tool handler interface.

    The default address targets the laptop's Session Manager tunnel. HTTPX
    timeouts apply to network operations, not an overall agent time budget.
    No automatic retries are performed here; the registry owns retry policy.
    """

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8003",
        *,
        timeout_seconds: float = 5.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        url = httpx.URL(base_url)
        if (
            url.scheme not in {"http", "https"}
            or not url.host
            or url.userinfo
            or url.query
            or url.fragment
            or url.path not in {"", "/"}
        ):
            raise ValueError("Prediction base URL must be an HTTP(S) origin without credentials.")
        if not math.isfinite(timeout_seconds) or not 0 < timeout_seconds <= 30:
            raise ValueError("Prediction timeout must be finite and between 0 and 30 seconds.")
        self._base_url = str(url).rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    def predict(self, value: FailurePredictionInput) -> FailurePredictionOutput:
        """Send validated measurements and fail explicitly instead of inventing a score."""
        # Revalidate even preconstructed model instances before any network activity.
        checked = FailurePredictionInput.model_validate(value.model_dump(mode="python"))
        try:
            with httpx.Client(
                base_url=self._base_url,
                timeout=self._timeout_seconds,
                transport=self._transport,
                follow_redirects=False,
                trust_env=False,
            ) as client:
                response = client.post("/predict", json=checked.model_dump(mode="json"))
        except httpx.TimeoutException:
            raise PredictionUnavailable("Prediction service timed out.") from None
        except httpx.RequestError:
            raise PredictionUnavailable("Prediction service could not be reached.") from None

        if response.status_code == 429 or response.status_code >= 500:
            raise PredictionUnavailable("Prediction service is temporarily unavailable.")
        if response.status_code != 200:
            # Do not expose upstream bodies, URLs, stack traces, or credentials.
            raise PredictionResponseError("Prediction service returned an unexpected status.")
        try:
            return FailurePredictionOutput.model_validate(response.json())
        except ValueError:
            message = "Prediction service returned an invalid result."
            raise PredictionResponseError(message) from None


class FailurePredictionToolHandler:
    """Adapt a validated result without treating a supplied input as a measured fact."""

    def __init__(self, client: FailurePredictionClient) -> None:
        self.client = client

    def predict_failure_risk(
        self, value: FailurePredictionInput, _: str | None
    ) -> FailureRiskToolOutput:
        result = self.client.predict(value)
        fingerprint = hashlib.sha256(value.model_dump_json().encode()).hexdigest()[:16]
        return FailureRiskToolOutput(
            **result.model_dump(),
            source_reference=f"tool:predict_failure_risk:{fingerprint}",
        )
