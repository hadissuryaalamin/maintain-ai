from __future__ import annotations

from typing import Any

from evals.runner import _render_markdown


def test_scenario_markdown_supports_optimized_only_report() -> None:
    aggregate: dict[str, Any] = {
        "case_count": 1,
        "task_completion_rate": {"numerator": 1, "denominator": 1, "value": 1.0},
        "correct_tool_selection_rate": {
            "numerator": 1,
            "denominator": 1,
            "value": 1.0,
            "coverage": 1.0,
        },
        "grounded_answer_rate": {
            "numerator": 1,
            "denominator": 1,
            "value": 1.0,
            "coverage": 1.0,
        },
        "total_tokens_estimated": 100,
        "token_usage_coverage": 1.0,
        "total_cost_usd_estimated": 0.0,
        "cost_coverage": 1.0,
        "average_latency_ms": {"value": 10.0},
    }
    report: dict[str, Any] = {
        "report_kind": "scenario_integration",
        "warning": "Synthetic scenario only.",
        "generated_at": "2026-01-01T00:00:00Z",
        "aggregates": {"optimized": aggregate},
        "comparison": None,
        "case_results": {"optimized": []},
        "optimization_levers": {
            "retrieval_chunk_limit": {
                "baseline_limit": 6,
                "optimized_limit": 4,
                "observable_truncation_cases": 0,
                "observed_retrieval_deltas": [],
            }
        },
        "offline_routing_policy_analysis": {
            "warning": "Shadow calculation only.",
            "variants": {"optimized": {"model_counts": {"small": 1}}},
            "paired_shadow_cost": {
                "paired_case_count": 0,
                "baseline_usd": None,
                "optimized_usd": None,
            },
        },
        "limitations": ["Not a live-model benchmark."],
    }

    markdown = _render_markdown(report)

    assert markdown.startswith("# Scenario integration optimized-only report")
    assert "--mode optimized --backend scenario" in markdown
    assert "| Metric | Optimized |" in markdown
    assert "100.0% (1/1; 100.0% case coverage)" in markdown
    assert "only one variant" in markdown
