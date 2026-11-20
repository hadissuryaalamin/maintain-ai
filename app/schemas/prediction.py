"""Contracts for the synthetic AI4I failure-evidence prediction service."""

from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, model_validator


class FailurePredictionInput(BaseModel):
    """Six supplied measurements; never infer missing values or accept outcome flags."""

    model_config = ConfigDict(extra="forbid", strict=True)

    type: Literal["L", "M", "H"]
    air_temp_k: FiniteFloat = Field(gt=0, description="Air temperature in kelvin")
    process_temp_k: FiniteFloat = Field(gt=0, description="Process temperature in kelvin")
    rpm: FiniteFloat = Field(gt=0, description="Rotational speed in rpm")
    torque_nm: FiniteFloat = Field(ge=0, description="Torque in newton-metres")
    tool_wear_min: FiniteFloat = Field(ge=0, description="Tool wear in minutes")

    @model_validator(mode="after")
    def finite_interaction(self) -> FailurePredictionInput:
        if not math.isfinite(self.torque_nm * self.tool_wear_min):
            raise ValueError("Torque times tool wear must remain finite.")
        return self


class FailurePredictionOutput(BaseModel):
    """Service evidence, not a calibrated physical risk or an equipment diagnosis."""

    model_config = ConfigDict(extra="forbid", strict=True)

    failure_score: FiniteFloat = Field(ge=0, le=1)
    predicted_label: int = Field(ge=0, le=1)
    threshold: FiniteFloat = Field(ge=0.5, le=0.5)
    target_policy: Literal["failure_evidence_or_v1"]

    @model_validator(mode="after")
    def consistent_label(self) -> FailurePredictionOutput:
        if self.predicted_label != int(self.failure_score >= self.threshold):
            raise ValueError("Label is inconsistent with the score and threshold.")
        return self


class FailureRiskToolOutput(FailurePredictionOutput):
    """Prediction plus application-authored provenance for the agent evidence layer."""

    source_reference: str = Field(min_length=1)
    model_scope: Literal["synthetic_ai4i_demo"] = "synthetic_ai4i_demo"
