"""Compare prediction feature off/on using real agent execution and mocked HTTP.

Both variants use identical code and optimized agent settings. Only prediction
tool availability changes. No AWS, paid LLM, or real prediction endpoint is called.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import tempfile
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from time import perf_counter
from typing import Any

import httpx
from fastapi.testclient import TestClient

from app.config import Settings
from app.db.session import Database
from app.llm.demo_provider import DemoProvider
from app.main import create_app
from app.schemas.prediction import FailurePredictionInput, FailurePredictionOutput
from app.tools.prediction import FailurePredictionClient
from app.tools.registry import build_tool_registry

ROOT = Path(__file__).resolve().parents[1]


def score_result(case: dict[str, Any], response: dict[str, Any], calls: list[dict]) -> dict:
    """Score declared behavior from the actual API output and observed transport calls."""
    trace = response.get("tool_trace", [])
    diagnostic = response.get("diagnostic") or {}
    evidence = [x for x in diagnostic.get("observations", []) if x["source_type"] == "tool"]
    checks = {
        "expected_terminal_status": response.get("status") == case["expected_status"],
        "prediction_selected_once": [x["tool_name"] for x in trace] == ["predict_failure_risk"],
        "exact_inputs_sent_once": calls == [case["inputs"]],
        "no_fault_hypotheses": diagnostic.get("possible_causes") == [],
        "no_equipment_or_work_order_action": not any(
            x["requires_shutdown"] or x["requires_approval"]
            for x in diagnostic.get("recommended_actions", [])
        ),
    }
    if case["fixture"]["kind"] == "json":
        expected = case["fixture"]["response"]
        checks["successful_tool_trace"] = len(trace) == 1 and trace[0]["status"] == "succeeded"
        checks["grounded_score_and_label"] = len(evidence) == 1 and (
            f"failure-evidence score {expected['failure_score']:.8g}" in evidence[0]["statement"]
            and f"predicted class {expected['predicted_label']}" in evidence[0]["statement"]
            and evidence[0]["source_reference"].startswith("tool:predict_failure_risk:")
        )
        checks["score_limitation_disclosed"] = len(evidence) == 1 and (
            "not a calibrated physical failure probability" in evidence[0]["statement"]
        )
    else:
        checks["controlled_failed_tool_trace"] = len(trace) == 1 and trace[0]["status"] == "failed"
        checks["no_fabricated_prediction"] = not evidence and (
            "No failure-evidence score" in " ".join(diagnostic.get("missing_information", []))
        )
    return {"checks": checks, "passed": all(checks.values())}


def run_case(case: dict, *, enabled: bool, workdir: Path, project_root: Path) -> dict:
    calls: list[dict] = []

    def handle(request: httpx.Request) -> httpx.Response:
        if request.method != "POST" or request.url.path != "/predict":
            raise AssertionError("Unexpected prediction request")
        calls.append(json.loads(request.content))
        if case["fixture"]["kind"] == "connect_error":
            raise httpx.ConnectError("Declared offline service failure", request=request)
        return httpx.Response(200, json=case["fixture"]["response"])

    def registry_factory(session, context, settings):
        return build_tool_registry(
            session,
            context,
            settings,
            prediction_client=FailurePredictionClient(transport=httpx.MockTransport(handle)),
        )

    with tempfile.TemporaryDirectory(prefix="prediction-eval-", dir=workdir) as temp:
        settings = Settings(
            _env_file=None,
            app_env="test",
            llm_provider="demo",
            allow_demo_auth=True,
            auto_seed=True,
            database_url=f"sqlite:///{Path(temp).as_posix()}/eval.db",
            data_path=project_root / "data",
            model_pricing_path=project_root / "config/model_pricing.yaml",
            failure_prediction_enabled=enabled,
            failure_prediction_timeout_seconds=1,
            provider_max_retries=0,
            request_timeout_seconds=15,
            store_tool_payloads=True,
            store_prompt_preview=False,
        )
        database = Database(settings.database_url)
        app = create_app(
            settings=settings,
            database=database,
            provider=DemoProvider(),
            registry_factory=registry_factory,
        )
        with TestClient(app) as client:
            started = perf_counter()
            result = client.post(
                "/api/v1/incidents/diagnose",
                headers={"X-Tenant-ID": "company-a", "X-User-ID": "user-a-tech"},
                json={"message": case["message"], "optimization_mode": "optimized"},
            )
            elapsed_ms = round((perf_counter() - started) * 1000, 3)
            result.raise_for_status()
            response = result.json()
    return {
        "case_id": case["id"],
        "feature_enabled": enabled,
        "elapsed_request_ms": elapsed_ms,
        "http_status": result.status_code,
        "observed_prediction_inputs": calls,
        **score_result(case, response, calls),
        "response": response,
    }


def summarize(cases: list[dict], results: list[dict]) -> dict:
    returning = {x["id"] for x in cases if x["fixture"]["kind"] == "json"}
    score_rows = [x for x in results if x["case_id"] in returning]
    failure_rows = [x for x in results if x["case_id"] not in returning]
    usages = [x["response"]["usage"] for x in results]
    return {
        "cases": len(results),
        "outcome_conformance_passed": sum(x["passed"] for x in results),
        "prediction_cases": len(score_rows),
        "prediction_cases_passed": sum(x["passed"] for x in score_rows),
        "failure_cases": len(failure_rows),
        "failure_cases_passed": sum(x["passed"] for x in failure_rows),
        "prediction_http_calls": sum(len(x["observed_prediction_inputs"]) for x in results),
        "estimated_input_tokens": sum(x["input_tokens"] or 0 for x in usages),
        "estimated_output_tokens": sum(x["output_tokens"] or 0 for x in usages),
        "estimated_cost_usd": str(
            sum((Decimal(x["estimated_total_cost"] or "0") for x in usages), Decimal(0))
        ),
        "mean_inprocess_request_ms": round(
            sum(x["elapsed_request_ms"] for x in results) / len(results), 3
        ),
    }


def evaluate(dataset: Path, workdir: Path, *, project_root: Path = ROOT) -> dict:
    document = json.loads(dataset.read_text(encoding="utf-8-sig"))
    cases = document["cases"]
    if document["schema_version"] != "prediction-integration-v1" or not 3 <= len(cases) <= 5:
        raise ValueError("Expected a version-one dataset containing 3 to 5 scenarios")
    if len({case["id"] for case in cases}) != len(cases):
        raise ValueError("Scenario IDs must be unique")
    for case in cases:
        FailurePredictionInput.model_validate(case["inputs"])
        kind = case["fixture"]["kind"]
        if kind == "json":
            FailurePredictionOutput.model_validate(case["fixture"]["response"])
        elif kind != "connect_error":
            raise ValueError("Unknown fixture kind")
    workdir.mkdir(parents=True, exist_ok=True)
    variants = {}
    for name, enabled in [("before_feature_off", False), ("after_feature_on", True)]:
        results = [
            run_case(case, enabled=enabled, workdir=workdir, project_root=project_root)
            for case in cases
        ]
        variants[name] = {"summary": summarize(cases, results), "results": results}
    code_paths = [
        *sorted((project_root / "app").rglob("*.py")),
        project_root / "evals/prediction.py",
    ]
    return {
        "report_schema": "prediction-comparison-v1",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "method": "Controlled feature-off versus feature-on ablation using identical current code",
        "scope": "Real in-process API/agent/registry; demo provider; mocked prediction HTTP",
        "network_calls_to_aws_or_paid_models": False,
        "python_version": platform.python_version(),
        "dataset_sha256": hashlib.sha256(dataset.read_bytes()).hexdigest(),
        "dataset": document,
        "source_sha256": {
            str(p.relative_to(project_root)).replace("\\", "/"): hashlib.sha256(
                p.read_bytes()
            ).hexdigest()
            for p in code_paths
        },
        "variants": variants,
    }


def render_report(report: dict) -> str:
    before = report["variants"]["before_feature_off"]
    after = report["variants"]["after_feature_on"]
    b, a = before["summary"], after["summary"]
    rows = []
    for label, passed, total in [
        ("Expected scenario outcomes", "outcome_conformance_passed", "cases"),
        ("Prediction-producing scenarios passed", "prediction_cases_passed", "prediction_cases"),
        ("Unavailable-service scenario passed", "failure_cases_passed", "failure_cases"),
    ]:
        rows.append((label, f"{b[passed]}/{b[total]}", f"{a[passed]}/{a[total]}"))
    for label, key in [
        ("Prediction HTTP calls (mocked)", "prediction_http_calls"),
        ("Estimated input tokens", "estimated_input_tokens"),
        ("Estimated output tokens", "estimated_output_tokens"),
        ("Demo estimated cost (USD)", "estimated_cost_usd"),
        ("Mean in-process request time (ms)", "mean_inprocess_request_ms"),
    ]:
        rows.append((label, str(b[key]), str(a[key])))
    lines = [
        "# Prediction tool integration comparison",
        "",
        "Five synthetic scenarios compare identical current agent code with the feature off/on.",
        "The real in-process API, agent and registry execute; prediction HTTP is mocked.",
        "This is a controlled feature ablation, not a historical checkout or ML accuracy test.",
        "It does not measure paid LLM quality.",
        "",
        f"Generated (UTC): `{report['generated_at_utc']}`. Python: `{report['python_version']}`.",
        "",
        "## Results",
        "",
        "| Metric | Before: feature off | After: feature on |",
        "| --- | ---: | ---: |",
        *[f"| {label} | {old} | {new} |" for label, old, new in rows],
        "",
        "Outcome conformance includes correct explicit failure handling.",
        "Four scenarios return predictions; the fifth should fail without inventing a score.",
        "Five conforming outcomes do not mean five successful predictions.",
        "",
        "## Per-scenario results",
        "",
        "| Scenario | Before status | After status | Before pass | After pass |",
        "| --- | --- | --- | --- | --- |",
    ]
    for old, new in zip(before["results"], after["results"], strict=True):
        old_status, new_status = old["response"]["status"], new["response"]["status"]
        lines.append(
            f"| {new['case_id']} | {old_status} | {new_status} | "
            f"{old['passed']} | {new['passed']} |"
        )
    lines += [
        "",
        "## Interpretation and limits",
        "",
        "Feature-off runs decline an unavailable capability; they cannot satisfy these requests.",
        "Feature-on checks cover tool selection, exact inputs, status, score/label provenance,",
        "limitations, and avoiding unsupported fault hypotheses or equipment actions.",
        "",
        "All scores are declared fixtures, including the low example resembling the live result.",
        "No XGBoost prediction is computed in this evaluation. Token counts are demo estimates.",
        "Cost is the demo provider's zero estimate; latency excludes an AWS network round trip.",
        "This adds capability, with no claim of token savings or general diagnostic improvement.",
        "",
        "The JSON sibling retains inputs, fixtures, actual API responses, checks and hashes.",
        "Existing 30-case baseline/optimized evaluation results remain separate and unchanged.",
        "",
        "## Reproduce",
        "",
        "```powershell",
        "python -m evals.prediction",
        "```",
        "",
        "No EC2, tunnel, API key, or running service is required.",
        "Temporary seeded databases are isolated and removed after each case.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=ROOT / "evals/cases/prediction-v1.json")
    parser.add_argument(
        "--output", type=Path, default=ROOT / "evals/reports/prediction-comparison-v1.json"
    )
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    report = evaluate(args.dataset, args.output.parent)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    args.output.with_suffix(".md").write_text(render_report(report), encoding="utf-8")
    print(json.dumps({k: v["summary"] for k, v in report["variants"].items()}, indent=2))
    print(f"Report: {args.output.with_suffix('.md')}")
    if report["variants"]["after_feature_on"]["summary"]["outcome_conformance_passed"] != len(
        report["dataset"]["cases"]
    ):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
