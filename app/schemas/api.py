"""HTTP API request and response contracts."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import OptimizationMode, RunStatus
from app.schemas.diagnostic import DiagnosticResult


class ApiSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ConversationMessage(ApiSchema):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=20000)


class DiagnoseRequest(ApiSchema):
    message: str = Field(min_length=3, max_length=10000)
    conversation_history: list[ConversationMessage] = Field(default_factory=list, max_length=100)
    optimization_mode: OptimizationMode = OptimizationMode.OPTIMIZED
    task_type: str = Field(default="diagnostic", min_length=1, max_length=50)


class ToolTraceItem(ApiSchema):
    tool_name: str
    call_id: str
    status: str
    arguments: dict[str, Any]
    result_preview: str
    latency_ms: int
    error_category: str | None = None


class UsageSummary(ApiSchema):
    model: str
    provider: str
    model_requests: int = 0
    input_tokens: int | None = None
    output_tokens: int | None = None
    cached_input_tokens: int | None = None
    estimated_total_cost: Decimal | None = None
    latency_ms: int = 0
    usage_is_estimated: bool = False


class PendingApproval(ApiSchema):
    approval_id: str
    tool_name: str
    proposed_action: dict[str, Any]
    message: str


class DiagnoseResponse(ApiSchema):
    run_id: str
    status: RunStatus
    diagnostic: DiagnosticResult | None = None
    pending_approval: PendingApproval | None = None
    tool_trace: list[ToolTraceItem] = Field(default_factory=list)
    usage: UsageSummary
    error: str | None = None


class ApprovalDecisionRequest(ApiSchema):
    approved: bool
    idempotency_key: str = Field(min_length=8, max_length=128)


class ApprovalDecisionResponse(ApiSchema):
    approval_id: str
    status: str
    result: dict[str, Any] | None = None


class RunRecord(ApiSchema):
    run_id: str
    status: str
    task_type: str
    optimization_mode: str
    model: str
    provider: str
    diagnostic: dict[str, Any] | None
    error_category: str | None
    started_at: datetime
    completed_at: datetime | None
    tool_trace: list[ToolTraceItem]
    usage: UsageSummary


class AnalyticsSummary(ApiSchema):
    run_count: int
    successful_runs: int
    success_rate: float
    total_cost: Decimal | None
    average_cost_per_run: Decimal | None
    unpriced_model_requests: int
    unavailable_usage_requests: int
    total_input_tokens: int | None
    total_output_tokens: int | None
    average_latency_ms: float
    tool_call_count: int
    tool_failure_rate: float
    cost_by_model: dict[str, Decimal | None]
    cost_by_task_type: dict[str, Decimal | None]
    tool_frequency: dict[str, int]
    optimization_comparison: dict[str, dict[str, float | int | None]]


class MachineSummary(ApiSchema):
    id: str
    name: str
    model: str
    line: str
    status: str
    condition: str | None = None
    active_alarm: str | None = None
    criticality: str | None = None
    hourly_downtime_cost: Decimal
    cost_currency: str | None = None
    last_status_at: datetime | None = None


class SensorPointOut(ApiSchema):
    value: float | None
    quality: str
    recorded_at: datetime


class SensorSeries(ApiSchema):
    metric: str
    unit: str
    latest: SensorPointOut | None
    readings: list[SensorPointOut]


class MachineSensors(ApiSchema):
    machine_id: str
    series: list[SensorSeries]
