"""Structured maintenance diagnostic output."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourceType(StrEnum):
    TOOL = "tool"
    MANUAL = "manual"
    INCIDENT_HISTORY = "incident_history"
    USER = "user"


class Confidence(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Observation(StrictSchema):
    statement: str = Field(min_length=1, max_length=1000)
    source_type: SourceType
    source_reference: str = Field(min_length=1, max_length=500)


class PossibleCause(StrictSchema):
    cause: str = Field(min_length=1, max_length=500)
    confidence: Confidence
    reasoning_summary: str = Field(
        min_length=1,
        max_length=1000,
        description="Concise evidence summary, never hidden chain-of-thought.",
    )


class RecommendedAction(StrictSchema):
    step: int = Field(ge=1, le=50)
    action: str = Field(min_length=1, max_length=1000)
    requires_shutdown: bool
    requires_approval: bool


class DiagnosticResult(StrictSchema):
    incident_summary: str = Field(min_length=1, max_length=1500)
    observations: list[Observation] = Field(max_length=30)
    possible_causes: list[PossibleCause] = Field(max_length=15)
    recommended_actions: list[RecommendedAction] = Field(max_length=20)
    missing_information: list[str] = Field(max_length=20)
    safety_notice: str = Field(min_length=1, max_length=1500)

    @model_validator(mode="after")
    def actions_have_unique_order(self) -> DiagnosticResult:
        steps = [action.step for action in self.recommended_actions]
        if len(steps) != len(set(steps)):
            raise ValueError("recommended action steps must be unique")
        return self
