"""Conservative parsing for an explicitly requested standalone AI4I demonstration."""

from __future__ import annotations

import json
import re

from app.schemas.prediction import FailurePredictionInput

PREDICTION_INPUT_GUIDANCE = (
    "Provide one JSON object with all six inputs: type (L/M/H), air_temp_k and "
    "process_temp_k (kelvin), rpm, torque_nm (Nm), and tool_wear_min (minutes). "
    "Do not include failure labels, flags, or a server URL. Values must be finite; "
    "temperatures and rpm must be positive, and torque/tool wear nonnegative."
)


def is_prediction_request(message: str) -> bool:
    """Require explicit prediction intent in the request prefix, not retrieved text."""
    prefix = message.split("{", 1)[0]
    return bool(
        re.search(
            r"(?i)^\s*(?:please\s+)?(?:predict_failure_risk|predict\s+(?:machine\s+)?failure|"
            r"failure\s+prediction|prediksi\s+kegagalan)\b",
            prefix,
        )
    )


def _unique_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON keys are not accepted.")
        result[key] = value
    return result


def parse_prediction_inputs(message: str) -> FailurePredictionInput:
    """Only accept a single, complete trailing JSON object with no silent coercion."""
    start = message.find("{")
    if start < 0:
        raise ValueError(PREDICTION_INPUT_GUIDANCE)
    payload = json.loads(message[start:], object_pairs_hook=_unique_keys)
    return FailurePredictionInput.model_validate(payload)
