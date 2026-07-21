# MCP integration

The MCP server exposes selected read-only maintenance capabilities while reusing
the application's typed tool registry and tenant-scoped data access. It is an
adapter, not a second implementation of maintenance queries.

## Run locally

Install the project, initialise/seed the local database using the normal
application setup, and set an authoritative tenant for this server process:

```bash
MCP_TENANT_ID=company-a MCP_USER_ID=user-a-tech python -m app.mcp_server
```

Windows PowerShell:

```powershell
$env:MCP_TENANT_ID = "company-a"
$env:MCP_USER_ID = "user-a-tech"
python -m app.mcp_server
```

The default transport is `stdio`, which is suitable for a local desktop MCP
client. Keep stdout reserved for protocol traffic; application logs belong on
stderr.

Docker Compose runs the same server over Streamable HTTP:

```bash
docker compose up --build mcp
```

The endpoint is `http://localhost:8001/mcp` unless `MCP_PORT` changes the published
host port. The container listens on port 8001.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | Application default | Shared maintenance database |
| `MCP_TENANT_ID` | none | Required authoritative tenant scope |
| `MCP_USER_ID` | none | Required tenant-member identity for MCP access |
| `MCP_TRANSPORT` | `stdio` | `stdio`, `streamable-http`, or `sse` |
| `MCP_HOST` | `127.0.0.1` | HTTP bind address |
| `MCP_PORT` | `8001` | HTTP listen port |

The process refuses to start without both `MCP_TENANT_ID` and `MCP_USER_ID`. They are
intentionally absent from model-visible tool parameters, so an MCP caller cannot switch
identity or tenant by editing tool arguments.

## Exposed capability

`get_machine_status(machine_id)` returns the selected machine's current synthetic
status through the core tool interface. `search_manual(query, machine_model)`
returns a bounded set of relevant tenant-scoped manual chunks. The core repositories
apply the configured tenant scope. A machine or document belonging to a different
tenant is not returned.

Additional read-only tools may be exposed only by wrapping registry entries that
retain the same validation, tenant injection, controlled errors, and audit
behavior. State-changing tools are deliberately excluded.

## Native tool calling versus MCP

| Concern | Native provider tools | MCP adapter |
| --- | --- | --- |
| Tool schema sent to model | Provider-specific JSON schema | MCP tool metadata |
| Orchestration | Bounded loop in this application | MCP client/host |
| Tenant source | Authenticated API context | Fixed trusted process config locally |
| Tool implementation | Core registry | Same core registry |
| Usage telemetry | Provider request plus persisted tool events | Adapter returns tool status/latency; model usage belongs to host |
| Write approval | Durable HTTP approval workflow | Not exposed |

Native tool calling remains the main application path because this repository is
intended to show direct provider integration, step limits, usage capture, and cost
calculation. MCP demonstrates interoperable tool exposure without replacing or
hiding that code.

## Client configuration example

For a client that launches a local stdio server, adapt this shape to the client's
configuration format:

```json
{
  "mcpServers": {
    "maintenance-company-a": {
      "command": "python",
      "args": ["-m", "app.mcp_server"],
      "env": {
        "MCP_TENANT_ID": "company-a",
        "MCP_USER_ID": "user-a-tech",
        "DATABASE_URL": "sqlite:///./maintenance_copilot.db"
      }
    }
  }
}
```

Use an absolute project interpreter or installed console command when the client
does not start in the repository directory. Never place provider secrets directly
in a configuration file that will be committed.
