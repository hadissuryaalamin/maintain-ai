"""Reproducibility and failure-sensitive scoring for the five-scenario comparison."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from evals.prediction import ROOT, evaluate, render_report, score_result


@pytest.fixture(scope="module")
def comparison(tmp_path_factory):
    return evaluate(
        ROOT / "evals/cases/prediction-v1.json",
        tmp_path_factory.mktemp("prediction-comparison"),
    )


def test_comparison_changes_feature_availability_without_claiming_a_model_benchmark(comparison):
    assert comparison["network_calls_to_aws_or_paid_models"] is False
    assert "feature-off" in comparison["method"]
    assert len(comparison["dataset"]["cases"]) == 5
    assert len(comparison["dataset_sha256"]) == 64
    assert comparison["source_sha256"]["evals/prediction.py"]
    before = comparison["variants"]["before_feature_off"]["summary"]
    after = comparison["variants"]["after_feature_on"]["summary"]
    assert before["prediction_http_calls"] == 0
    assert before["outcome_conformance_passed"] == 0
    assert after["prediction_cases_passed"] == 4
    assert after["failure_cases_passed"] == 1
    assert after["outcome_conformance_passed"] == 5
    assert after["prediction_http_calls"] == 5


def test_removed_prediction_evidence_fails_scoring(comparison):
    case = comparison["dataset"]["cases"][0]
    row = deepcopy(comparison["variants"]["after_feature_on"]["results"][0])
    row["response"]["diagnostic"]["observations"] = []
    result = score_result(case, row["response"], row["observed_prediction_inputs"])
    assert result["passed"] is False
    assert result["checks"]["grounded_score_and_label"] is False


def test_wrong_input_is_not_accepted_as_success(comparison):
    case = comparison["dataset"]["cases"][0]
    row = comparison["variants"]["after_feature_on"]["results"][0]
    result = score_result(case, row["response"], [case["inputs"] | {"rpm": 999}])
    assert result["passed"] is False
    assert result["checks"]["exact_inputs_sent_once"] is False


def test_unavailable_service_is_failed_run_with_no_fabricated_prediction(comparison):
    row = comparison["variants"]["after_feature_on"]["results"][-1]
    assert row["response"]["status"] == "failed"
    assert row["passed"] is True
    assert row["checks"]["no_fabricated_prediction"] is True


def test_report_distinguishes_scenario_conformance_from_prediction_success(comparison):
    report = render_report(comparison)
    assert "4/4" in report and "1/1" in report and "5/5" in report
    assert "declared fixtures" in report
    assert "do not mean five successful predictions" in report
    assert "historical checkout" in report
    assert "python -m evals.prediction" in report


def test_evaluation_leaves_no_temporary_databases(tmp_path: Path):
    evaluate(ROOT / "evals/cases/prediction-v1.json", tmp_path)
    assert list(tmp_path.iterdir()) == []
