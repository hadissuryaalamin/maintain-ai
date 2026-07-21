"""Small, typed HTTP client used by the Streamlit application.

Identity headers are added here rather than at individual call sites. This keeps the
demo honest: changing the tenant in the sidebar creates a new client and every
request is scoped consistently.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


class APIError(RuntimeError):
    """A safe-to-display error returned by the API or transport."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True, slots=True)
class APIClient:
    """Tenant-aware client for the FastAPI application."""

    base_url: str
    tenant_id: str
    user_id: str
    timeout_seconds: float = 60.0

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Tenant-ID": self.tenant_id,
            "X-User-ID": self.user_id,
        }

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/health")

    def diagnose(
        self,
        message: str,
        *,
        optimization_mode: str,
        conversation_history: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "message": message,
            "optimization_mode": optimization_mode,
        }
        if conversation_history:
            payload["conversation_history"] = conversation_history
        return self._request("POST", "/api/v1/incidents/diagnose", json=payload)

    def confirm_approval(
        self,
        approval_id: str,
        *,
        approved: bool,
        idempotency_key: str,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/api/v1/approvals/{approval_id}/confirm",
            json={"approved": approved, "idempotency_key": idempotency_key},
        )

    def get_run(self, run_id: str) -> dict[str, Any]:
        return self._request("GET", f"/api/v1/runs/{run_id}")

    def analytics_summary(self) -> dict[str, Any]:
        return self._request("GET", "/api/v1/analytics/summary")

    def analytics_runs(self) -> dict[str, Any]:
        return self._request("GET", "/api/v1/analytics/runs")

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = f"{self.base_url.rstrip('/')}{path}"
        try:
            response = httpx.request(
                method,
                url,
                headers=self._headers,
                json=json,
                timeout=self.timeout_seconds,
            )
        except httpx.TimeoutException as exc:
            raise APIError(
                "The API did not respond before the request timeout. "
                "The run may still be processing."
            ) from exc
        except httpx.RequestError as exc:
            raise APIError(f"Could not reach the API at {self.base_url}.") from exc

        if response.is_success:
            if not response.content:
                return {}
            try:
                value = response.json()
            except ValueError as exc:
                raise APIError("The API returned an invalid JSON response.") from exc
            if isinstance(value, dict):
                return value
            return {"items": value}

        message = _safe_error_message(response)
        raise APIError(message, status_code=response.status_code)


def _safe_error_message(response: httpx.Response) -> str:
    """Extract a controlled API error without displaying response internals."""

    try:
        payload = response.json()
    except ValueError:
        payload = None

    detail: Any = payload.get("detail") if isinstance(payload, dict) else None
    if isinstance(detail, str) and detail.strip():
        return detail
    if isinstance(detail, list):
        messages = [
            str(item.get("msg", "Invalid request")) for item in detail if isinstance(item, dict)
        ]
        if messages:
            return "; ".join(messages)
    return f"API request failed with status {response.status_code}."
