# Industrial AI Maintenance Operations Copilot

Portfolio-quality, evidence-grounded maintenance decision support built with FastAPI,
Streamlit, SQLite, and a directly implemented native tool-calling loop. It can inspect
synthetic machine evidence, search small manual chunks and prior incidents, produce a
structured preliminary diagnosis, measure model usage/cost, and prepare a work order only
after explicit human approval.

> **Safety boundary:** this project cannot start, stop, reset, energize, isolate, or otherwise
> control equipment. It is not a substitute for site procedures, lockout/tagout, an OEM
> manual, a risk assessment, or a qualified technician.

All included industrial records are synthetic. The default `demo` provider is deterministic,
offline, and records its token counts as estimated. Set `LLM_PROVIDER=openai` to exercise the
direct OpenAI Responses API implementation in `app/llm/openai_provider.py`.

## What is included

- Bounded tool-calling agent: request/provider character budgets, step/call/token/time limits,
  observable retries, cancellation, duplicate-call suppression, controlled errors, and strict
  structured output.
- Six typed tools: manual search, current machine status, sensor history, incident search,
  downtime-cost calculation, and approval-gated draft work-order creation.
- Security controls: allowlisted tools, authoritative out-of-band tenant context, query-level
  tenant filters, cross-tenant audit events, untrusted-content delimiters, injection fixtures,
  approval persistence, and work-order idempotency.
- Usage and cost telemetry per model request: exact/estimated status, tokens, cache tokens,
  latency, model/provider, agent step, tool names, status, and versioned price lookup.
- Privacy-aware telemetry defaults: prompts, free-text tool arguments, and result bodies are
  redacted; exact approval proposals live in their tenant-scoped workflow record.
- Three implemented optimization levers: configured small-model routing, bounded retrieval of
  relevant chunks, and conversation-history trimming. Baseline and optimized runs are measured
  separately; no savings claim is made without an evaluation result.
- A Streamlit demo and analytics view, a read-only MCP server reusing the same tools and tenant
  checks, Docker Compose, GitHub Actions CI, 30 versioned evaluation cases, and operating docs.

## Architecture

```text
Streamlit UI --HTTP--> FastAPI --> bounded agent loop --> provider adapter
                         |              |                    |-- demo (offline)
                         |              |                    `-- OpenAI Responses API
                         |              |-- typed tool registry + approval gate
                         |              `-- usage/cost telemetry
                         `--> tenant-scoped repositories --> SQLite

MCP client --> read-only MCP adapter --> same tool registry and tenant boundary
```

See [architecture](docs/architecture.md), [security model](docs/security.md), the dated
[security test report](docs/security-test-report.md), and the
[native-tool-calling versus MCP note](docs/mcp.md) for design detail.

## Quick start

Requirements: Python 3.12+ and Git. No API key is needed for the offline demo.

```bash
python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[all,dev]"
cp .env.example .env  # Windows PowerShell: Copy-Item .env.example .env
python -m scripts.seed_database
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/docs`. In a second shell, start the UI:

```bash
streamlit run dashboard/app.py
```

The local demo identity is `company-a` / `user-a-tech`. Identity headers are a development
convenience, **not production authentication**.

### Submit the example incident

```bash
curl -X POST http://127.0.0.1:8000/api/v1/incidents/diagnose \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: company-a" \
  -H "X-User-ID: user-a-tech" \
  -d '{"message":"Servo press A1 on Line 3 stopped with E217 after changeover."}'
```

The response includes `diagnostic`, an observable `tool_trace`, and a `usage` summary. It never
exposes hidden reasoning.

### Exercise approval and idempotency

Ask: `Create a work order for A1 to investigate the overload.` The diagnosis endpoint returns
`awaiting_approval` and the exact proposal; nothing has been created. Confirm separately:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/approvals/APPROVAL_ID/confirm \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: company-a" \
  -H "X-User-ID: user-a-tech" \
  -d '{"approved":true,"idempotency_key":"demo-a1-overload-001"}'
```

Repeating the same confirmed operation is a replay, not a second work order. Reusing a key for
different arguments is rejected.

## Technician chat app

`web/` is a chat-first React app for technicians on the shop floor. It works on phones,
tablets and desktops, with large touch targets for gloved use. It calls the same API as the
Streamlit dashboard and adds three read-only endpoints for machine context:
`GET /api/v1/machines`, `GET /api/v1/machines/{id}` and `GET /api/v1/machines/{id}/sensors`.

Requirements: Node 22 and pnpm 9.

Development (two terminals):

```bash
uvicorn app.main:app --reload          # API on http://127.0.0.1:8000
pnpm -C web install && pnpm -C web dev # app on http://localhost:5173/app/
```

Production: `pnpm -C web build` writes `web/dist`, which FastAPI serves at
`http://localhost:8000/app/` (path configurable with `WEB_DIST_PATH`). The Docker image builds
it automatically.

The app uses the demo identity headers (pick a demo user in the sidebar), keeps conversation
history only in the browser, and is read-only decision support: it can propose a draft work
order for human approval but cannot control equipment. Optional build-time settings:
`VITE_DEMO_TENANT_ID`, `VITE_DEMO_USER_ID`, `VITE_DASHBOARD_URL` (each answer links to the dashboard with its run id; paste the id into
the "Run and tool trace" tab).

## Use a live LLM provider

The agent loop speaks an app-owned, provider-neutral conversation format
(`UserMessage`, `AssistantMessage`, `ToolCall`, `ToolResult`, `ToolSpec` in
`app/llm/base.py`). Each vendor adapter translates that format to its own API, and every
provider must return the same `DiagnosticResult` JSON, which then goes through the same
validation, grounding and safety policy. Switching vendor is configuration only: edit `.env`
and restart the API.

| `LLM_PROVIDER` | Key | Suggested `DEFAULT_MODEL` / `SMALL_MODEL` | Adapter |
|---|---|---|---|
| `demo` | none | (ignored; offline rules) | `app/llm/demo_provider.py` |
| `openai` | `OPENAI_API_KEY` | `gpt-5.6-terra` / `gpt-5.6-luna` | Responses API, strict JSON-schema output |
| `anthropic` | `ANTHROPIC_API_KEY` | `claude-sonnet-5-5` / `claude-haiku-5-5` | Messages API; the final answer arrives through a `submit_diagnostic` tool (tool choice `auto` plus a protocol instruction) |

API usage is billed per token from the vendor's API account. A ChatGPT or Claude app
subscription does not include API credit. When credit runs out, runs fail with
"insufficient credit" (Claude) or a provider rejection (OpenAI) rather than a fabricated answer.
Live calls are never part of the default test run. The OpenAI adapter follows the official
Responses API patterns for
[function calling](https://developers.openai.com/api/docs/guides/function-calling) and
[structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs).
Configured prices in `config/model_pricing.yaml` are dated snapshots linked to official pricing
pages; reported costs are estimates, not invoices. Providers that only speak the OpenAI Chat
Completions API (for example DeepSeek) need one more adapter on the same neutral format.

## Verification

```bash
ruff check .
ruff format --check .
mypy app dashboard evals scripts
pytest -m "not live" -q
python -m evals.runner --help
```

Run the reproducible offline scenario evaluation (30 cases in both modes):

```bash
python -m evals.runner --dataset evals/cases/v1.json --mode both --backend scenario
```

This exercises the actual API/agent/telemetry/security workflow with declared synthetic tool
outcomes injected at a test-only boundary. Use `--backend demo` for seeded-data integration or
`--backend fixture` for a contract-only harness self-check. Baseline and optimized modes must
both satisfy the same quality/security checks before a cost reduction can be described as an
improvement. See the checked-in [scenario report](evals/reports/sample-scenario-comparison-v1.md),
its [machine-readable results](evals/reports/sample-scenario-comparison-v1.json), and the
[evaluation instructions](evals/README.md).

On the current synthetic scenario set, optimized mode raises evaluated task completion from
53.3% to 60.0% and correct tool selection from 86.7% to 93.3%. Grounded-answer scoring is
100% on its applicable subset (18/18 baseline and 20/20 optimized; 60.0% and 66.7% case
coverage), and both modes pass all three tenant-isolation and all three injection cases.
For the 28/30 cases with paired usage, estimated tokens fall 43.0%. The separate 59.4% shadow
price delta evaluates routing decisions only; it is not a billed-cost, hosted-model-quality, or
production-savings claim. Failed checks and coverage denominators are listed in the report.

## Docker and MCP

```bash
docker compose up --build
```

This starts the API, dashboard, and read-only MCP server with a persistent local SQLite volume.
To run the MCP server directly in PowerShell, set `$env:MCP_TENANT_ID='company-a'` and
`$env:MCP_USER_ID='user-a-tech'`, then run `python -m app.mcp_server` (POSIX shells use `export`).
It exposes selected read-only tools and fixes its trusted demo tenant/user context from process
environment variables at startup. See
[deployment](docs/deployment.md) and [MCP usage](docs/mcp.md).

## Repository map

```text
app/          API, agent, provider, tools, retrieval, security, telemetry, database
dashboard/    Streamlit incident, approval, trace, and analytics UI
data/         versioned synthetic manuals and seed records
evals/        30 cases, deterministic rubric, runner, and reports
config/       dated model-pricing snapshots
tests/        unit, API, security, approval, and evaluation tests
docs/         architecture, security, MCP, deployment, operations, and demo script
```

## Important limitations

- The local header identity adapter must be replaced by verified OIDC/JWT identity in production.
- SQLite is for local/demo usage; production needs migrations, PostgreSQL validation, backups,
  concurrency tests, and appropriate secret management.
- Lexical retrieval is intentionally transparent and small; it is not a semantic-search claim.
- Synthetic thresholds and manuals are not valid instructions for real equipment.
- A successful evaluation demonstrates behavior on this fixture set, not universal safety or
  diagnostic accuracy.

Operational guidance lives in [operations](docs/operations.md). Security reports should follow
[SECURITY.md](SECURITY.md). Contributions follow [CONTRIBUTING.md](CONTRIBUTING.md).

## Optional failure-evidence prediction tool

The read-only `predict_failure_risk` tool can call the separate `maintain-predict`
API through the laptop's Session Manager tunnel. It is disabled by default, so
ordinary offline runs retain the original six tools and make no prediction requests.
To enable it for a locally running maintain-ai process, set:

```powershell
$env:FAILURE_PREDICTION_ENABLED = "true"
$env:FAILURE_PREDICTION_BASE_URL = "http://127.0.0.1:8003"
$env:FAILURE_PREDICTION_TIMEOUT_SECONDS = "5"
```

Start EC2 and the Session Manager tunnel manually, then restart maintain-ai to load
these settings. The URL is operator configuration, never a model-controlled argument.
Inside Docker, `127.0.0.1` refers to that container; the laptop tunnel address is not
usable unchanged from a Compose service.

The tool requires six explicit inputs: `type` (L/M/H), `air_temp_k`,
`process_temp_k`, `rpm`, `torque_nm`, and `tool_wear_min`. Do not substitute vibration
or other sensor metrics, invent product type, or infer missing measurements. It
validates the response policy, threshold, and label/score consistency and returns an
application-authored source reference for grounded observations. Timeout or upstream
errors produce tool failures, never a fabricated prediction. Existing registry retry
limits apply to transient failures; HTTP timeouts are per network operation.

The score comes from synthetic AI4I data and is not a calibrated physical failure
probability, a diagnosis, or a safety clearance. The model-facing tool name retains
`risk` for the planned interface; that name does not change these limitations.

When enabled, the deterministic DemoProvider selects the tool for explicit standalone
requests beginning with `Prediksi kegagalan`, `Predict failure`, `Failure prediction`,
or `predict_failure_risk`, followed by a single JSON object with the six input fields.
This demo selection uses parsing rules, not a paid LLM. Missing, invalid, duplicate,
or extra fields trigger clarification without a prediction request. The ordinary
OpenAI adapter receives the tool schema automatically when the feature is enabled.
MCP exposure is unchanged. Existing 30-case evaluation metrics above predate this
integration and are not prediction-tool selection quality measurements.

For a locally running API on port 8000 with demo authentication, send a request to
`POST /api/v1/incidents/diagnose` using headers `X-Tenant-ID: company-a` and
`X-User-ID: user-a-tech`. Example message:

```text
Prediksi kegagalan menggunakan input berikut:
{"type":"L","air_temp_k":300,"process_temp_k":310,"rpm":1500,"torque_nm":40,"tool_wear_min":100}
```

A successful run includes `predict_failure_risk` in `tool_trace` and a grounded
observation with the returned score and source reference. Prediction-only requests
do not generate fault hypotheses, work orders, or invasive inspection instructions.
The demonstration input is not automatically associated with an actual machine.
Run the laptop API with `python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`
after setting the prediction environment variables above and `LLM_PROVIDER=demo`.
The Session Manager tunnel must remain running in a separate terminal.

## Prediction integration evaluation

The five-scenario feature-off/on comparison is recorded in
[the report](evals/reports/prediction-comparison-v1.md), with full responses and
checks in its JSON sibling. Reproduce it offline with `python -m evals.prediction`.
It uses the same current agent code in both configurations and a mocked prediction
endpoint, independently of the existing 30-case baseline/optimized experiment.

The user also completed a live laptop-agent-to-EC2 call: run
`78e72096-8e73-449e-9146-81e0c7d2e3e8`, tool succeeded in 222 ms, and score
`0.0005919649847783148` at threshold 0.5. The
[separate evidence record](evals/reports/prediction-live-check-v1.json) identifies
this as user-supplied live output, not part of the mocked evaluation. EC2 was
subsequently stopped. Chatbot UI hosting, public serving, and paid LLM evaluation
are separate future work rather than prerequisites for this integration.

## Roadmap

The main planned work is in [docs/roadmap.md](docs/roadmap.md): letting model-written answers
through grounding when every claim cites a real source, and moving the Insights and run-trace
views into the React app so Streamlit can be removed.

## License

MIT — see [LICENSE](LICENSE).
