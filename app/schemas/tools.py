"""Typed tool input and output contracts.

No model-facing input includes ``tenant_id``. Tenant authority always comes from the
authenticated application context.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ToolSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SearchManualInput(ToolSchema):
    query: str = Field(min_length=2, max_length=500)
    machine_model: str | None = Field(default=None, min_length=1, max_length=100)


class ManualMatch(ToolSchema):
    chunk_id: str
    title: str
    section: str
    excerpt: str
    source_reference: str
    relevance_score: float = Field(ge=0)
    content_is_untrusted: bool = True


class SearchManualOutput(ToolSchema):
    matches: list[ManualMatch]
    returned_chunks: int = Field(ge=0)


class MachineStatusInput(ToolSchema):
    machine_id: str = Field(min_length=1, max_length=64)


class MachineStatusOutput(ToolSchema):
    machine_id: str
    name: str
    model: str
    line: str
    status: str
    alarm_code: str | None
    last_maintenance_at: datetime | None
    source_reference: str


class SensorHistoryInput(ToolSchema):
    machine_id: str = Field(min_length=1, max_length=64)
    metric: str = Field(min_length=1, max_length=100)
    start_time: datetime
    end_time: datetime

    @model_validator(mode="after")
    def validate_range(self) -> SensorHistoryInput:
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        if (self.end_time - self.start_time).days > 31:
            raise ValueError("sensor history range cannot exceed 31 days")
        return self


class SensorPoint(ToolSchema):
    timestamp: datetime
    value: float | None
    unit: str
    quality: str = "good"


class SensorHistoryOutput(ToolSchema):
    machine_id: str
    metric: str
    readings: list[SensorPoint]
    source_reference: str
    data_complete: bool


class SearchIncidentHistoryInput(ToolSchema):
    query: str = Field(min_length=2, max_length=500)
    machine_id: str | None = Field(default=None, min_length=1, max_length=64)


class IncidentMatch(ToolSchema):
    incident_id: str
    machine_id: str
    title: str
    summary: str
    resolution: str
    occurred_at: datetime
    source_reference: str
    relevance_score: float = Field(ge=0)


class SearchIncidentHistoryOutput(ToolSchema):
    matches: list[IncidentMatch]


class DowntimeCostInput(ToolSchema):
    machine_id: str = Field(min_length=1, max_length=64)
    downtime_minutes: int = Field(gt=0, le=60 * 24 * 31)


class DowntimeCostOutput(ToolSchema):
    machine_id: str
    downtime_minutes: int
    hourly_cost: Decimal
    estimated_cost: Decimal
    currency: str = "USD"
    source_reference: str


class WorkOrderPriority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class CreateWorkOrderInput(ToolSchema):
    machine_id: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=3, max_length=250)
    description: str = Field(min_length=3, max_length=4000)
    priority: WorkOrderPriority


class CreateWorkOrderOutput(ToolSchema):
    work_order_id: str
    machine_id: str
    title: str
    priority: WorkOrderPriority
    status: str
    created_at: datetime
    idempotent_replay: bool = False


class ToolError(ToolSchema):
    category: str
    message: str
    retryable: bool = False


class ToolExecutionResult(ToolSchema):
    ok: bool
    tool_name: str
    data: dict[str, Any] | None = None
    error: ToolError | None = None
    approval_id: str | None = None
    proposed_action: dict[str, Any] | None = None
