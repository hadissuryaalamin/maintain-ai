# Portfolio demo script (3–5 minutes)

Prepare with `sh scripts/demo.sh` or `.\scripts\demo.ps1`. Keep
`LLM_PROVIDER=demo` for a deterministic, no-cost recording, or clearly label a live
provider run and its estimated cost. The seeded data is synthetic.

## 0:00–0:35 — Frame the system

Open the Streamlit dashboard at <http://localhost:8501>.

Say: "This is an industrial maintenance assistant. It can inspect tenant-scoped
synthetic evidence, produce a preliminary diagnosis, and draft a work order. It
cannot control machinery, and a human must approve every state change."

Point out the API URL and the `company-a` / `user-a-tech` demo identity in the
sidebar. Mention that headers make the boundary visible locally; verified identity
claims would replace them in production.

## 0:35–1:35 — Run an evidence-grounded diagnosis

Submit:

> Servo press on Line 3 stopped. An overload alarm appeared after the product
> changeover. Check the current status and recent evidence, then recommend safe next
> steps.

Use **optimized** mode. While the run completes, explain that the code uses a
bounded native provider tool-calling loop rather than a general agent framework.

In the result, point to:

- the incident summary;
- observations with source type/reference;
- causes labeled with confidence, not certainty;
- actions ordered by safety and likelihood;
- missing information and the safety notice.

Say: "The assistant may only claim evidence returned by successful tools. Retrieved
manual and incident content is treated as untrusted data, not instructions."

## 1:35–2:20 — Show observable execution and cost

Open **Tool trace**. Show the tool names, statuses, validated inputs, and timing.
Explain that this is an observable decision/tool trace, not hidden chain-of-thought.

Show input/output tokens, latency, model/provider, and estimated cost. Mention that
missing provider usage is explicitly unavailable or estimated, never silently
recorded as zero.

## 2:20–3:00 — Demonstrate human approval

Return to **Incident & approval** and submit a short follow-up:

> Draft a high-priority work order for A1 to inspect the overload after changeover.

Expand the pending proposal. Read the exact machine, title, description, and
priority before selecting **Approve exact proposal**.

Say: "The model did not create this work order. It created a durable proposal. This
separate request supplies explicit approval and an idempotency key, so a network
retry cannot duplicate the work order. No endpoint controls physical equipment."

If recording a security-focused version, reject first and submit another incident
to show that rejection is also auditable.

## 3:00–3:40 — Show cost/quality operations

Open **Telemetry dashboard** and select **Refresh analytics**. Show total and
average cost, task success, tool failure, per-model/task data, and recent runs. The demo has
created an optimized run; for the versioned baseline-versus-optimized result, open
[`../evals/reports/sample-scenario-comparison-v1.md`](../evals/reports/sample-scenario-comparison-v1.md).

Say: "Routing, smaller retrieval contexts, and history trimming are optimisation
techniques, but I only claim savings when the versioned evaluation measures both
cost and task quality."

## 3:40–4:20 — Prove isolation and interoperability

Copy the Company A run ID. Change the sidebar identity to `company-b` / `user-b-tech`, paste
the copied Company A ID into **Tool trace**, and select **Load run**. The request should fail
closed without revealing Company A's run. Switch back to `company-a` / `user-a-tech` for the
rest of the demo.

Briefly open [`mcp.md`](mcp.md) or an MCP inspector and list the MCP tools. Explain
that MCP exposes `get_machine_status` through the same core registry with a
process-authoritative tenant and intentionally excludes write tools.

## 4:20–4:40 — Close honestly

Say: "The portfolio demonstrates direct model integration, typed and tenant-scoped
tools, evidence grounding, approval/idempotency, usage/cost telemetry, deterministic
security evaluation, MCP interoperability, and container deployment. The data is
synthetic, identity headers are local-demo only, and a qualified technician remains
responsible for safety and diagnosis."

Optional final frame: API docs at <http://localhost:8000/docs> and the architecture
diagram in [`architecture.md`](architecture.md).
