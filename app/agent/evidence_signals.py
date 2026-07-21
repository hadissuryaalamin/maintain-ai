"""Application-authored uncertainty signals derived from validated evidence only.

The provider never supplies prose to this module.  Signal fields are either extracted from the
current validated user message, parsed from a successful typed tool output, or selected from
closed application enums.  Rendering is intentionally centralized so tool error bodies and
other untrusted text cannot reach the final diagnostic.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from pydantic import ValidationError

from app.schemas.common import ErrorCategory
from app.schemas.tools import MachineStatusOutput, SensorHistoryOutput

_KNOWN_TOOL_NAMES = frozenset(
    {
        "search_manual",
        "get_machine_status",
        "get_sensor_history",
        "search_incident_history",
        "calculate_downtime_cost",
        "create_work_order",
    }
)
_CODE_TOKEN = re.compile(
    r"(?<![A-Za-z0-9-])(?:[A-Za-z]{1,8}\d{2,6}|[A-Za-z]{2,8}-[A-Za-z0-9]{2,8})"
    r"(?![A-Za-z0-9-])"
)
_ALARM_CONTEXT = re.compile(
    r"(?i)\b(?:alarm|fault|error|code|display(?:ed|s)?|show(?:ed|s|ing)?|"
    r"report(?:ed|s|ing)?|read(?:s|ing)?)\b(?:\s+(?:is|was))?\s*[:=#-]?\s*$"
)
_SAFE_CODE = re.compile(r"[A-Z]{1,8}(?:\d{2,6}|-[A-Z0-9]{2,8})")
_SAFE_METRIC = re.compile(r"[A-Za-z0-9_.:-]{1,100}")


@dataclass(frozen=True, slots=True)
class AlarmMismatchSignal:
    """A user-reported code differs from the validated current machine status."""

    reported_code: str
    status_code: str | None


@dataclass(frozen=True, slots=True)
class SensorEvidenceSignal:
    """A successful sensor response contained absent or incomplete history."""

    metric: str
    zero_readings: bool
    data_complete: bool


@dataclass(frozen=True, slots=True)
class ToolFailureSignal:
    """A controlled tool failure without its potentially sensitive error body."""

    tool_name: str
    error_category: ErrorCategory
    retryable: bool


GroundingSignal = AlarmMismatchSignal | SensorEvidenceSignal | ToolFailureSignal


def signals_from_successful_tool_result(
    *,
    current_message: str,
    tool_name: str,
    data: dict[str, object],
) -> list[GroundingSignal]:
    """Build signals from a successful result after independently validating its schema."""

    try:
        if tool_name == "get_machine_status":
            status = MachineStatusOutput.model_validate(data)
            status_code = _normalized_code(status.alarm_code)
            reported_codes = _explicit_alarm_codes(current_message, status_code)
            return [
                AlarmMismatchSignal(reported_code=code, status_code=status_code)
                for code in reported_codes
                if code != status_code
            ]

        if tool_name == "get_sensor_history":
            history = SensorHistoryOutput.model_validate(data)
            if history.readings and history.data_complete:
                return []
            metric = _safe_metric(history.metric)
            return [
                SensorEvidenceSignal(
                    metric=metric,
                    zero_readings=not history.readings,
                    data_complete=history.data_complete,
                )
            ]
    except ValidationError:
        # A mismatch after the registry validation is not trusted enough to produce a signal.
        return []
    return []


def signal_from_tool_failure(
    *,
    tool_name: str,
    error_category: str | ErrorCategory,
    retryable: bool,
) -> ToolFailureSignal:
    """Build a generic failure signal from closed, application-controlled vocabulary."""

    controlled_name = tool_name if tool_name in _KNOWN_TOOL_NAMES else "unregistered_tool"
    try:
        controlled_category = ErrorCategory(error_category)
    except ValueError:
        controlled_category = ErrorCategory.INTERNAL
    return ToolFailureSignal(
        tool_name=controlled_name,
        error_category=controlled_category,
        retryable=retryable,
    )


def render_grounding_signal(signal: GroundingSignal) -> str:
    """Render only fixed templates and normalized identifiers into final-response prose."""

    if isinstance(signal, AlarmMismatchSignal):
        reported = _normalized_code(signal.reported_code) or "unrecognized"
        observed = _normalized_code(signal.status_code) or "none"
        return (
            f"Alarm mismatch: the current message reports code '{reported}', while validated "
            f"machine status reports code '{observed}'. Treat the user-reported code as "
            "unconfirmed until the discrepancy is resolved."
        )

    if isinstance(signal, SensorEvidenceSignal):
        metric = _safe_metric(signal.metric)
        if signal.zero_readings and not signal.data_complete:
            return (
                f"Sensor history for metric '{metric}' is unavailable (zero readings), and the "
                "validated result marks the data incomplete; this evidence remains unconfirmed."
            )
        if signal.zero_readings:
            return (
                f"Sensor history for metric '{metric}' is unavailable because the validated "
                "result contains zero readings."
            )
        return (
            f"Sensor history data for metric '{metric}' is incomplete; this evidence remains "
            "unconfirmed."
        )

    transient = " The failure may be transient." if signal.retryable else ""
    guidance = {
        "get_machine_status": " Machine status and alarm evidence remain unconfirmed.",
        "search_manual": " Manual evidence remains unavailable.",
        "get_sensor_history": " Sensor history evidence remains unavailable.",
        "search_incident_history": " Historical incident evidence remains unavailable.",
        "calculate_downtime_cost": " The downtime-cost estimate remains unavailable.",
        "create_work_order": " No work-order state change was completed.",
        "unregistered_tool": " No evidence was accepted from that request.",
    }[signal.tool_name]
    return (
        f"Tool '{signal.tool_name}' did not return usable evidence (error category "
        f"'{signal.error_category.value}').{transient}{guidance}"
    )


def _explicit_alarm_codes(message: str, status_code: str | None) -> list[str]:
    """Extract bounded alarm-like tokens without treating surrounding user prose as fact."""

    results: list[str] = []
    status_prefix = _code_prefix(status_code)
    for match in _CODE_TOKEN.finditer(message):
        candidate = _normalized_code(match.group())
        if candidate is None:
            continue
        preceding_context = message[max(0, match.start() - 32) : match.start()]
        is_explicit = (
            (candidate.startswith("E") and candidate[1:].isdigit())
            or candidate == status_code
            or (_code_prefix(candidate) is not None and _code_prefix(candidate) == status_prefix)
            or _ALARM_CONTEXT.search(preceding_context) is not None
        )
        if is_explicit and candidate not in results:
            results.append(candidate)
    return results[:3]


def _normalized_code(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().upper()
    return normalized if _SAFE_CODE.fullmatch(normalized) else None


def _code_prefix(code: str | None) -> str | None:
    if code is None:
        return None
    match = re.match(r"[A-Z]+", code)
    return match.group() if match else None


def _safe_metric(value: str) -> str:
    return value if _SAFE_METRIC.fullmatch(value) else "unrecognized_metric"
