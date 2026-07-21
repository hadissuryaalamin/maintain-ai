# Architecture

The Industrial AI Maintenance Operations Copilot is an assistance system, not a
machine-control system. Its write boundary ends at creating maintenance records.
It cannot start, stop, reset, or otherwise control industrial equipment.

## Runtime components

```text
Browser
  |
  | X-Tenant-ID + X-User-ID (local demo only)
  v
Streamlit dashboard -----> FastAPI /api/v1
                              |
                              +--> bounded agent loop
                              |      +--> direct provider adapter
                              |      +--> typed tool registry
                              |      +--> approval gate
                              |
                              +--> retrieval and tenant-scoped repositories
                              +--> usage, cost, and tool-event telemetry
                              |
                              v
                  SQLite (local); PostgreSQL migration required for production

MCP client ---> MCP server ---> the same tenant-scoped read-only tool interfaces
```

The API is the application boundary for the Streamlit UI. The UI contains no
database or model-provider logic. It submits an incident, renders the structured
diagnostic, displays observable tool events and telemetry, and confirms or rejects
an exact pending proposal.

## Diagnostic request sequence

1. FastAPI derives an application context from the authenticated identity. The
   local demo represents that identity with `X-Tenant-ID` and `X-User-ID` headers.
2. The agent selects a configured model and sends system policy, bounded
   conversation context, and native tool schemas directly through the provider
   adapter.
3. A requested tool name is checked against the allowlist and its arguments are
   validated. The authoritative tenant is injected from application context, not
   accepted from model arguments.
4. Repositories apply the tenant predicate in each data query. Tool output and
   retrieved text are returned to the model as delimited, untrusted evidence. Successful typed
   results also populate an application-owned evidence ledger.
5. The loop stops at a final structured result or at configured raw-request, provider-input,
   step, tool-call, output-token, or timeout limits.
6. Before returning a diagnostic, the application replaces provider-authored factual fields
   and actions with text derived from the evidence ledger and deterministic safety policy.
   Model usage and observable tool events are persisted; hidden chain-of-thought is neither
   requested nor exposed.
7. A state-changing request becomes a pending approval. Only a separate explicit
   confirmation with an idempotency key can execute it.

## Package boundaries

| Area | Responsibility |
| --- | --- |
| `app/api` | HTTP validation, identity context, and response mapping |
| `app/agent` | Bounded native tool-calling loop and structured output |
| `app/llm` | Direct provider adapters, retries, and usage normalization |
| `app/tools` | Typed tool contracts, allowlist, permissions, and execution |
| `app/retrieval` | Small relevant chunks from manuals and incidents |
| `app/security` | Tenant context, injection controls, and approval policy |
| `app/telemetry` | Run, token, latency, cost, and tool-event measurements |
| `app/db` | Persistence and tenant-scoped repositories |
| `dashboard` | HTTP-only demo and operational views |
| `app/mcp_server.py` | Read-only MCP adapter over core tools |

## Design decisions

### Direct provider integration

The agent's critical path uses the selected provider SDK and native tool calling.
No general agent framework sits between the orchestration code and the provider.
This makes retry, usage accounting, argument validation, and loop limits explicit
and testable. Provider-specific messages stay behind a small adapter so another
provider need not change business logic.

### SQLite locally, PostgreSQL later

SQLite keeps the portfolio demo one-command and stores its file on the Compose
volume. Data access is separated from the UI and tenant filtering is performed by
repositories, which is the seam for a PostgreSQL deployment. A production move
still requires a real migration plan, concurrency testing, connection pooling,
and managed backups; changing only a URL is not sufficient validation.

### Approval is a durable workflow state

Creating a work order is not an immediate side effect of a model tool call. The
system stores an immutable proposal, displays it to the user, and accepts a
separate approve/reject command. The confirmation carries an idempotency key so a
retry cannot create duplicate work orders.

### Optimisation claims require measurements

The optimised route can use a cheaper model for simple tasks, smaller retrieval
contexts, and trimmed conversation history. The telemetry UI labels cost as
estimated and shows baseline/optimised data; savings should only be claimed when
evaluation quality and cost were measured on the same versioned cases.

## Known boundaries

- Header identity is intentionally convenient for local demonstration and is not
  authentication.
- Synthetic manuals, incidents, sensor readings, and prices are illustrative.
- A diagnosis is preliminary and must not replace lockout/tagout, OEM procedures,
  or qualified human judgement.
- The local MCP tenant is fixed at process startup. Multi-tenant production MCP
  requires an authenticated gateway that constructs a trusted context per request.
