"""Pricing, usage telemetry, model routing, and context trimming tests."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.agent.routing import ModelRouter, trim_history
from app.config import Settings
from app.db.models import AgentRun
from app.llm.base import ProviderResponse, ProviderUsage
from app.schemas.api import ConversationMessage
from app.schemas.common import OptimizationMode
from app.security.context import AuthContext
from app.telemetry.pricing import PricingCatalog, PricingConfig, PricingEntry
from app.telemetry.service import TelemetryService


def _catalog() -> PricingCatalog:
    return PricingCatalog(
        PricingConfig(
            schema_version="test-v1",
            entries=[
                PricingEntry(
                    provider="fake",
                    model="fake-model",
                    effective_from=date(2026, 1, 1),
                    verified_at=date(2026, 1, 2),
                    source_url="local://test-pricing",
                    input_per_million_tokens=Decimal("2.00"),
                    cached_input_per_million_tokens=Decimal("0.50"),
                    cache_write_multiplier=Decimal("1.25"),
                    output_per_million_tokens=Decimal("3.00"),
                ),
                PricingEntry(
                    provider="fake",
                    model="fake-model",
                    effective_from=date(2026, 6, 1),
                    verified_at=date(2026, 6, 2),
                    source_url="local://test-pricing-new",
                    input_per_million_tokens=Decimal("2.00"),
                    cached_input_per_million_tokens=Decimal("0.50"),
                    cache_write_multiplier=Decimal("1.25"),
                    output_per_million_tokens=Decimal("3.00"),
                ),
            ],
        )
    )


def _run(
    session: Session,
    context: AuthContext,
    *,
    status: str = "completed",
    task_type: str = "diagnostic",
    mode: str = "optimized",
) -> AgentRun:
    run = AgentRun(
        id=str(uuid4()),
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        task_type=task_type,
        optimization_mode=mode,
        model="fake-model",
        provider="fake",
        status=status,
    )
    session.add(run)
    session.flush()
    return run


def _provider_response(request_id: str, usage: ProviderUsage) -> ProviderResponse:
    return ProviderResponse(
        request_id=request_id,
        output_text="{}",
        tool_calls=[],
        items=[],
        usage=usage,
    )


def test_pricing_uses_effective_version_and_cached_token_rates() -> None:
    usage = ProviderUsage(
        input_tokens=1000,
        output_tokens=500,
        cached_input_tokens=200,
        cache_write_tokens=100,
    )

    estimate = _catalog().calculate(
        provider="fake",
        model="fake-model",
        usage=usage,
        at=datetime(2026, 7, 21, tzinfo=UTC),
    )

    # Input: 700*2 + 200*.5 + 100*2*1.25 = 1750 millionths of a dollar.
    assert estimate.input_cost == Decimal("0.00175000")
    assert estimate.output_cost == Decimal("0.00150000")
    assert estimate.total_cost == Decimal("0.00325000")
    assert estimate.pricing_version == "test-v1:fake-model:2026-06-01"


def test_pricing_is_unavailable_without_exact_usage_or_matching_snapshot() -> None:
    catalog = _catalog()

    missing_usage = catalog.calculate(
        provider="fake",
        model="fake-model",
        usage=ProviderUsage(input_tokens=None, output_tokens=10, estimated=True),
        at=datetime(2026, 7, 21, tzinfo=UTC),
    )
    unknown_model = catalog.calculate(
        provider="fake",
        model="unknown",
        usage=ProviderUsage(input_tokens=10, output_tokens=10),
        at=datetime(2026, 7, 21, tzinfo=UTC),
    )

    assert missing_usage.total_cost is None
    assert missing_usage.pricing_version is None
    assert unknown_model.total_cost is None
    assert unknown_model.pricing_version is None


def test_telemetry_records_usage_cost_latency_tools_and_tenant_scoped_analytics(
    session: Session,
    context_a: AuthContext,
    context_b: AuthContext,
    settings: Settings,
) -> None:
    run_a = _run(session, context_a, task_type="diagnostic", mode="optimized")
    telemetry_a = TelemetryService(session, context_a, settings, pricing=_catalog())
    telemetry_a.record_model_response(
        run_id=run_a.id,
        response=_provider_response(
            "request-a",
            ProviderUsage(
                input_tokens=1000,
                output_tokens=500,
                cached_input_tokens=200,
                cache_write_tokens=100,
                estimated=True,
            ),
        ),
        provider="fake",
        model="fake-model",
        step=1,
        latency_ms=125,
        tool_names=["get_machine_status"],
    )
    telemetry_a.record_tool_call(
        run_id=run_a.id,
        step=1,
        call_id="tool-success",
        tool_name="get_machine_status",
        arguments={"machine_id": "A1"},
        result_preview='{"ok":true}',
        status="succeeded",
        error_category=None,
        latency_ms=4,
    )
    telemetry_a.record_tool_call(
        run_id=run_a.id,
        step=1,
        call_id="tool-failure",
        tool_name="get_sensor_history",
        arguments={"machine_id": "A1"},
        result_preview='{"ok":false}',
        status="failed",
        error_category="not_found",
        latency_ms=3,
    )
    telemetry_a.record_tool_call(
        run_id=run_a.id,
        step=1,
        call_id="tool-approval",
        tool_name="create_work_order",
        arguments={"machine_id": "A1"},
        result_preview='{"ok":false,"error":{"category":"approval_required"}}',
        status="approval_required",
        error_category="approval_required",
        latency_ms=1,
    )

    run_b = _run(session, context_b, task_type="secret-b-task", mode="baseline")
    telemetry_b = TelemetryService(session, context_b, settings, pricing=_catalog())
    telemetry_b.record_model_response(
        run_id=run_b.id,
        response=_provider_response(
            "request-b", ProviderUsage(input_tokens=9999, output_tokens=9999)
        ),
        provider="fake",
        model="fake-model",
        step=1,
        latency_ms=999,
        tool_names=[],
    )

    usage = telemetry_a.usage_summary(run_a.id, model="fake-model", provider="fake")
    analytics = telemetry_a.analytics()

    assert usage.model_requests == 1
    assert usage.input_tokens == 1000
    assert usage.output_tokens == 500
    assert usage.cached_input_tokens == 200
    assert usage.estimated_total_cost == Decimal("0.00325000")
    assert usage.latency_ms == 125
    assert usage.usage_is_estimated is True
    assert analytics.run_count == 1
    assert analytics.successful_runs == 1
    assert analytics.total_input_tokens == 1000
    assert analytics.total_output_tokens == 500
    assert analytics.total_cost == Decimal("0.00325000")
    assert analytics.average_latency_ms == 125
    assert analytics.tool_call_count == 3
    assert analytics.tool_failure_rate == pytest.approx(1 / 3)
    assert analytics.tool_frequency == {
        "get_machine_status": 1,
        "get_sensor_history": 1,
        "create_work_order": 1,
    }
    assert "secret-b-task" not in analytics.cost_by_task_type
    assert analytics.optimization_comparison["optimized"]["runs"] == 1


def test_usage_summary_marks_mixed_or_unavailable_usage_as_unknown(
    session: Session, context_a: AuthContext, settings: Settings
) -> None:
    run = _run(session, context_a, status="failed")
    telemetry = TelemetryService(session, context_a, settings, pricing=_catalog())
    telemetry.record_model_response(
        run_id=run.id,
        response=_provider_response("success", ProviderUsage(input_tokens=20, output_tokens=5)),
        provider="fake",
        model="fake-model",
        step=1,
        latency_ms=10,
        tool_names=[],
    )
    telemetry.record_model_error(
        run_id=run.id,
        request_id="failed-attempt",
        provider="fake",
        model="fake-model",
        step=1,
        latency_ms=7,
        error_category="timeout",
    )

    usage = telemetry.usage_summary(run.id, model="fake-model", provider="fake")
    analytics = telemetry.analytics()

    assert usage.model_requests == 2
    assert usage.input_tokens is None
    assert usage.output_tokens is None
    assert usage.cached_input_tokens is None
    assert usage.estimated_total_cost is None
    assert usage.latency_ms == 17
    assert analytics.total_input_tokens is None
    assert analytics.total_output_tokens is None
    assert analytics.unavailable_usage_requests == 1
    assert analytics.optimization_comparison["optimized"]["average_tokens"] is None


def test_model_router_selects_configured_models_by_mode_and_complexity(
    settings: Settings,
) -> None:
    openai_settings = settings.model_copy(
        update={
            "llm_provider": "openai",
            "small_model": "cheap-model",
            "default_model": "capable-model",
        }
    )
    router = ModelRouter(openai_settings)

    simple = router.select("What is the maintenance interval?", OptimizationMode.OPTIMIZED)
    complex_request = router.select(
        "A1 stopped with an overload alarm; diagnose the root cause.",
        OptimizationMode.OPTIMIZED,
    )
    baseline = router.select("What is the interval?", OptimizationMode.BASELINE)

    assert simple.model == "cheap-model"
    assert "lower-cost" in simple.reason
    assert complex_request.model == "capable-model"
    assert baseline.model == "capable-model"
    assert "baseline" in baseline.reason

    demo = ModelRouter(settings).select("simple request", OptimizationMode.OPTIMIZED)
    assert demo.model == settings.demo_model
    assert "offline demo" in demo.reason


def test_history_trimming_respects_message_and_character_limits(settings: Settings) -> None:
    history = [
        ConversationMessage(
            role="user" if index % 2 == 0 else "assistant", content=str(index) * 450
        )
        for index in range(6)
    ]
    optimized_settings = settings.model_copy(
        update={"history_message_limit": 3, "history_character_limit": 1000}
    )

    trimmed = trim_history(
        history,
        optimized_settings,
        OptimizationMode.OPTIMIZED,
        current_message="routine follow-up",
    )
    baseline = trim_history(history, optimized_settings, OptimizationMode.BASELINE)

    assert [message.content[0] for message in trimmed.messages] == ["4", "5"]
    assert trimmed.omitted_messages == 4
    assert trimmed.omitted_characters == 1800
    assert baseline.messages == history
    assert baseline.omitted_messages == 0
    assert baseline.omitted_characters == 0


def test_history_trimming_preserves_relevant_older_and_recent_context_in_order(
    settings: Settings,
) -> None:
    history = [
        ConversationMessage(
            role="user",
            content=(
                "[conversation:turn-117] Machine A1 reported overload alarm E217 after changeover."
            ),
        ),
        ConversationMessage(role="assistant", content="irrelevant-padding-1 " * 20),
        ConversationMessage(role="user", content="irrelevant-padding-2 " * 20),
        ConversationMessage(role="assistant", content="irrelevant-padding-3 " * 20),
        ConversationMessage(
            role="user",
            content="[conversation:item-298] Later A1 vibration became intermittent.",
        ),
        ConversationMessage(role="assistant", content="irrelevant-padding-4 " * 20),
        ConversationMessage(role="user", content="Please continue from the latest check."),
    ]
    optimized_settings = settings.model_copy(
        update={"history_message_limit": 3, "history_character_limit": 1000}
    )

    trimmed = trim_history(
        history,
        optimized_settings,
        OptimizationMode.OPTIMIZED,
        current_message="Diagnose the A1 overload alarm and intermittent vibration.",
    )

    assert trimmed.messages == [history[0], history[4], history[6]]
    assert sum(len(message.content) for message in trimmed.messages) <= 1000
    assert trimmed.omitted_messages == 4
    assert trimmed.omitted_characters == sum(len(item.content) for item in history[1:4]) + len(
        history[5].content
    )


def test_history_trimming_baseline_remains_untrimmed_with_current_message(
    settings: Settings,
) -> None:
    history = [
        ConversationMessage(role="user", content="old context"),
        ConversationMessage(role="assistant", content="new context"),
    ]
    constrained = settings.model_copy(
        update={"history_message_limit": 1, "history_character_limit": 1000}
    )

    trimmed = trim_history(
        history,
        constrained,
        OptimizationMode.BASELINE,
        current_message="A1 alarm",
    )

    assert trimmed.messages == history
    assert trimmed.omitted_messages == 0
    assert trimmed.omitted_characters == 0
