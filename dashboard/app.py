"""Streamlit demo and operations dashboard."""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterable, Mapping
from decimal import Decimal, InvalidOperation
from typing import Any

import streamlit as st

from dashboard.api_client import APIClient, APIError

st.set_page_config(
    page_title="Maintenance Operations Copilot",
    page_icon="⚙️",
    layout="wide",
)


def _initial_state() -> None:
    defaults: dict[str, Any] = {
        "last_run": None,
        "conversation": [],
        "approval_keys": {},
        "selected_run_id": "",
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _identity_sidebar() -> APIClient:
    with st.sidebar:
        st.header("Connection")
        base_url = st.text_input(
            "API URL",
            value=os.getenv("API_BASE_URL", "http://localhost:8000"),
            disabled=not _environment_flag("DASHBOARD_ALLOW_API_URL_EDIT"),
            help=(
                "FastAPI base URL. Set API_BASE_URL before startup; editing is disabled "
                "unless DASHBOARD_ALLOW_API_URL_EDIT=true."
            ),
        )
        tenant_id = st.text_input(
            "Tenant ID",
            value=os.getenv("DEMO_TENANT_ID", "company-a"),
            help="Sent as X-Tenant-ID on every API request.",
        )
        user_id = st.text_input(
            "User ID",
            value=os.getenv("DEMO_USER_ID", "user-a-tech"),
            help="Sent as X-User-ID on every API request.",
        )
        identity_key = (base_url.strip(), tenant_id.strip(), user_id.strip())
        if st.session_state.get("active_identity") != identity_key:
            _reset_identity_scoped_state(identity_key)
        st.caption("Demo identity headers are not production authentication. See docs/security.md.")
        client = APIClient(
            base_url=base_url.strip(),
            tenant_id=tenant_id.strip(),
            user_id=user_id.strip(),
        )
        if st.button("Check API", use_container_width=True):
            if not all((client.base_url, client.tenant_id, client.user_id)):
                st.error("API URL, tenant ID, and user ID are required.")
            else:
                try:
                    health = client.health()
                    st.success(f"API ready: {health.get('status', 'ok')}")
                except APIError as exc:
                    st.error(str(exc))
        st.divider()
        st.caption("This assistant does not control physical equipment.")
    return client


def _reset_identity_scoped_state(identity_key: tuple[str, str, str]) -> None:
    """Prevent one selected demo identity's results appearing under another."""

    st.session_state.active_identity = identity_key
    st.session_state.last_run = None
    st.session_state.conversation = []
    st.session_state.approval_keys = {}
    st.session_state.selected_run_id = ""
    st.session_state.pop("analytics_summary", None)
    st.session_state.pop("analytics_runs", None)
    st.session_state.pop("trace-run-id", None)


def _environment_flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _render_diagnostic(diagnostic: Mapping[str, Any]) -> None:
    st.subheader("Preliminary diagnosis")
    summary = diagnostic.get("incident_summary") or diagnostic.get("summary")
    if summary:
        st.write(summary)

    observations = _list_of_mappings(diagnostic.get("observations"))
    if observations:
        st.markdown("**Observed and retrieved evidence**")
        st.dataframe(observations, use_container_width=True, hide_index=True)

    causes = _list_of_mappings(diagnostic.get("possible_causes"))
    if causes:
        st.markdown("**Possible causes**")
        st.dataframe(causes, use_container_width=True, hide_index=True)

    actions = _list_of_mappings(diagnostic.get("recommended_actions"))
    if actions:
        st.markdown("**Recommended actions**")
        st.dataframe(actions, use_container_width=True, hide_index=True)

    missing = diagnostic.get("missing_information")
    if isinstance(missing, list) and missing:
        st.markdown("**Missing information**")
        for item in missing:
            st.write(f"- {item}")

    notice = diagnostic.get("safety_notice")
    if notice:
        st.warning(str(notice))


def _render_usage(usage: Mapping[str, Any] | None) -> None:
    if not usage:
        return
    st.subheader("Run telemetry")
    cols = st.columns(4)
    cols[0].metric("Input tokens", _display_number(usage.get("input_tokens")))
    cols[1].metric("Output tokens", _display_number(usage.get("output_tokens")))
    cols[2].metric("Latency", _latency(usage))
    cols[3].metric("Estimated cost", _cost(usage))
    with st.expander("Usage details"):
        st.json(dict(usage))


def _render_trace(trace: Any) -> None:
    items = _list_of_mappings(trace)
    st.subheader("Observable tool trace")
    st.caption(
        "Tool names, validated inputs, outcomes, and timing are shown. "
        "Hidden reasoning is not stored or displayed."
    )
    if not items:
        st.info("No tools were called for this run.")
        return

    summary_rows: list[dict[str, Any]] = []
    for index, event in enumerate(items, start=1):
        summary_rows.append(
            {
                "#": event.get("step") or event.get("step_number") or index,
                "tool": event.get("tool_name") or event.get("name") or "unknown",
                "status": event.get("status") or ("failed" if event.get("error") else "success"),
                "latency_ms": event.get("latency_ms") or event.get("duration_ms"),
            }
        )
    st.dataframe(summary_rows, use_container_width=True, hide_index=True)
    for index, event in enumerate(items, start=1):
        name = event.get("tool_name") or event.get("name") or f"Tool call {index}"
        with st.expander(f"{index}. {name}"):
            st.json(dict(event))


def _approval_id(pending: Mapping[str, Any]) -> str | None:
    raw = pending.get("approval_id") or pending.get("id")
    return str(raw) if raw else None


def _render_pending_approval(
    client: APIClient, pending: Mapping[str, Any], *, run_id: str | None
) -> None:
    st.subheader("Human approval required")
    st.warning(
        "Review the exact proposed state change. Approval creates a record only; "
        "it never controls machinery."
    )
    proposal = pending.get("proposed_action") or pending.get("proposal") or pending
    st.json(proposal)
    approval_id = _approval_id(pending)
    if not approval_id:
        st.error("The API did not supply an approval ID; no state change can be confirmed.")
        return

    keys: dict[str, str] = st.session_state.approval_keys
    idempotency_key = keys.setdefault(approval_id, str(uuid.uuid4()))
    approve_col, reject_col = st.columns(2)
    if approve_col.button(
        "Approve exact proposal",
        type="primary",
        key=f"approve-{approval_id}",
        use_container_width=True,
    ):
        _submit_approval(
            client,
            approval_id,
            approved=True,
            idempotency_key=idempotency_key,
            run_id=run_id,
        )
    if reject_col.button(
        "Reject",
        key=f"reject-{approval_id}",
        use_container_width=True,
    ):
        _submit_approval(
            client,
            approval_id,
            approved=False,
            idempotency_key=idempotency_key,
            run_id=run_id,
        )


def _submit_approval(
    client: APIClient,
    approval_id: str,
    *,
    approved: bool,
    idempotency_key: str,
    run_id: str | None,
) -> None:
    try:
        result = client.confirm_approval(
            approval_id,
            approved=approved,
            idempotency_key=idempotency_key,
        )
    except APIError as exc:
        st.error(str(exc))
        return
    action = "approved" if approved else "rejected"
    st.success(f"Proposal {action}.")
    if result:
        st.json(result)
    if run_id:
        try:
            st.session_state.last_run = client.get_run(run_id)
        except APIError:
            pass


def _incident_tab(client: APIClient) -> None:
    st.header("Incident assistant")
    st.write(
        "Describe a maintenance incident in plain language. The response separates "
        "evidence, inference, and recommended actions."
    )
    example = (
        "Servo press on Line 3 stopped. An overload alarm appeared after the product changeover."
    )
    with st.form("incident-form"):
        message = st.text_area(
            "Incident report",
            height=130,
            placeholder=example,
        )
        optimization_mode = st.radio(
            "Run mode",
            options=("optimized", "baseline"),
            horizontal=True,
            help="Use both modes with the same case to compare measured quality and cost.",
        )
        include_history = st.checkbox(
            "Include this session's recent conversation",
            value=False,
            help="The API applies its configured history trimming policy.",
        )
        submitted = st.form_submit_button("Run preliminary diagnosis", type="primary")

    if submitted:
        if not all((client.base_url, client.tenant_id, client.user_id)):
            st.error("API URL, tenant ID, and user ID are required.")
        elif not message.strip():
            st.error("Enter an incident report.")
        else:
            history = st.session_state.conversation if include_history else None
            try:
                with st.spinner("Inspecting tenant-scoped evidence…"):
                    run = client.diagnose(
                        message.strip(),
                        optimization_mode=optimization_mode,
                        conversation_history=history,
                    )
            except APIError as exc:
                st.error(str(exc))
            else:
                st.session_state.last_run = run
                st.session_state.selected_run_id = str(run.get("run_id", ""))
                st.session_state.conversation.extend(
                    [
                        {"role": "user", "content": message.strip()},
                        {
                            "role": "assistant",
                            "content": _conversation_summary(run),
                        },
                    ]
                )

    run = st.session_state.last_run
    if isinstance(run, Mapping):
        status = str(run.get("status", "completed"))
        st.caption(f"Run `{run.get('run_id', 'unknown')}` · status: `{status}`")
        if run.get("error"):
            st.error(str(run["error"]))
        diagnostic = run.get("diagnostic")
        if isinstance(diagnostic, Mapping):
            _render_diagnostic(diagnostic)
        elif run.get("message"):
            st.write(run["message"])
        pending = run.get("pending_approval")
        if isinstance(pending, Mapping):
            _render_pending_approval(client, pending, run_id=_optional_string(run.get("run_id")))
        _render_usage(_as_mapping(run.get("usage")))


def _trace_tab(client: APIClient) -> None:
    st.header("Run and tool trace")
    default_run_id = str(st.session_state.selected_run_id or "")
    run_id = st.text_input("Run ID", value=default_run_id, key="trace-run-id")
    if st.button("Load run", key="load-run"):
        if not run_id.strip():
            st.error("Enter a run ID.")
        else:
            try:
                st.session_state.last_run = client.get_run(run_id.strip())
                st.session_state.selected_run_id = run_id.strip()
            except APIError as exc:
                st.error(str(exc))
    run = st.session_state.last_run
    if isinstance(run, Mapping):
        _render_trace(run.get("tool_trace"))
        _render_usage(_as_mapping(run.get("usage")))
    else:
        st.info("Run a diagnosis or load a run ID to inspect its trace.")


def _analytics_tab(client: APIClient) -> None:
    st.header("Cost, quality, and operations")
    st.caption("All analytics endpoints remain tenant-scoped by the same identity headers.")
    if st.button("Refresh analytics", type="primary"):
        try:
            with st.spinner("Loading tenant-scoped telemetry…"):
                st.session_state.analytics_summary = client.analytics_summary()
                st.session_state.analytics_runs = client.analytics_runs()
        except APIError as exc:
            st.error(str(exc))

    summary = st.session_state.get("analytics_summary")
    if isinstance(summary, Mapping):
        _analytics_metrics(summary)
        model_rows = _named_value_rows(
            summary.get("by_model") or summary.get("cost_by_model"), "model", "cost"
        )
        if model_rows:
            st.subheader("By model")
            st.dataframe(model_rows, use_container_width=True, hide_index=True)
        task_rows = _named_value_rows(
            summary.get("by_task_type") or summary.get("cost_by_task_type"),
            "task_type",
            "cost",
        )
        if task_rows:
            st.subheader("By task type")
            st.dataframe(task_rows, use_container_width=True, hide_index=True)
        tool_rows = _named_value_rows(
            summary.get("tools") or summary.get("tool_stats") or summary.get("tool_frequency"),
            "tool",
            "calls",
        )
        if tool_rows:
            st.subheader("Tool outcomes")
            st.dataframe(tool_rows, use_container_width=True, hide_index=True)
        experiments = _named_value_rows(
            summary.get("optimization_comparison") or summary.get("experiments"),
            "mode",
            "measurements",
        )
        if experiments:
            st.subheader("Measured baseline vs optimized")
            st.dataframe(experiments, use_container_width=True, hide_index=True)

    runs = st.session_state.get("analytics_runs")
    if isinstance(runs, Mapping):
        rows = _list_of_mappings(runs.get("runs") or runs.get("items"))
    else:
        rows = _list_of_mappings(runs)
    if rows:
        st.subheader("Recent runs")
        st.dataframe(rows, use_container_width=True, hide_index=True)
    elif summary is None:
        st.info("Refresh to load operational metrics and recent runs.")


def _analytics_metrics(summary: Mapping[str, Any]) -> None:
    total_cost = summary.get(
        "total_cost", summary.get("total_cost_usd", summary.get("estimated_total_cost_usd"))
    )
    avg_cost = summary.get(
        "average_cost_per_run",
        summary.get("average_cost_per_run_usd", summary.get("avg_cost_usd")),
    )
    success = summary.get("task_success_rate", summary.get("success_rate"))
    failure = summary.get("tool_failure_rate")
    cols = st.columns(4)
    cols[0].metric("Total estimated cost", _currency(total_cost))
    cols[1].metric("Average / run", _currency(avg_cost))
    cols[2].metric("Task success", _percentage(success))
    cols[3].metric("Tool failure", _percentage(failure))


def _list_of_mappings(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, Iterable) or isinstance(value, (str, bytes, Mapping)):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


def _named_value_rows(value: Any, name_column: str, value_column: str) -> list[dict[str, Any]]:
    """Normalize API grouping maps and already-tabular values for Streamlit."""

    if isinstance(value, Mapping):
        rows: list[dict[str, Any]] = []
        for name, item in value.items():
            if isinstance(item, Mapping):
                rows.append({name_column: name, **dict(item)})
            else:
                rows.append({name_column: name, value_column: item})
        return rows
    return _list_of_mappings(value)


def _as_mapping(value: Any) -> Mapping[str, Any] | None:
    return value if isinstance(value, Mapping) else None


def _optional_string(value: Any) -> str | None:
    return str(value) if value is not None else None


def _conversation_summary(run: Mapping[str, Any]) -> str:
    diagnostic = run.get("diagnostic")
    if isinstance(diagnostic, Mapping):
        summary = diagnostic.get("incident_summary") or diagnostic.get("summary")
        if summary:
            return str(summary)
    run_id = run.get("run_id", "unknown")
    status = run.get("status", "unknown")
    return f"Maintenance run {run_id} completed with status {status}."


def _display_number(value: Any) -> str:
    return (
        "Unavailable" if value is None else f"{value:,}" if isinstance(value, int) else str(value)
    )


def _latency(usage: Mapping[str, Any]) -> str:
    milliseconds = usage.get("latency_ms")
    if milliseconds is not None:
        return (
            f"{milliseconds:,.0f} ms"
            if isinstance(milliseconds, (int, float))
            else str(milliseconds)
        )
    seconds = usage.get("latency_seconds")
    if isinstance(seconds, (int, float)):
        return f"{seconds:.2f} s"
    return "Unavailable"


def _cost(usage: Mapping[str, Any]) -> str:
    return _currency(
        usage.get(
            "estimated_total_cost",
            usage.get("total_cost_usd", usage.get("estimated_total_cost_usd")),
        )
    )


def _currency(value: Any) -> str:
    if value is None:
        return "Unavailable"
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return str(value)
    return f"${amount:,.6f}"


def _percentage(value: Any) -> str:
    if not isinstance(value, (int, float)):
        return "Unavailable" if value is None else str(value)
    normalized = value * 100 if 0 <= value <= 1 else value
    return f"{normalized:.1f}%"


def main() -> None:
    _initial_state()
    st.title("⚙️ Industrial AI Maintenance Operations Copilot")
    st.caption(
        "Evidence-grounded preliminary diagnosis with tenant-scoped tools, approval "
        "gates, and observable cost telemetry."
    )
    client = _identity_sidebar()
    incident, trace, analytics = st.tabs(
        ["Incident & approval", "Tool trace", "Telemetry dashboard"]
    )
    with incident:
        _incident_tab(client)
    with trace:
        _trace_tab(client)
    with analytics:
        _analytics_tab(client)


if __name__ == "__main__":
    main()
