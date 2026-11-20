"""Deterministic grounding and safety enforcement for structured diagnostics."""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

from pydantic import ValidationError

from app.agent.evidence_signals import GroundingSignal, render_grounding_signal
from app.schemas.api import ConversationMessage
from app.schemas.common import RunStatus
from app.schemas.diagnostic import (
    Confidence,
    DiagnosticResult,
    Observation,
    PossibleCause,
    RecommendedAction,
    SourceType,
)
from app.schemas.prediction import FailureRiskToolOutput
from app.schemas.tools import (
    DowntimeCostOutput,
    MachineStatusOutput,
    SearchIncidentHistoryOutput,
    SearchManualOutput,
    SensorHistoryOutput,
)

CANONICAL_SAFETY_NOTICE = (
    "Preliminary decision support only. Follow site procedures and have a qualified person "
    "apply lockout/tagout and verify a zero-energy state before guards are opened or invasive "
    "work begins. Never bypass interlocks. This system cannot control machinery."
)

CANONICAL_ISOLATION_ACTION = RecommendedAction(
    step=1,
    action=(
        "Follow site lockout/tagout and verify a zero-energy state before opening guards or "
        "beginning invasive inspection."
    ),
    requires_shutdown=True,
    requires_approval=False,
)

_SAFETY_DEFEAT_ACTION = re.compile(
    r"(?i)\b(?:bypass|defeat|disable|override)\b.{0,80}"
    r"\b(?:interlock|guard|safety|lockout|tagout|emergency\s+stop)\b"
)
_MACHINE_CONTROL_ACTION = re.compile(
    r"(?i)\b(?:start|restart|reset|energize|operate|run|cycle|jog|resume)\b|"
    r"\b(?:power|turn)\s+(?:the\s+\w+\s+)?(?:on|up)\b|"
    r"\bclear\s+(?:the\s+)?(?:alarm|fault)\b"
)
_LIVE_ELECTRICAL_ACTION = re.compile(
    r"(?i)(?:\b(?:live|energized|powered)\b.{0,100}"
    r"\b(?:electrical|electric|terminal|wire|wiring|cabinet|panel|circuit|voltage)\b|"
    r"\b(?:electrical|electric|terminal|wire|wiring|cabinet|panel|circuit|voltage)\b"
    r".{0,100}\b(?:live|energized|powered)\b)"
)
_INVASIVE_ACTION = re.compile(
    r"(?i)(?:\b(?:open|remove|access|enter|inspect|check|measure|test)\b.{0,100}"
    r"\b(?:guard|cover|cabinet|panel|enclosure|terminal|wire|wiring|circuit|belt|coupling|"
    r"bearing|motor|spindle|gearbox|hydraulic|pneumatic)\b|"
    r"\b(?:replace|repair|adjust|tighten|loosen|disconnect|reconnect|disassemble)\b)"
)
_HISTORY_PROVENANCE_MARKER = re.compile(
    r"\[(conversation:(?:turn|item)-[0-9]+)\]",
    re.IGNORECASE,
)
_HISTORY_OBSERVATION_STATEMENT = (
    "A retained user-authored conversation message was available at this provenance reference."
)
_MAX_HISTORY_OBSERVATIONS = 8


def observations_from_tool_result(tool_name: str, data: dict[str, Any]) -> list[Observation]:
    """Create trusted observation text from a registry-validated tool result.

    Retrieved free text is deliberately not copied into the diagnostic. Manual excerpts and
    incident narratives remain available to the model as untrusted evidence, while the final
    response exposes only application-authored facts and their exact source references.
    """

    try:
        if tool_name == "predict_failure_risk":
            prediction = FailureRiskToolOutput.model_validate(data)
            statement = (
                f"The synthetic AI4I model returned failure-evidence score "
                f"{prediction.failure_score:.8g}, predicted class {prediction.predicted_label}, "
                f"and threshold {prediction.threshold} for the supplied inputs under "
                f"{prediction.target_policy}. This is not a calibrated physical failure "
                "probability, an observed machine condition, or a diagnosis."
            )
            observation = _observation(statement, SourceType.TOOL, prediction.source_reference)
            return [observation] if observation else []

        if tool_name == "get_machine_status":
            machine_status = MachineStatusOutput.model_validate(data)
            details = (
                f"Machine {_quoted(machine_status.machine_id)} ({_quoted(machine_status.name)}, "
                f"model {_quoted(machine_status.model)}, line {_quoted(machine_status.line)}) was "
                f"recorded with status {_quoted(machine_status.status)}"
            )
            if machine_status.alarm_code:
                details += f" and alarm {_quoted(machine_status.alarm_code)}"
            details += "."
            observation = _observation(details, SourceType.TOOL, machine_status.source_reference)
            return [observation] if observation else []

        if tool_name == "get_sensor_history":
            sensor_history = SensorHistoryOutput.model_validate(data)
            valid_readings = [
                (item, float(item.value))
                for item in sensor_history.readings
                if item.value is not None
            ]
            statement = (
                f"Sensor history for machine {_quoted(sensor_history.machine_id)} and metric "
                f"{_quoted(sensor_history.metric)} returned {len(valid_readings)} numeric "
                f"reading(s) out of {len(sensor_history.readings)} requested result(s)"
            )
            if valid_readings:
                latest, latest_value = max(valid_readings, key=lambda item: item[0].timestamp)
                numeric_values = [number for _, number in valid_readings]
                statement += (
                    f"; the observed range was {_number(min(numeric_values))} to "
                    f"{_number(max(numeric_values))} {_fragment(latest.unit)}, and the latest "
                    f"reading was {_number(latest_value)} {_fragment(latest.unit)} at "
                    f"{latest.timestamp.isoformat()}"
                )
            completeness = "complete" if sensor_history.data_complete else "incomplete"
            statement += f". The returned series was marked {completeness}."
            observation = _observation(statement, SourceType.TOOL, sensor_history.source_reference)
            return [observation] if observation else []

        if tool_name == "search_manual":
            manual_results = SearchManualOutput.model_validate(data)
            observations: list[Observation] = []
            for manual_match in manual_results.matches:
                observation = _observation(
                    (
                        f"Tenant-scoped manual chunk {_quoted(manual_match.chunk_id)} was "
                        f"retrieved from section {_quoted(manual_match.section)} for this run."
                    ),
                    SourceType.MANUAL,
                    manual_match.source_reference,
                )
                if observation:
                    observations.append(observation)
            return observations

        if tool_name == "search_incident_history":
            incident_results = SearchIncidentHistoryOutput.model_validate(data)
            observations = []
            for incident_match in incident_results.matches:
                observation = _observation(
                    (
                        f"Historical incident {_quoted(incident_match.incident_id)} for machine "
                        f"{_quoted(incident_match.machine_id)} at "
                        f"{incident_match.occurred_at.isoformat()} was retrieved for comparison."
                    ),
                    SourceType.INCIDENT_HISTORY,
                    incident_match.source_reference,
                )
                if observation:
                    observations.append(observation)
            return observations

        if tool_name == "calculate_downtime_cost":
            downtime_cost = DowntimeCostOutput.model_validate(data)
            observation = _observation(
                (
                    f"Configured downtime cost for machine {_quoted(downtime_cost.machine_id)} "
                    f"over {downtime_cost.downtime_minutes} minute(s) was "
                    f"{downtime_cost.estimated_cost} {_fragment(downtime_cost.currency)}, using "
                    f"an hourly cost of {downtime_cost.hourly_cost} "
                    f"{_fragment(downtime_cost.currency)}."
                ),
                SourceType.TOOL,
                downtime_cost.source_reference,
            )
            return [observation] if observation else []
    except ValidationError:
        # The registry validates output before this function is called. Treat any later mismatch
        # as unavailable evidence rather than allowing it to weaken final-response grounding.
        return []
    return []


def observations_from_retained_user_history(
    messages: Sequence[ConversationMessage],
) -> list[Observation]:
    """Create provenance-only observations from retained, validated user history.

    Conversation prose is untrusted and therefore never copied into the final diagnostic.  A
    marker in assistant-authored history is also ignored: assistant turns may help the model
    follow a conversation, but they are not an authoritative user report.
    """

    observations: list[Observation] = []
    seen: set[str] = set()
    for message in messages:
        if message.role != "user":
            continue
        for match in _HISTORY_PROVENANCE_MARKER.finditer(message.content):
            source_reference = match.group(1).casefold()
            if source_reference in seen:
                continue
            seen.add(source_reference)
            observations.append(
                Observation(
                    statement=_HISTORY_OBSERVATION_STATEMENT,
                    source_type=SourceType.USER,
                    source_reference=source_reference,
                )
            )
            if len(observations) == _MAX_HISTORY_OBSERVATIONS:
                return observations
    return observations


def enforce_grounding(
    diagnostic: DiagnosticResult,
    evidence_observations: Sequence[Observation],
    terminal_status: RunStatus = RunStatus.COMPLETED,
    *,
    retained_history: Sequence[ConversationMessage] = (),
    grounding_signals: Sequence[GroundingSignal] = (),
) -> DiagnosticResult:
    """Replace model-authored factual fields and enforce deterministic action safety."""

    provider_observation_count = len(diagnostic.observations)
    provider_cause_count = len(diagnostic.possible_causes)
    provider_action_count = len(diagnostic.recommended_actions)
    unsafe_action_count = sum(
        _is_unsafe_action(action.action) for action in diagnostic.recommended_actions
    )
    history_observations = observations_from_retained_user_history(retained_history)
    grounded = _deduplicated_evidence(
        evidence_observations,
        limit=29 - len(history_observations),
    )

    diagnostic.incident_summary = _grounded_incident_summary(
        len(grounded), len(history_observations)
    )
    diagnostic.observations = [
        Observation(
            statement="The current incident description was supplied by the user.",
            source_type=SourceType.USER,
            source_reference="user:current-message",
        ),
        *grounded,
        *history_observations,
    ]
    diagnostic.possible_causes = _bounded_hypotheses(grounded)
    # Missing-information prose is another factual channel, so do not retain model-authored text.
    diagnostic.missing_information = []
    rendered_signals: list[str] = []
    for signal in grounding_signals:
        rendered = render_grounding_signal(signal)
        if rendered not in rendered_signals:
            rendered_signals.append(rendered)
        if len(rendered_signals) == 12:
            break
    for rendered in rendered_signals:
        _append_missing_information(diagnostic, rendered)
    if provider_observation_count:
        _append_missing_information(
            diagnostic,
            (
                f"{provider_observation_count} provider-authored observation(s) were replaced "
                "with application-grounded evidence."
            ),
        )
    if provider_cause_count:
        _append_missing_information(
            diagnostic,
            (
                f"{provider_cause_count} model-authored cause hypothesis(es) were replaced with "
                "low-confidence, evidence-bounded hypotheses."
            ),
        )
    if not grounded:
        _append_missing_information(
            diagnostic,
            "No successful tenant-scoped external evidence was available for this run.",
        )
    status_guidance = _status_missing_information(terminal_status)
    if status_guidance:
        _append_missing_information(diagnostic, status_guidance)
    if provider_action_count:
        _append_missing_information(
            diagnostic,
            (
                f"{provider_action_count} model-authored recommended action(s) were replaced "
                "with application-authored safety steps."
            ),
        )
    if unsafe_action_count:
        _append_missing_information(
            diagnostic,
            (f"{unsafe_action_count} unsafe model-recommended action(s) were removed by policy."),
        )

    generated_actions = _deterministic_actions(terminal_status, grounded)
    diagnostic.recommended_actions = [
        action.model_copy(
            update={
                "step": index,
                "requires_shutdown": action.requires_shutdown or _is_invasive(action.action),
            }
        )
        for index, action in enumerate(generated_actions[:20], start=1)
    ]
    diagnostic.safety_notice = CANONICAL_SAFETY_NOTICE
    return diagnostic


def _deduplicated_evidence(
    evidence: Sequence[Observation], *, limit: int = 29
) -> list[Observation]:
    deduplicated: list[Observation] = []
    seen: set[tuple[SourceType, str, str]] = set()
    for observation in evidence:
        if observation.source_type == SourceType.USER:
            continue
        key = (observation.source_type, observation.source_reference, observation.statement)
        if key in seen:
            continue
        seen.add(key)
        deduplicated.append(observation)
        if len(deduplicated) == limit:
            break
    return deduplicated


def _grounded_incident_summary(
    external_evidence_count: int,
    history_reference_count: int,
) -> str:
    if not external_evidence_count:
        history_context = (
            f" and {history_reference_count} retained user-conversation provenance reference(s)"
            if history_reference_count
            else ""
        )
        return (
            f"Preliminary diagnostic based on the current user report{history_context}; no "
            "successful tenant-scoped external evidence was available."
        )
    history_context = (
        f" and {history_reference_count} retained user-conversation provenance reference(s)"
        if history_reference_count
        else ""
    )
    return (
        "Preliminary diagnostic based on the current user report and "
        f"{external_evidence_count} application-grounded, tenant-scoped evidence item(s)"
        f"{history_context}. The possible causes remain unconfirmed pending qualified "
        "inspection."
    )


def _status_missing_information(status: RunStatus) -> str | None:
    if status == RunStatus.NEEDS_CLARIFICATION:
        return (
            "Provide the exact machine ID and, if available, the alarm code, affected sensor "
            "metric, and relevant time window."
        )
    if status == RunStatus.ACCESS_DENIED:
        return (
            "The requested resource was unavailable in the authenticated tenant scope; use an "
            "in-scope machine ID or ask a tenant administrator for access guidance."
        )
    if status == RunStatus.FAILED:
        return (
            "Evidence collection or model processing did not complete; retry once, then "
            "escalate with the run ID if the failure persists."
        )
    return None


def _deterministic_actions(
    status: RunStatus, evidence: Sequence[Observation]
) -> list[RecommendedAction]:
    actions = [CANONICAL_ISOLATION_ACTION]
    if status == RunStatus.NEEDS_CLARIFICATION:
        actions.append(
            RecommendedAction(
                step=2,
                action=(
                    "Provide the exact machine ID, alarm code, affected sensor metric, and "
                    "relevant time window before further diagnosis."
                ),
                requires_shutdown=False,
                requires_approval=False,
            )
        )
        return actions
    if status == RunStatus.ACCESS_DENIED:
        actions.append(
            RecommendedAction(
                step=2,
                action=(
                    "Use an in-scope machine ID or ask a tenant administrator for access "
                    "guidance; do not attempt to bypass tenant controls."
                ),
                requires_shutdown=False,
                requires_approval=False,
            )
        )
        return actions
    if status == RunStatus.FAILED:
        actions.append(
            RecommendedAction(
                step=2,
                action=(
                    "Retry evidence collection once, then escalate with the run ID if the "
                    "failure persists."
                ),
                requires_shutdown=False,
                requires_approval=False,
            )
        )
        return actions

    categories = {_evidence_category(observation) for observation in evidence}
    categories.discard(None)
    if not categories:
        actions.append(
            RecommendedAction(
                step=2,
                action=(
                    "Collect the exact machine ID, alarm code, affected component, and recent "
                    "sensor window before attempting further diagnosis."
                ),
                requires_shutdown=False,
                requires_approval=False,
            )
        )
        return actions
    if "machine_status" in categories:
        actions.append(
            RecommendedAction(
                step=2,
                action=(
                    "Have a qualified technician verify the grounded machine-state and alarm "
                    "observation at the local interface without changing equipment state."
                ),
                requires_shutdown=False,
                requires_approval=False,
            )
        )
    if "sensor_history" in categories:
        actions.append(
            RecommendedAction(
                step=2,
                action=(
                    "Compare the grounded sensor history with approved tenant-scoped operating "
                    "limits and instrument-quality checks before drawing a conclusion."
                ),
                requires_shutdown=False,
                requires_approval=False,
            )
        )
    if "manual" in categories:
        actions.append(
            RecommendedAction(
                step=2,
                action=(
                    "Review the cited tenant-scoped manual sections and site procedure before "
                    "selecting an inspection method."
                ),
                requires_shutdown=False,
                requires_approval=False,
            )
        )
    if "incident_history" in categories:
        actions.append(
            RecommendedAction(
                step=2,
                action=(
                    "Compare the cited historical incident records with current symptoms; do "
                    "not assume the same cause without on-site verification."
                ),
                requires_shutdown=False,
                requires_approval=False,
            )
        )
    actions.append(
        RecommendedAction(
            step=2,
            action=(
                "Have a qualified person inspect the de-energized motor, guards, and accessible "
                "connections under the applicable site procedure."
            ),
            # The invariant below also infers this from the invasive action text.
            requires_shutdown=False,
            requires_approval=False,
        )
    )
    actions.append(
        RecommendedAction(
            step=2,
            action=(
                "After a qualified person reviews the evidence and proposed scope, offer to "
                "prepare a draft work order. No work order is created without a separate "
                "explicit confirmation."
            ),
            requires_shutdown=False,
            requires_approval=True,
        )
    )
    return actions


def _evidence_category(observation: Observation) -> str | None:
    reference = observation.source_reference
    if reference.startswith("tool:get_machine_status:"):
        return "machine_status"
    if reference.startswith("tool:get_sensor_history:"):
        return "sensor_history"
    if observation.source_type == SourceType.MANUAL:
        return "manual"
    if observation.source_type == SourceType.INCIDENT_HISTORY:
        return "incident_history"
    return None


def _bounded_hypotheses(evidence: Sequence[Observation]) -> list[PossibleCause]:
    categories: dict[str, list[str]] = {}
    for observation in evidence:
        category = _evidence_category(observation)
        if category is None:
            continue
        categories.setdefault(category, []).append(observation.source_reference)

    templates = {
        "machine_status": (
            "The recorded machine state or alarm may be relevant to the reported symptom."
        ),
        "sensor_history": (
            "A condition reflected in the retrieved sensor history may be relevant to the "
            "reported symptom."
        ),
        "manual": "A condition covered by the retrieved manual material may be relevant.",
        "incident_history": (
            "A condition similar to a retrieved historical incident may be relevant."
        ),
    }
    hypotheses = []
    for category in ("machine_status", "sensor_history", "manual", "incident_history"):
        references = categories.get(category)
        if not references:
            continue
        cited = ", ".join(references[:3])
        hypotheses.append(
            PossibleCause(
                cause=f"Unconfirmed hypothesis: {templates[category]}",
                confidence=Confidence.LOW,
                reasoning_summary=(
                    f"This hypothesis is bounded to grounded source(s) {cited}; the sources do "
                    "not by themselves establish causation."
                )[:1000],
            )
        )
    if hypotheses:
        return hypotheses
    return [
        PossibleCause(
            cause="Unconfirmed hypothesis: the cause remains undetermined.",
            confidence=Confidence.LOW,
            reasoning_summary=(
                "No successful external evidence established a cause; collect tenant-scoped "
                "evidence and have a qualified person inspect the equipment."
            ),
        )
    ]


def _observation(
    statement: str,
    source_type: SourceType,
    source_reference: str,
) -> Observation | None:
    if not source_reference or len(source_reference) > 500:
        return None
    normalized = " ".join(statement.split())[:1000]
    if not normalized:
        return None
    return Observation(
        statement=normalized,
        source_type=source_type,
        source_reference=source_reference,
    )


def _fragment(value: object, *, maximum: int = 120) -> str:
    return " ".join(str(value).split())[:maximum]


def _quoted(value: object) -> str:
    return f"'{_fragment(value)}'"


def _number(value: float) -> str:
    return f"{value:g}"


def _is_unsafe_action(text: str) -> bool:
    return bool(
        _SAFETY_DEFEAT_ACTION.search(text)
        or _MACHINE_CONTROL_ACTION.search(text)
        or _LIVE_ELECTRICAL_ACTION.search(text)
    )


def _is_invasive(text: str) -> bool:
    return bool(_INVASIVE_ACTION.search(text))


def _append_missing_information(diagnostic: DiagnosticResult, message: str) -> None:
    if len(diagnostic.missing_information) < 20:
        diagnostic.missing_information.append(message)
    else:
        diagnostic.missing_information[-1] = message
