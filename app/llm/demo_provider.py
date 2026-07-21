"""Deterministic offline provider for demos and tests.

The provider deliberately uses small, explainable request-parsing rules.  It exercises the
same native tool/approval/telemetry path as the OpenAI adapter, but never presents fixture
knowledge as if it came from a model or a live machine.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from app.llm.base import (
    ProviderRequest,
    ProviderResponse,
    ProviderToolCall,
    ProviderUsage,
)
from app.schemas.diagnostic import (
    Confidence,
    DiagnosticResult,
    Observation,
    PossibleCause,
    RecommendedAction,
    SourceType,
)

_MODEL_MACHINES = {
    "SP-400": "A1",
    "CP-200": "A2",
    "CV-120": "B1",
    "CNC-500": "B2",
}
_TRUSTED_TENANT_MACHINES = {
    "company-a": frozenset({"A1", "A2"}),
    "company-b": frozenset({"B1", "B2"}),
}
_DEFAULT_METRICS_BY_MODEL = {
    "SP-400": "servo_motor_current_rms",
    "CP-200": "vibration_rms",
    "CV-120": "belt_tracking_offset",
    "CNC-500": "spindle_vibration_rms",
}
_KNOWN_METRICS_BY_MODEL = {
    "SP-400": {"servo_motor_current_rms", "servo_drive_temperature"},
    "CP-200": {"vibration_rms", "suction_pressure"},
    "CV-120": {"belt_tracking_offset", "belt_speed"},
    "CNC-500": {"spindle_vibration_rms", "spindle_temperature"},
}
_METRIC_LABELS = {
    "servo_motor_current_rms": "motor current",
    "servo_drive_temperature": "servo-drive temperature",
    "vibration_rms": "vibration",
    "suction_pressure": "suction pressure",
    "belt_tracking_offset": "belt tracking offset",
    "belt_speed": "belt speed",
    "spindle_vibration_rms": "spindle vibration",
    "spindle_temperature": "spindle temperature",
    "acoustic_emission": "acoustic emission",
    "spindle_load": "spindle load",
}

# The synthetic corpus is timestamped around this instant.  A fixed clock keeps the offline
# demo reproducible and prevents a "recent" query from silently drifting as fixtures age.
_DEMO_NOW = datetime(2026, 7, 21, 10, 15, tzinfo=UTC)


class DemoProvider:
    """A conservative, deterministic substitute for a hosted language model."""

    name = "demo"

    async def generate(self, request: ProviderRequest) -> ProviderResponse:
        request_id = f"demo-{uuid4()}"
        outputs = [
            item for item in request.input_items if item.get("type") == "function_call_output"
        ]
        message = self._current_user_text(request.input_items)
        machine_id = self._resolve_machine(
            request.input_items, trusted_tenant_id=request.trusted_tenant_id
        )
        called_names = self._called_tool_names(request.input_items)

        if machine_id is None:
            return self._diagnostic_response(
                request_id=request_id,
                request=request,
                diagnostic=self._clarification_diagnostic(message),
                terminal_status="needs_clarification",
            )

        status_data = self._successful_tool_data(outputs, "get_machine_status")
        # Once a status lookup has failed, stop. Continuing could derive or expose metadata
        # for a machine outside the authenticated tenant.
        if "get_machine_status" not in called_names or status_data is not None:
            calls = self._choose_tools(
                message,
                machine_id,
                status_data=status_data,
                called_names=called_names,
            )
            if calls:
                return self._tool_call_response(request_id=request_id, request=request, calls=calls)

        if not outputs:
            return self._diagnostic_response(
                request_id=request_id,
                request=request,
                diagnostic=self._no_tool_diagnostic(message, machine_id),
            )

        diagnostic, terminal_status = self._build_diagnostic(
            request.input_items,
            message=self._assessment_text(request.input_items),
            machine_id=machine_id,
        )
        return self._diagnostic_response(
            request_id=request_id,
            request=request,
            diagnostic=diagnostic,
            terminal_status=terminal_status,
        )

    def _tool_call_response(
        self,
        *,
        request_id: str,
        request: ProviderRequest,
        calls: list[ProviderToolCall],
    ) -> ProviderResponse:
        output_items = [
            {
                "type": "function_call",
                "call_id": call.call_id,
                "name": call.name,
                "arguments": call.arguments,
            }
            for call in calls
        ]
        return ProviderResponse(
            request_id=request_id,
            output_text="",
            tool_calls=calls,
            output_items=output_items,
            usage=self._usage(request, output_items),
        )

    @staticmethod
    def _called_tool_names(items: list[dict[str, Any]]) -> set[str]:
        names = {
            str(item.get("name"))
            for item in items
            if item.get("type") == "function_call" and item.get("name")
        }
        for item in items:
            if item.get("type") != "function_call_output":
                continue
            try:
                payload = json.loads(str(item.get("output", "{}")))
            except (json.JSONDecodeError, TypeError):
                continue
            result = payload.get("tool_result", payload)
            if result.get("tool_name"):
                names.add(str(result["tool_name"]))
        return names

    @staticmethod
    def _successful_tool_data(
        outputs: list[dict[str, Any]], tool_name: str
    ) -> dict[str, Any] | None:
        for item in reversed(outputs):
            try:
                payload = json.loads(str(item.get("output", "{}")))
            except (json.JSONDecodeError, TypeError):
                continue
            result = payload.get("tool_result", payload)
            if result.get("tool_name") == tool_name and result.get("ok"):
                data = result.get("data")
                return data if isinstance(data, dict) else None
        return None

    def _diagnostic_response(
        self,
        *,
        request_id: str,
        request: ProviderRequest,
        diagnostic: DiagnosticResult,
        terminal_status: str = "completed",
    ) -> ProviderResponse:
        output_text = diagnostic.model_dump_json()
        message_item = {
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": output_text}],
        }
        return ProviderResponse(
            request_id=request_id,
            output_text=output_text,
            tool_calls=[],
            output_items=[message_item],
            usage=self._usage(request, [message_item]),
            metadata={"terminal_status": terminal_status},
        )

    @staticmethod
    def _current_user_text(items: list[dict[str, Any]]) -> str:
        messages = [str(item.get("content", "")) for item in items if item.get("role") == "user"]
        return messages[-1] if messages else ""

    @classmethod
    def _assessment_text(cls, items: list[dict[str, Any]]) -> str:
        """Include a few relevant recent turns only when the user explicitly refers to them."""

        current = cls._current_user_text(items)
        if not re.search(
            r"(?i)\b(conversation|current incident|relevant recent context|as (?:we|I) "
            r"(?:said|reported)|above)\b",
            current,
        ):
            return current
        prior = [
            str(item.get("content", ""))
            for item in items
            if item.get("role") in {"user", "assistant"}
        ][:-1]
        relevant = [
            content[:2000]
            for content in reversed(prior)
            if re.search(
                r"(?i)\b(rough|alarm|stopped|vibration|overload|tracking|noise|"
                r"temperature|pressure|changeover|A1|A2|B1|B2)\b",
                content,
            )
        ][:3]
        return "\n".join([current, *reversed(relevant)])

    @classmethod
    def _resolve_machine(
        cls,
        items: list[dict[str, Any]],
        *,
        trusted_tenant_id: str | None,
    ) -> str | None:
        """Resolve an explicit asset without guessing from a line or tenant prefix."""

        message = cls._current_user_text(items)
        current_ids = cls._machine_ids(message)
        if len(current_ids) == 1:
            return next(iter(current_ids))
        if len(current_ids) > 1:
            return None

        upper_message = message.upper()
        model_ids = {
            machine
            for model, machine in _MODEL_MACHINES.items()
            if re.search(rf"\b{re.escape(model)}\b", upper_message)
            and cls._trusted_alias(machine, trusted_tenant_id)
        }
        if len(model_ids) == 1:
            return next(iter(model_ids))

        descriptor_ids = {
            machine
            for pattern, machine in (
                (r"(?i)\bservo press\b", "A1"),
                (r"(?i)\bcooling pump\b", "A2"),
                (r"(?i)\bpackaging conveyor\b", "B1"),
                (r"(?i)\b(?:finish mill|machining cent(?:er|re))\b", "B2"),
            )
            if re.search(pattern, message) and cls._trusted_alias(machine, trusted_tenant_id)
        }
        if len(descriptor_ids) == 1:
            return next(iter(descriptor_ids))

        # A message that explicitly refers back to supplied history may use its most recent
        # unambiguous asset.  Generic statements such as "the machine" never trigger this.
        refers_to_context = re.search(
            r"(?i)\b(based on (?:the )?conversation|current incident|"
            r"relevant recent context|as (?:we|I) (?:said|reported)|above)\b",
            message,
        )
        if not refers_to_context:
            return None
        prior_messages = [
            str(item.get("content", ""))
            for item in items
            if item.get("role") in {"user", "assistant"}
        ][:-1]
        for prior in reversed(prior_messages):
            identifiers = cls._machine_ids(prior)
            if len(identifiers) == 1:
                return next(iter(identifiers))
        return None

    @staticmethod
    def _trusted_alias(machine_id: str, trusted_tenant_id: str | None) -> bool:
        return machine_id in _TRUSTED_TENANT_MACHINES.get(trusted_tenant_id or "", ())

    @staticmethod
    def _machine_ids(value: str) -> set[str]:
        return {
            match.upper()
            for match in re.findall(r"(?i)(?<![A-Z0-9])(?:A1|A2|B1|B2)(?![A-Z0-9])", value)
        }

    def _choose_tools(
        self,
        message: str,
        machine_id: str,
        *,
        status_data: dict[str, Any] | None,
        called_names: set[str],
    ) -> list[ProviderToolCall]:
        lower = message.lower()

        def call(name: str, args: dict[str, Any]) -> ProviderToolCall:
            return ProviderToolCall(
                call_id=f"call-{uuid4()}", name=name, arguments=json.dumps(args)
            )

        if self._direct_work_order_request(message) and "create_work_order" not in called_names:
            return [call("create_work_order", self._work_order_arguments(message, machine_id))]

        if re.search(r"\b(downtime|lost production|production loss)\b", lower) and re.search(
            r"\b(cost|value|dollars?|usd|estimate)\b", lower
        ):
            minutes = self._duration_minutes(message)
            if minutes is not None and "calculate_downtime_cost" not in called_names:
                return [
                    call(
                        "calculate_downtime_cost",
                        {"machine_id": machine_id, "downtime_minutes": minutes},
                    )
                ]

        requested_metric = self._requested_metric(
            message, model=str(status_data.get("model")) if status_data else None
        )
        explicit_sensor = requested_metric is not None or re.search(
            r"(?i)\b(sensors?|telemetry|readings?|trend|history)\b", message
        )
        if re.search(r"(?i)\bsummar\w*\b.{0,40}\bcurrent condition\b", message):
            explicit_sensor = True
        broad_diagnosis = re.search(
            r"(?i)\b(diagnos\w*|likely (?:issue|cause)|what (?:failed|should I check)|"
            r"preliminary diagnosis)\b",
            message,
        ) or (
            re.search(r"(?i)\bstopped\b", message)
            and re.search(r"(?i)\b(alarm|overload|changeover|fault)\b", message)
        )
        code_lookup = re.search(
            r"(?i)\b(what does (?:that|this|the) code mean|explain\w*|confirm it|"
            r"use (?:that|this) code)\b",
            message,
        )
        incident_intent = re.search(
            r"(?i)\b(incident|similar|histor(?:y|ical)|prior (?:note|record)|"
            r"old (?:note|record)|benchmark)\w*\b",
            message,
        )
        manual_intent = re.search(
            r"(?i)\b(manuals?|procedure|guidance|alarm code|prompt injection|"
            r"what does .+ code mean)\b",
            message,
        )
        status_intent = re.search(
            r"(?i)\b(live state|live status|current (?:state|status|condition)|"
            r"status|confirm its live|shows?|displayed|has .{0,16}(?:alarm|E\d{3}|"
            r"[A-Z]{2,5}-\d{1,3}|VIB-HI)|running|stopped)\b",
            message,
        )

        # Explicit, narrow requests remain narrow.  A broad diagnosis uses complementary
        # current, trend, manual, and history evidence, capped at four calls.
        if broad_diagnosis and not code_lookup:
            want_status = True
            want_sensor = True
            want_manual = True
            want_incidents = True
        else:
            want_status = bool(status_intent or code_lookup)
            want_sensor = bool(explicit_sensor)
            want_manual = bool(manual_intent or code_lookup)
            want_incidents = bool(incident_intent)

        # A sensor series is more useful and safer when paired with the machine's current
        # state/alarm.  This adds no extra evidence source when no sensor lookup was requested.
        if want_sensor:
            want_status = True

        if want_incidents and re.search(r"(?i)\b(find similar|tracking incidents)\b", message):
            want_status = True
        if re.search(r"(?i)\b(all incidents|benchmark)\b", message):
            want_status = False
        if re.search(r"(?i)\b(can it keep running|definitely the cause|reset)\b", message):
            want_manual = True
            want_incidents = True
        if re.search(r"(?i)\breset\b", message):
            want_status = True
        if re.search(r"(?i)\b(check|use|retrieve).{0,30}\bmanual\b", message):
            want_manual = True

        # Any request that could expose model-specific or default-metric metadata must first
        # prove that the machine is visible in the authoritative tenant scope.
        if (want_status or want_sensor or want_manual) and "get_machine_status" not in called_names:
            return [call("get_machine_status", {"machine_id": machine_id})]
        if (want_status or want_sensor or want_manual) and status_data is None:
            return []

        model = str(status_data.get("model")) if status_data else None
        metric = requested_metric
        if metric is None and want_sensor and model:
            metric = _DEFAULT_METRICS_BY_MODEL.get(model)

        calls: list[ProviderToolCall] = []
        if want_sensor and metric is not None and "get_sensor_history" not in called_names:
            start, end = self._sensor_window(message)
            calls.append(
                call(
                    "get_sensor_history",
                    {
                        "machine_id": machine_id,
                        "metric": metric,
                        "start_time": start.isoformat().replace("+00:00", "Z"),
                        "end_time": end.isoformat().replace("+00:00", "Z"),
                    },
                )
            )
        if want_manual and model and "search_manual" not in called_names:
            calls.append(
                call(
                    "search_manual",
                    {"query": message[:500], "machine_model": model},
                )
            )
        if want_incidents and "search_incident_history" not in called_names:
            calls.append(
                call(
                    "search_incident_history",
                    {"query": message[:500], "machine_id": machine_id},
                )
            )
        return calls

    @staticmethod
    def _direct_work_order_request(message: str) -> bool:
        return bool(
            re.search(
                r"(?is)\b(create|open|draft|prepare|make|submit|generate)\b"
                r".{0,80}\bwork[ -]?order\b",
                message,
            )
        )

    @staticmethod
    def _work_order_arguments(message: str, machine_id: str) -> dict[str, Any]:
        priority_match = re.search(r"(?i)\b(critical|high|medium|low)(?:-priority)?\b", message)
        priority = priority_match.group(1).lower() if priority_match else "medium"
        title_match = re.search(
            r"(?is)\btitled?\s+(.+?)(?=\s*,?\s*(?:with\s+)?description\b|[.;]|$)",
            message,
        )
        description_match = re.search(r"(?is)\bdescription\s+(.+?)(?=[.;]\s*$|$)", message)
        subject_match = re.search(
            r"(?is)\bwork[ -]?order\s+(?:for\s+)?(.+?)"
            r"(?=\s+and\s+skip\b|\s*,?\s*(?:with\s+)?description\b|[.;]|$)",
            message,
        )
        subject = subject_match.group(1).strip() if subject_match else "reported issue"
        subject = re.sub(rf"(?i)^(?:for\s+)?{re.escape(machine_id)}\s*", "", subject)
        subject = re.sub(
            r"(?i)^(?:a\s+)?(?:critical|high|medium|low)(?:-priority)?\s+", "", subject
        )
        title = title_match.group(1).strip(" ,") if title_match else subject.capitalize()
        if len(title) < 3:
            title = f"Inspect {machine_id}"
        description = (
            description_match.group(1).strip(" ,")
            if description_match
            else f"Inspect {machine_id} {subject.lower()} fault"
        )
        return {
            "machine_id": machine_id,
            "title": title[:250],
            "description": description[:4000],
            "priority": priority,
        }

    @staticmethod
    def _duration_minutes(message: str) -> int | None:
        match = re.search(r"(?i)\b(\d+)\s*(minutes?|mins?|hours?|hrs?|days?)\b", message)
        if not match:
            return None
        value = int(match.group(1))
        unit = match.group(2).lower()
        if unit.startswith(("hour", "hr")):
            value *= 60
        elif unit.startswith("day"):
            value *= 24 * 60
        return value if 0 < value <= 31 * 24 * 60 else None

    @staticmethod
    def _requested_metric(message: str, *, model: str | None) -> str | None:
        lower = message.lower().replace("-", " ").replace("_", " ")
        patterns = (
            (r"\bacoustic emission\b", "acoustic_emission"),
            (r"\bspindle load\b", "spindle_load"),
            (r"\b(?:servo(?: motor)?|motor) current\b", "servo_motor_current_rms"),
            (r"\bsuction pressure\b", "suction_pressure"),
            (r"\bbelt speed\b", "belt_speed"),
            (r"\b(?:belt )?tracking (?:offset|deviation)\b", "belt_tracking_offset"),
            (r"\bspindle temperature\b", "spindle_temperature"),
            (r"\b(?:servo|drive) temperature\b", "servo_drive_temperature"),
            (r"\bspindle vibration(?: rms)?\b", "spindle_vibration_rms"),
            (
                r"\bvibration(?: rms)?\b",
                "spindle_vibration_rms" if model == "CNC-500" else "vibration_rms",
            ),
        )
        for pattern, metric in patterns:
            if re.search(pattern, lower):
                return metric
        if re.search(r"\b\d+(?:\.\d+)?\s*mm/s\b", lower):
            return "spindle_vibration_rms" if model == "CNC-500" else "vibration_rms"
        return None

    @staticmethod
    def _sensor_window(message: str) -> tuple[datetime, datetime]:
        between = re.search(
            r"(?i)\bbetween\s+(\d{1,2}):(\d{2})\s+and\s+"
            r"(\d{1,2}):(\d{2})(?:\s+UTC)?\b",
            message,
        )
        if between:
            start = _DEMO_NOW.replace(
                hour=int(between.group(1)), minute=int(between.group(2)), second=0
            )
            end = _DEMO_NOW.replace(
                hour=int(between.group(3)), minute=int(between.group(4)), second=0
            )
            if end > start:
                return start, end

        if re.search(r"(?i)\bfrom midnight\b", message):
            return _DEMO_NOW.replace(hour=0, minute=0, second=0), _DEMO_NOW
        if re.search(r"(?i)\btoday\b", message):
            return _DEMO_NOW.replace(hour=0, minute=0, second=0), _DEMO_NOW.replace(
                hour=23, minute=59, second=59
            )

        recent = re.search(
            r"(?i)\blast\s+(?:(\d+|an?|one)\s+)?"
            r"(minutes?|mins?|hours?|hrs?|days?)\b",
            message,
        )
        if recent:
            amount_text = recent.group(1)
            amount = int(amount_text) if amount_text and amount_text.isdigit() else 1
            unit = recent.group(2).lower()
            delta = (
                timedelta(hours=amount)
                if unit.startswith(("hour", "hr"))
                else timedelta(days=amount)
                if unit.startswith("day")
                else timedelta(minutes=amount)
            )
            if delta <= timedelta(days=31):
                return _DEMO_NOW - delta, _DEMO_NOW

        return _DEMO_NOW - timedelta(hours=25), _DEMO_NOW

    @staticmethod
    def _clarification_diagnostic(message: str) -> DiagnosticResult:
        return DiagnosticResult(
            incident_summary=(
                "The affected equipment cannot be identified reliably from the request."
            ),
            observations=[],
            possible_causes=[
                PossibleCause(
                    cause="Cause cannot be assessed until the asset is identified",
                    confidence=Confidence.LOW,
                    reasoning_summary=(
                        "No machine-specific records were queried because selecting an asset "
                        "without an explicit identifier could mix unrelated evidence."
                    ),
                )
            ],
            recommended_actions=[
                RecommendedAction(
                    step=1,
                    action=(
                        "Keep personnel clear of the equipment and follow the site's safe-stop "
                        "procedure if abnormal noise, heat, motion, or another hazard is present."
                    ),
                    requires_shutdown=False,
                    requires_approval=False,
                )
            ],
            missing_information=[
                "Please identify which machine using its machine ID or asset tag; also provide "
                "its location or model if the identifier is unavailable."
            ],
            safety_notice=(
                "No machine was assumed and no tools were called. This is preliminary decision "
                "support only; follow site procedures and use qualified personnel."
            ),
        )

    @staticmethod
    def _no_tool_diagnostic(message: str, machine_id: str) -> DiagnosticResult:
        return DiagnosticResult(
            incident_summary=f"No authoritative lookup was requested for {machine_id}.",
            observations=[],
            possible_causes=[
                PossibleCause(
                    cause="No equipment condition was established",
                    confidence=Confidence.LOW,
                    reasoning_summary="The request did not identify evidence to retrieve.",
                )
            ],
            recommended_actions=[
                RecommendedAction(
                    step=1,
                    action="Provide the observed condition, alarm, metric, or lookup needed.",
                    requires_shutdown=False,
                    requires_approval=False,
                )
            ],
            missing_information=[
                "Clarify what status, sensor, manual, incident, or cost evidence is needed "
                f"for {machine_id}."
            ],
            safety_notice=(
                "Do not treat this response as a condition assessment or permission to operate."
            ),
        )

    @classmethod
    def _build_diagnostic(
        cls,
        items: list[dict[str, Any]],
        *,
        message: str,
        machine_id: str | None,
    ) -> tuple[DiagnosticResult, str]:
        observations: list[Observation] = []
        causes: list[PossibleCause] = []
        missing: list[str] = []
        status_data: dict[str, Any] | None = None
        sensor_results: list[dict[str, Any]] = []
        manual_matches: list[dict[str, Any]] = []
        incident_matches: list[dict[str, Any]] = []
        errors: list[tuple[str, str]] = []

        for item in items:
            if item.get("type") != "function_call_output":
                continue
            try:
                payload = json.loads(str(item.get("output", "{}")))
            except (json.JSONDecodeError, TypeError):
                missing.append("A tool returned an unreadable result; no claim was based on it.")
                errors.append(("unknown", "invalid_result"))
                continue
            envelope = payload.get("tool_result", payload)
            name = str(envelope.get("tool_name") or "unknown")
            if not envelope.get("ok"):
                category = str((envelope.get("error") or {}).get("category", "unknown"))
                errors.append((name, category))
                missing.append(cls._tool_error_disclosure(name, category))
                continue
            data = envelope.get("data") or {}
            if name == "get_machine_status":
                status_data = data
                alarm = data.get("alarm_code") or "no active alarm code"
                observations.append(
                    Observation(
                        statement=(
                            f"{data.get('machine_id')} is recorded as {data.get('status')} "
                            f"with {alarm}."
                        ),
                        source_type=SourceType.TOOL,
                        source_reference=data["source_reference"],
                    )
                )
            elif name == "get_sensor_history":
                sensor_results.append(data)
                cls._add_sensor_evidence(data, observations, missing)
            elif name == "search_manual":
                matches = list(data.get("matches") or [])
                manual_matches.extend(matches)
                if not matches:
                    missing.append("No relevant manual section was found for the request.")
                for match in matches[:2]:
                    observations.append(
                        Observation(
                            statement=f"Relevant manual section retrieved: {match['section']}.",
                            source_type=SourceType.MANUAL,
                            source_reference=match["source_reference"],
                        )
                    )
            elif name == "search_incident_history":
                matches = list(data.get("matches") or [])
                incident_matches.extend(matches)
                if not matches:
                    missing.append("No related incident history was found for this machine.")
                for match in matches[:2]:
                    observations.append(
                        Observation(
                            statement=f"Related historical incident retrieved: {match['title']}.",
                            source_type=SourceType.INCIDENT_HISTORY,
                            source_reference=match["source_reference"],
                        )
                    )
            elif name == "calculate_downtime_cost":
                observations.append(
                    Observation(
                        statement=(
                            f"Configured downtime estimate for {data.get('downtime_minutes')} "
                            f"minutes is {data.get('estimated_cost')} {data.get('currency')}."
                        ),
                        source_type=SourceType.TOOL,
                        source_reference=data["source_reference"],
                    )
                )

        cls._add_alarm_assessment(message, status_data, manual_matches, causes, missing)
        cls._add_conflict_assessment(
            message,
            status_data=status_data,
            sensor_results=sensor_results,
            manual_matches=manual_matches,
            incident_matches=incident_matches,
            causes=causes,
            missing=missing,
        )

        if not causes:
            causes.append(
                PossibleCause(
                    cause="Cause not yet confirmed",
                    confidence=Confidence.LOW,
                    reasoning_summary=(
                        "The available records narrow the next checks but do not replace a "
                        "qualified physical inspection and time-aligned evidence."
                    ),
                )
            )

        terminal_status = cls._terminal_status(
            status_data=status_data, sensor_results=sensor_results, errors=errors
        )
        diagnostic = DiagnosticResult(
            incident_summary=(
                f"Preliminary evidence review for {machine_id}."
                if machine_id
                else "Preliminary evidence review of the reported incident."
            ),
            observations=observations,
            possible_causes=causes,
            recommended_actions=cls._recommended_actions(
                status_data=status_data, has_errors=bool(errors)
            ),
            missing_information=cls._deduplicate(missing)[:20],
            safety_notice=(
                "Preliminary decision support only. Do not bypass interlocks or energize, "
                "reset, or operate equipment unless authorized site procedures and a qualified "
                "person permit it. This system cannot control machinery."
            ),
        )
        return diagnostic, terminal_status

    @staticmethod
    def _tool_error_disclosure(name: str, category: str) -> str:
        if category in {"not_found", "tenant_access_denied"}:
            return (
                "The requested resource was unavailable within the authenticated tenant scope; "
                "no status, sensor, manual, or incident fact was inferred from that failure."
            )
        if category == "invalid_arguments":
            return (
                f"The {name} request was rejected as invalid; the requested evidence "
                "is unavailable."
            )
        if category == "timeout":
            return f"The {name} request timed out; its current evidence remains unconfirmed."
        return f"The {name} evidence source was unavailable ({category}); no result was assumed."

    @staticmethod
    def _add_sensor_evidence(
        data: dict[str, Any], observations: list[Observation], missing: list[str]
    ) -> None:
        metric = str(data.get("metric") or "requested metric")
        label = _METRIC_LABELS.get(metric, metric.replace("_", " "))
        readings = list(data.get("readings") or [])
        numeric = [float(point["value"]) for point in readings if point.get("value") is not None]
        if not readings or not numeric:
            unavailable = (
                f"{label.capitalize()} is unavailable"
                if metric == "acoustic_emission"
                else f"{label.capitalize()} history unavailable"
            )
            missing.append(
                f"{unavailable}: no numeric {metric} readings were found in the requested range."
            )
            return

        unit = next((str(point.get("unit") or "") for point in readings), "")
        low, high = min(numeric), max(numeric)
        observations.append(
            Observation(
                statement=(
                    f"The retrieved {metric} series has {len(numeric)} numeric points "
                    f"ranging from {low:g} to {high:g} {unit}."
                ),
                source_type=SourceType.TOOL,
                source_reference=data["source_reference"],
            )
        )
        incomplete = not bool(data.get("data_complete", False))
        suspect = sum(
            point.get("value") is None or point.get("quality") in {"missing", "suspect"}
            for point in readings
        )
        if incomplete or suspect:
            missing.append(
                f"The {label} history is incomplete or contains {suspect} missing/suspect "
                "sample(s); continuous behavior cannot be confirmed or interpolated."
            )

    @classmethod
    def _add_alarm_assessment(
        cls,
        message: str,
        status_data: dict[str, Any] | None,
        manual_matches: list[dict[str, Any]],
        causes: list[PossibleCause],
        missing: list[str],
    ) -> None:
        reported_codes = cls._alarm_codes(message)
        observed = str((status_data or {}).get("alarm_code") or "").upper()
        if not reported_codes:
            if observed:
                causes.append(
                    PossibleCause(
                        cause="Condition associated with the recorded alarm",
                        confidence=Confidence.MEDIUM,
                        reasoning_summary=(
                            f"The current record contains {observed}, but the code alone does "
                            "not establish the physical root cause."
                        ),
                    )
                )
            return

        if not status_data:
            missing.append(
                "The user-reported alarm could not be compared with an authoritative "
                "current status."
            )
            return

        mismatches = sorted(code for code in reported_codes if code != observed)
        if mismatches:
            missing.append(
                "Alarm mismatch: the request reports "
                f"{', '.join(mismatches)}, while current status reports "
                f"{observed or 'no active alarm'}. The reported code was not treated as verified."
            )
            causes.append(
                PossibleCause(
                    cause="Reported alarm identity is unconfirmed",
                    confidence=Confidence.LOW,
                    reasoning_summary=(
                        "The reported and current alarm records do not match, so neither code "
                        "should be used to assert a cause without timestamp and HMI verification."
                    ),
                )
            )
            return

        manual_text = " ".join(str(match.get("excerpt") or "") for match in manual_matches).upper()
        code = next(iter(reported_codes))
        if manual_matches and code not in manual_text:
            missing.append(
                f"Alarm mapping mismatch: retrieved guidance does not define {code} for this "
                "model; verify the exact HMI code and equipment model."
            )
        elif re.search(r"(?i)\b(confirm|definitely|so the)\b", message):
            missing.append(
                f"No alarm-code mismatch was observed for {code}, but agreement confirms only "
                "the recorded code, not the asserted root cause."
            )
        causes.append(
            PossibleCause(
                cause=f"Condition associated with recorded alarm {code}",
                confidence=Confidence.MEDIUM,
                reasoning_summary=(
                    "Status corroborates the alarm identity, while manual guidance describes "
                    "multiple plausible contributors rather than a confirmed cause."
                ),
            )
        )

    @staticmethod
    def _alarm_codes(message: str) -> set[str]:
        # Conversation/source labels such as ``[conversation:item-298]`` are provenance,
        # not equipment alarm codes.
        message = re.sub(r"\[[^\]]+\]", " ", message)
        values = {
            item.upper()
            for item in re.findall(
                r"(?i)\b(?:[A-Z]\d{3}|[A-Z]{2,5}-(?:[A-Z]{2,4}|\d{1,3}))\b", message
            )
        }
        return values - set(_MODEL_MACHINES)

    @staticmethod
    def _add_conflict_assessment(
        message: str,
        *,
        status_data: dict[str, Any] | None,
        sensor_results: list[dict[str, Any]],
        manual_matches: list[dict[str, Any]],
        incident_matches: list[dict[str, Any]],
        causes: list[PossibleCause],
        missing: list[str],
    ) -> None:
        decision_or_history = re.search(
            r"(?i)\b(prior|old|incident|note|definitely|keep running|reset|acceptable)\b",
            message,
        )
        if manual_matches and incident_matches and decision_or_history:
            missing.append(
                "Potential evidence conflict: manual guidance and incident history serve "
                "different purposes and may disagree; a prior outcome is not current policy or "
                "proof of the present cause."
            )
            causes.append(
                PossibleCause(
                    cause="Conflicting or non-equivalent evidence",
                    confidence=Confidence.LOW,
                    reasoning_summary=(
                        "The current status/trend, current manual, and historical incident must "
                        "be reconciled by timestamp and condition before deciding a cause or "
                        "restart."
                    ),
                )
            )

        reported_measurement = re.search(r"\b(\d+(?:\.\d+)?)\s*mm/s\b", message, re.I)
        if reported_measurement and sensor_results:
            values = [
                float(point["value"])
                for result in sensor_results
                for point in result.get("readings", [])
                if point.get("value") is not None
            ]
            reported = float(reported_measurement.group(1))
            if values and all(abs(reported - value) > 1e-6 for value in values):
                missing.append(
                    "Measurement conflict: the user-reported value is not present in the "
                    "retrieved series; confirm its timestamp, source, and unit before using it."
                )

        if re.search(r"(?i)\brough finish\b", message):
            missing.append(
                "Rough finish cause unconfirmed: tooling, process, workholding, and time-aligned "
                "spindle evidence have not all been inspected."
            )
        if re.search(r"(?i)\bdefinitely\b.{0,30}\b(?:sensor|cause)\b", message):
            missing.append(
                "Tension sensor cause not confirmed: the alarm, manual, and incident "
                "history do not establish one definite physical cause."
            )
        if (
            status_data
            and not status_data.get("alarm_code")
            and re.search(r"(?i)\b(?:no|without an?) alarm\b", message)
        ):
            missing.append(
                "No active alarm is recorded, but that does not establish that the machine "
                "is fault-free."
            )

    @staticmethod
    def _terminal_status(
        *,
        status_data: dict[str, Any] | None,
        sensor_results: list[dict[str, Any]],
        errors: list[tuple[str, str]],
    ) -> str:
        if any(category == "tenant_access_denied" for _, category in errors):
            return "access_denied"
        if errors:
            return "failed"
        model = str(status_data.get("model")) if status_data else None
        for result in sensor_results:
            metric = str(result.get("metric") or "")
            readings = result.get("readings") or []
            if model and metric not in _KNOWN_METRICS_BY_MODEL.get(model, set()) and not readings:
                return "failed"
        return "completed"

    @staticmethod
    def _recommended_actions(
        *, status_data: dict[str, Any] | None, has_errors: bool
    ) -> list[RecommendedAction]:
        alarm_or_stop = bool(
            status_data
            and (status_data.get("alarm_code") or status_data.get("status") == "stopped")
        )
        if alarm_or_stop:
            actions = [
                RecommendedAction(
                    step=1,
                    action=(
                        "Keep personnel clear. Before opening guards or touching the mechanism, "
                        "follow site lockout/tagout and verify the task-specific zero-energy state."
                    ),
                    requires_shutdown=True,
                    requires_approval=False,
                ),
                RecommendedAction(
                    step=2,
                    action=(
                        "Verify machine identity, local HMI state, alarm code, and event time "
                        "with an authorized operator without resetting the alarm."
                    ),
                    requires_shutdown=False,
                    requires_approval=False,
                ),
            ]
        else:
            actions = [
                RecommendedAction(
                    step=1,
                    action=(
                        "Keep personnel clear and verify machine identity, local HMI state, "
                        "alarm code, and event time with an authorized operator."
                    ),
                    requires_shutdown=False,
                    requires_approval=False,
                ),
                RecommendedAction(
                    step=2,
                    action=(
                        "Before opening guards or touching the mechanism, follow site "
                        "lockout/tagout and verify the task-specific zero-energy state."
                    ),
                    requires_shutdown=True,
                    requires_approval=False,
                ),
            ]
        if has_errors:
            actions.append(
                RecommendedAction(
                    step=3,
                    action=(
                        "Restore or validate the unavailable evidence source and repeat the "
                        "bounded lookup before drawing a stronger conclusion."
                    ),
                    requires_shutdown=False,
                    requires_approval=False,
                )
            )
        else:
            actions.append(
                RecommendedAction(
                    step=3,
                    action=(
                        "Have a qualified technician reconcile the cited records with a safe "
                        "physical inspection before restart or repair decisions."
                    ),
                    requires_shutdown=True,
                    requires_approval=False,
                )
            )
        actions.append(
            RecommendedAction(
                step=4,
                action="Create a draft work order only if on-site follow-up is requested.",
                requires_shutdown=False,
                requires_approval=True,
            )
        )
        return actions

    @staticmethod
    def _deduplicate(values: list[str]) -> list[str]:
        return list(dict.fromkeys(values))

    @staticmethod
    def _usage(request: ProviderRequest, output: list[dict[str, Any]]) -> ProviderUsage:
        input_chars = len(request.instructions) + len(json.dumps(request.input_items))
        output_chars = len(json.dumps(output))
        return ProviderUsage(
            input_tokens=max(1, input_chars // 4),
            output_tokens=max(1, output_chars // 4),
            cached_input_tokens=0,
            cache_write_tokens=0,
            estimated=True,
        )
