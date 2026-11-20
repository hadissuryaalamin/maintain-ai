"""Test-only tool boundary for deterministic end-to-end scenario evaluation.

The scenario backend keeps the production agent, HTTP routes, telemetry, approval gate,
tenant context, tool validation, and deterministic demo provider intact.  Only declared
tool outcomes are substituted, after the normal registry has validated model arguments.
Undeclared tools continue to use the production synthetic-data implementation so an
unexpected call remains observable and is never silently converted into a passing call.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.repositories import TenantAccessDenied
from app.llm.base import LLMProvider, ProviderRequest, ProviderResponse
from app.schemas.tools import (
    IncidentMatch,
    MachineStatusInput,
    MachineStatusOutput,
    ManualMatch,
    SearchIncidentHistoryInput,
    SearchIncidentHistoryOutput,
    SearchManualOutput,
    SensorHistoryInput,
    SensorHistoryOutput,
    SensorPoint,
)
from app.security.content import contains_likely_prompt_injection, delimit_untrusted_content
from app.security.context import AuthContext, log_security_event
from app.tools.base import ToolDefinition, TransientToolError
from app.tools.registry import (
    ToolInvocation,
    ToolRegistry,
    ToolRegistryFactory,
    build_tool_registry,
)

_FIXED_EVENT_TIME = datetime(2026, 7, 21, 9, 0, tzinfo=UTC)
_INJECTION_MARKERS = re.compile(
    r"(?i)(system\s+override|approval_token|skip\s+confirmation|"
    r"replace\s+tenant_id|outranks\s+application\s+policy)"
)


class RecordingProvider:
    """Capture provider requests for deterministic evaluator evidence."""

    def __init__(self, provider: LLMProvider) -> None:
        self.provider = provider
        self.name = provider.name
        self.requests: list[ProviderRequest] = []

    async def generate(self, request: ProviderRequest) -> ProviderResponse:
        self.requests.append(
            ProviderRequest(
                model=request.model,
                instructions=request.instructions,
                conversation=list(request.conversation),
                tools=deepcopy(request.tools),
                output_schema=deepcopy(request.output_schema),
                max_output_tokens=request.max_output_tokens,
                trusted_tenant_id=request.trusted_tenant_id,
            )
        )
        return await self.provider.generate(request)


class ScenarioRegistry(ToolRegistry):
    """A normal ToolRegistry that audits declared untrusted evidence retrieval."""

    def __init__(
        self,
        *,
        session: Session,
        context: AuthContext,
        definitions: list[ToolDefinition],
        documents_by_tool: dict[str, list[dict[str, Any]]],
        max_retries: int,
    ) -> None:
        super().__init__(
            session=session,
            context=context,
            definitions=definitions,
            max_retries=max_retries,
        )
        self._documents_by_tool = documents_by_tool
        self._logged_document_ids: set[str] = set()

    async def execute(
        self,
        *,
        name: str,
        arguments: dict[str, Any],
        run_id: str,
        approval_granted: bool = False,
        idempotency_key: str | None = None,
    ) -> ToolInvocation:
        invocation = await super().execute(
            name=name,
            arguments=arguments,
            run_id=run_id,
            approval_granted=approval_granted,
            idempotency_key=idempotency_key,
        )
        documents = self._documents_by_tool.get(name, [])
        if not invocation.result.ok or not documents:
            return invocation

        for document in documents:
            document_id = str(document["document_id"])
            content = str(document.get("content", ""))
            if document_id in self._logged_document_ids:
                continue
            if contains_likely_prompt_injection(content) or _INJECTION_MARKERS.search(content):
                log_security_event(
                    self.session,
                    context=self.context,
                    event_type="prompt_injection_content_retrieved",
                    target_type="evaluation_document",
                    target_id=document_id,
                    detail=(
                        "Scenario evaluation delivered a declared untrusted document "
                        "containing likely instruction-like content."
                    ),
                )
            self._logged_document_ids.add(document_id)
        return invocation


def build_scenario_registry_factory(case: dict[str, Any]) -> ToolRegistryFactory:
    """Build a per-case registry factory from the dataset's declared behavior contract."""

    behaviors = {
        str(item["tool"]): dict(item)
        for item in (case.get("fixture") or {}).get("tool_behaviors", [])
    }
    documents = [dict(item) for item in (case.get("fixture") or {}).get("retrieved_documents", [])]
    documents_by_tool = {
        tool_name: _documents_for_tool(tool_name, behavior, documents)
        for tool_name, behavior in behaviors.items()
    }

    def factory(session: Session, context: AuthContext, settings: Settings) -> ToolRegistry:
        production = build_tool_registry(session, context, settings)
        resolved_documents_by_tool = {
            name: (
                values[: settings.retrieval_chunk_limit]
                if name == "search_manual"
                else list(values)
            )
            for name, values in documents_by_tool.items()
        }
        definitions: list[ToolDefinition] = []
        for spec in production.tool_specs:
            name = spec.name
            original = production.definition(name)
            if original is None:
                raise RuntimeError(f"Production tool definition disappeared: {name}")
            behavior = behaviors.get(name)
            if behavior is None:
                definitions.append(original)
                continue
            definitions.append(
                ToolDefinition(
                    name=original.name,
                    description=original.description,
                    input_model=original.input_model,
                    output_model=original.output_model,
                    handler=_fixture_handler(
                        name=name,
                        behavior=behavior,
                        documents=resolved_documents_by_tool.get(name, []),
                        session=session,
                        context=context,
                    ),
                    read_only=original.read_only,
                    requires_approval=original.requires_approval,
                )
            )
        return ScenarioRegistry(
            session=session,
            context=context,
            definitions=definitions,
            documents_by_tool=resolved_documents_by_tool,
            max_retries=settings.provider_max_retries,
        )

    return factory


def _documents_for_tool(
    tool_name: str,
    behavior: dict[str, Any],
    documents: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    result = behavior.get("result") or {}
    declared_ids = {
        str(value) for key in ("chunk_ids", "incident_ids") for value in result.get(key, [])
    }
    if result.get("metadata_id"):
        declared_ids.add(str(result["metadata_id"]))
    if declared_ids:
        return [item for item in documents if str(item.get("document_id")) in declared_ids]
    source_types = {
        "search_manual": {"manual"},
        "search_incident_history": {"incident_history"},
        "get_sensor_history": {"sensor_metadata"},
    }.get(tool_name, set())
    return [item for item in documents if item.get("source_type") in source_types]


def _fixture_handler(
    *,
    name: str,
    behavior: dict[str, Any],
    documents: list[dict[str, Any]],
    session: Session,
    context: AuthContext,
) -> Callable[[BaseModel, str | None], BaseModel]:
    def handler(value: BaseModel, _: str | None) -> BaseModel:
        status = str(behavior["status"])
        if status == "access_denied":
            machine_id = getattr(value, "machine_id", None)
            log_security_event(
                session,
                context=context,
                event_type="cross_tenant_access_denied",
                target_type="machine" if machine_id else "tool",
                target_id=str(machine_id) if machine_id else name,
                detail="Scenario fixture denied a declared cross-tenant access attempt.",
            )
            raise TenantAccessDenied("machine not found")
        if status in {"timeout", "transient_error"}:
            raise TransientToolError(str(behavior.get("error_code", status)))
        if status in {"validation_error", "failure", "failed"}:
            raise ValueError(str(behavior.get("error_code", status)))
        if status == "no_data":
            if not isinstance(value, SensorHistoryInput):
                raise ValueError("no_data is only supported for sensor-history fixtures")
            return SensorHistoryOutput(
                machine_id=value.machine_id,
                metric=value.metric,
                readings=[],
                source_reference=f"tool:get_sensor_history:{value.machine_id}:{value.metric}",
                data_complete=False,
            )
        if status != "success":
            raise ValueError(f"unsupported scenario behavior status: {status}")
        return _success_output(name, value, behavior.get("result") or {}, documents)

    return handler


def _success_output(
    name: str,
    value: BaseModel,
    result: dict[str, Any],
    documents: list[dict[str, Any]],
) -> BaseModel:
    if name == "get_machine_status" and isinstance(value, MachineStatusInput):
        machine_id = str(result.get("machine_id", value.machine_id))
        return MachineStatusOutput(
            machine_id=machine_id,
            name=f"Scenario machine {machine_id}",
            model=str(result.get("model", "unknown")),
            line="Synthetic evaluation line",
            status=str(result.get("state", result.get("status", "unknown"))),
            alarm_code=result.get("alarm", result.get("alarm_code")),
            last_maintenance_at=None,
            source_reference=str(result.get("reference", f"machine:{machine_id}:current-status")),
        )
    if name == "get_sensor_history" and isinstance(value, SensorHistoryInput):
        raw_values = list(result.get("values", []))
        readings: list[SensorPoint] = []
        span = value.end_time - value.start_time
        for index, raw in enumerate(raw_values):
            point_value = raw.get("value") if isinstance(raw, dict) else raw
            fraction = (index + 1) / max(len(raw_values), 1)
            readings.append(
                SensorPoint(
                    timestamp=value.start_time + timedelta(seconds=span.total_seconds() * fraction),
                    value=float(point_value) if point_value is not None else None,
                    unit=str(result.get("unit", "unknown")),
                    quality="good",
                )
            )
        return SensorHistoryOutput(
            machine_id=value.machine_id,
            metric=str(result.get("metric", value.metric)),
            readings=readings,
            source_reference=str(
                result.get(
                    "reference", f"tool:get_sensor_history:{value.machine_id}:{value.metric}"
                )
            ),
            data_complete=bool(readings) and "missing_interval" not in result,
        )
    if name == "search_manual":
        manual_matches = [
            ManualMatch(
                chunk_id=str(document["document_id"]),
                title=f"Scenario manual {index + 1}",
                section=_document_section(str(document["document_id"])),
                excerpt=delimit_untrusted_content(str(document.get("content", ""))),
                source_reference=str(document["document_id"]),
                relevance_score=max(0.0, 1.0 - index * 0.01),
            )
            for index, document in enumerate(documents)
        ]
        return SearchManualOutput(
            matches=manual_matches,
            returned_chunks=len(manual_matches),
        )
    if name == "search_incident_history" and isinstance(value, SearchIncidentHistoryInput):
        incident_matches = [
            IncidentMatch(
                incident_id=str(document["document_id"]).removeprefix("incident:"),
                machine_id=value.machine_id or "unknown",
                title=f"Scenario incident {index + 1}",
                summary=delimit_untrusted_content(str(document.get("content", ""))),
                resolution=delimit_untrusted_content("No separate resolution was declared."),
                occurred_at=_FIXED_EVENT_TIME - timedelta(days=index),
                source_reference=str(document["document_id"]),
                relevance_score=max(0.0, 1.0 - index * 0.01),
            )
            for index, document in enumerate(documents)
        ]
        return SearchIncidentHistoryOutput(matches=incident_matches)
    raise ValueError(f"scenario success output is not implemented for {name}")


def _document_section(document_id: str) -> str:
    if "#" in document_id:
        return document_id.rsplit("#", 1)[1]
    return document_id
