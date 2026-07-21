"""Persistence and aggregation for observable agent runs."""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import AgentRun, ModelUsage, ToolCallEvent
from app.llm.base import ProviderResponse
from app.schemas.api import AnalyticsSummary, ToolTraceItem, UsageSummary
from app.security.context import AuthContext
from app.telemetry.pricing import PricingCatalog


class TelemetryService:
    def __init__(
        self,
        session: Session,
        context: AuthContext,
        settings: Settings,
        pricing: PricingCatalog | None = None,
    ) -> None:
        self.session = session
        self.context = context
        self.settings = settings
        self.pricing = pricing or PricingCatalog.load(settings.model_pricing_path)

    def record_model_response(
        self,
        *,
        run_id: str,
        response: ProviderResponse,
        provider: str,
        model: str,
        step: int,
        latency_ms: int,
        tool_names: list[str],
    ) -> ModelUsage:
        # Pricing effective dates are calendar snapshots maintained in the deployment's
        # configured local timezone, while event timestamps below remain UTC.
        now = datetime.now().astimezone()
        cost = self.pricing.calculate(provider=provider, model=model, usage=response.usage, at=now)
        event = ModelUsage(
            id=str(uuid4()),
            run_id=run_id,
            request_id=response.request_id,
            tenant_id=self.context.tenant_id,
            user_id=self.context.user_id,
            provider=provider,
            model=model,
            agent_step=step,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            cached_input_tokens=response.usage.cached_input_tokens,
            cache_write_tokens=response.usage.cache_write_tokens,
            usage_is_estimated=response.usage.estimated,
            input_cost=cost.input_cost,
            output_cost=cost.output_cost,
            total_cost=cost.total_cost,
            pricing_version=cost.pricing_version,
            latency_ms=latency_ms,
            tool_names_json=tool_names,
            status="succeeded",
        )
        self.session.add(event)
        self.session.flush()
        return event

    def record_model_error(
        self,
        *,
        run_id: str,
        request_id: str,
        provider: str,
        model: str,
        step: int,
        latency_ms: int,
        error_category: str,
    ) -> ModelUsage:
        event = ModelUsage(
            id=str(uuid4()),
            run_id=run_id,
            request_id=request_id,
            tenant_id=self.context.tenant_id,
            user_id=self.context.user_id,
            provider=provider,
            model=model,
            agent_step=step,
            input_tokens=None,
            output_tokens=None,
            cached_input_tokens=None,
            cache_write_tokens=None,
            usage_is_estimated=False,
            input_cost=None,
            output_cost=None,
            total_cost=None,
            pricing_version=None,
            latency_ms=latency_ms,
            tool_names_json=[],
            status="failed",
            error_category=error_category,
        )
        self.session.add(event)
        self.session.flush()
        return event

    def record_tool_call(
        self,
        *,
        run_id: str,
        step: int,
        call_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        result_preview: str,
        status: str,
        error_category: str | None,
        latency_ms: int,
    ) -> ToolCallEvent:
        stored_arguments = (
            arguments
            if self.settings.store_tool_payloads
            else _redact_tool_arguments(tool_name, arguments)
        )
        stored_preview = (
            result_preview[:1000]
            if self.settings.store_tool_payloads
            else "[tool result payload redacted by default]"
        )
        event = ToolCallEvent(
            id=str(uuid4()),
            run_id=run_id,
            tenant_id=self.context.tenant_id,
            user_id=self.context.user_id,
            agent_step=step,
            call_id=call_id,
            tool_name=tool_name,
            arguments_json=stored_arguments,
            result_preview=stored_preview,
            status=status,
            error_category=error_category,
            latency_ms=latency_ms,
        )
        self.session.add(event)
        self.session.flush()
        return event

    def usage_summary(self, run_id: str, *, model: str, provider: str) -> UsageSummary:
        events = list(
            self.session.scalars(
                select(ModelUsage).where(
                    ModelUsage.run_id == run_id,
                    ModelUsage.tenant_id == self.context.tenant_id,
                )
            )
        )
        return _usage_summary(events, model=model, provider=provider)

    def tool_trace(self, run_id: str) -> list[ToolTraceItem]:
        events = list(
            self.session.scalars(
                select(ToolCallEvent)
                .where(
                    ToolCallEvent.run_id == run_id,
                    ToolCallEvent.tenant_id == self.context.tenant_id,
                )
                .order_by(ToolCallEvent.created_at, ToolCallEvent.id)
            )
        )
        return [
            ToolTraceItem(
                tool_name=event.tool_name,
                call_id=event.call_id,
                status=event.status,
                arguments=event.arguments_json,
                result_preview=event.result_preview,
                latency_ms=event.latency_ms,
                error_category=event.error_category,
            )
            for event in events
        ]

    def analytics(self) -> AnalyticsSummary:
        runs = list(
            self.session.scalars(
                select(AgentRun).where(AgentRun.tenant_id == self.context.tenant_id)
            )
        )
        run_ids = [run.id for run in runs]
        usages: list[ModelUsage] = []
        tools: list[ToolCallEvent] = []
        if run_ids:
            usages = list(
                self.session.scalars(
                    select(ModelUsage).where(
                        ModelUsage.tenant_id == self.context.tenant_id,
                        ModelUsage.run_id.in_(run_ids),
                    )
                )
            )
            tools = list(
                self.session.scalars(
                    select(ToolCallEvent).where(
                        ToolCallEvent.tenant_id == self.context.tenant_id,
                        ToolCallEvent.run_id.in_(run_ids),
                    )
                )
            )

        unpriced_requests = sum(item.total_cost is None for item in usages)
        unavailable_usage_requests = sum(
            item.input_tokens is None or item.output_tokens is None for item in usages
        )
        priced_total = sum(
            (Decimal(str(item.total_cost)) for item in usages if item.total_cost is not None),
            Decimal(0),
        )
        total_cost: Decimal | None = None if unpriced_requests else priced_total
        successful = sum(run.status == "completed" for run in runs)
        # An approval-required result is the expected safe outcome of a write proposal,
        # not a tool failure. It remains in the call count/frequency while only rejected or
        # genuinely failed executions contribute to the failure rate.
        failed_tools = sum(item.status in {"failed", "rejected"} for item in tools)
        cost_by_model: dict[str, Decimal | None] = {}
        for model in {item.model for item in usages}:
            model_usage = [item for item in usages if item.model == model]
            cost_by_model[model] = (
                None
                if any(item.total_cost is None for item in model_usage)
                else sum((Decimal(str(item.total_cost)) for item in model_usage), Decimal(0))
            )
        task_by_run = {run.id: run.task_type for run in runs}
        cost_by_task: dict[str, Decimal | None] = {}
        for task in set(task_by_run.values()):
            task_usage = [
                item for item in usages if task_by_run.get(item.run_id, "unknown") == task
            ]
            cost_by_task[task] = (
                None
                if any(item.total_cost is None for item in task_usage)
                else sum((Decimal(str(item.total_cost)) for item in task_usage), Decimal(0))
            )
        modes: dict[str, dict[str, float | int | None]] = {}
        for mode in {run.optimization_mode for run in runs}:
            selected = [run for run in runs if run.optimization_mode == mode]
            selected_ids = {run.id for run in selected}
            selected_usage = [item for item in usages if item.run_id in selected_ids]
            mode_cost = sum(
                (
                    Decimal(str(item.total_cost))
                    for item in selected_usage
                    if item.total_cost is not None
                ),
                Decimal(0),
            )
            mode_has_unpriced = any(item.total_cost is None for item in selected_usage)
            mode_has_unavailable_usage = any(
                item.input_tokens is None or item.output_tokens is None for item in selected_usage
            )
            modes[mode] = {
                "runs": len(selected),
                "success_rate": (
                    sum(run.status == "completed" for run in selected) / len(selected)
                    if selected
                    else 0.0
                ),
                "average_cost": (
                    None if mode_has_unpriced else float(mode_cost / max(len(selected), 1))
                ),
                "average_tokens": (
                    None
                    if mode_has_unavailable_usage
                    else sum(
                        (item.input_tokens or 0) + (item.output_tokens or 0)
                        for item in selected_usage
                    )
                    / max(len(selected), 1)
                ),
            }

        return AnalyticsSummary(
            run_count=len(runs),
            successful_runs=successful,
            success_rate=successful / len(runs) if runs else 0.0,
            total_cost=total_cost,
            average_cost_per_run=(
                total_cost / max(len(runs), 1) if total_cost is not None else None
            ),
            unpriced_model_requests=unpriced_requests,
            unavailable_usage_requests=unavailable_usage_requests,
            total_input_tokens=(
                None
                if unavailable_usage_requests
                else sum(item.input_tokens or 0 for item in usages)
            ),
            total_output_tokens=(
                None
                if unavailable_usage_requests
                else sum(item.output_tokens or 0 for item in usages)
            ),
            average_latency_ms=(
                sum(item.latency_ms for item in usages) / len(usages) if usages else 0.0
            ),
            tool_call_count=len(tools),
            tool_failure_rate=failed_tools / len(tools) if tools else 0.0,
            cost_by_model=cost_by_model,
            cost_by_task_type=cost_by_task,
            tool_frequency=dict(Counter(item.tool_name for item in tools)),
            optimization_comparison=modes,
        )


def _usage_summary(events: list[ModelUsage], *, model: str, provider: str) -> UsageSummary:
    if not events:
        return UsageSummary(
            model=model,
            provider=provider,
            model_requests=0,
            input_tokens=None,
            output_tokens=None,
            cached_input_tokens=None,
            estimated_total_cost=None,
            latency_ms=0,
            usage_is_estimated=False,
        )
    available_inputs = [event.input_tokens for event in events if event.input_tokens is not None]
    available_outputs = [event.output_tokens for event in events if event.output_tokens is not None]
    cached = [
        event.cached_input_tokens for event in events if event.cached_input_tokens is not None
    ]
    costs = [Decimal(event.total_cost) for event in events if event.total_cost is not None]
    return UsageSummary(
        model=model,
        provider=provider,
        model_requests=len(events),
        input_tokens=sum(available_inputs) if len(available_inputs) == len(events) else None,
        output_tokens=sum(available_outputs) if len(available_outputs) == len(events) else None,
        cached_input_tokens=sum(cached) if len(cached) == len(events) else None,
        estimated_total_cost=sum(costs, Decimal(0)) if len(costs) == len(events) else None,
        latency_ms=sum(event.latency_ms for event in events),
        usage_is_estimated=any(event.usage_is_estimated for event in events),
    )


_SAFE_TOOL_ARGUMENT_FIELDS = {
    "search_manual": {"machine_model"},
    "get_machine_status": {"machine_id"},
    "get_sensor_history": {"machine_id", "metric", "start_time", "end_time"},
    "search_incident_history": {"machine_id"},
    "calculate_downtime_cost": {"machine_id", "downtime_minutes"},
    "create_work_order": {"machine_id", "priority"},
}


def _redact_tool_arguments(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Keep useful operational selectors while omitting free text and unknown payloads."""

    safe_fields = _SAFE_TOOL_ARGUMENT_FIELDS.get(tool_name, set())
    return {key: value if key in safe_fields else "[redacted]" for key, value in arguments.items()}
