# Deployment

## One-command local stack

Prerequisites are Docker Engine with Compose v2 and free ports 8000, 8001, and
8501. Copy `.env.example` to `.env` and leave `LLM_PROVIDER=demo` for a free,
deterministic demonstration. To use a live provider, choose the configured
provider/model and supply its key through the environment; live requests may cost
money.

```bash
docker compose up --build
```

Open:

- Dashboard: <http://localhost:8501>
- API health: <http://localhost:8000/health>
- OpenAPI: <http://localhost:8000/docs>
- MCP Streamable HTTP: <http://localhost:8001/mcp>

The API and MCP service share the named `maintenance-data` volume. Stop services
without deleting data with `docker compose down`. `docker compose down --volumes`
permanently deletes the local database and should be used only when a clean demo
reset is intended.

Published demo ports bind to `127.0.0.1` intentionally. Do not expose the local
header-auth API or fixed-tenant MCP endpoint to an untrusted network.

For a guided startup on macOS/Linux or Windows PowerShell:

```bash
sh scripts/demo.sh
```

```powershell
.\scripts\demo.ps1
```

## Run processes without Docker

Use Python 3.12 or newer:

```bash
python -m venv .venv
python -m pip install -e ".[all,dev]"
uvicorn app.main:app --reload
```

In a second terminal:

```bash
API_BASE_URL=http://localhost:8000 streamlit run dashboard/app.py
```

Run `python -m app.mcp_server` in a third terminal after setting both
`MCP_TENANT_ID` and `MCP_USER_ID` if MCP is part of the demonstration.

## Configuration

Configuration is loaded from environment variables. Use `.env.example` as the
authoritative list. Important deployment values include:

- database URL and connection options;
- model provider and model routing choices;
- provider credentials;
- raw-request/provider-input, agent-step, tool-call, output-token, and timeout limits;
- versioned pricing configuration;
- log level and prompt-content logging policy;
- MCP tenant, user, transport, host, and port;
- API bind address and port (`API_HOST`, `API_PORT`);
- dashboard API URL (`API_BASE_URL`); URL editing is locked unless the local-only
  `DASHBOARD_ALLOW_API_URL_EDIT=true` escape hatch is set;
- external reverse-proxy host/origin policy if the API is exposed beyond the loopback demo;
  the application does not implement that perimeter policy itself.

Never bake `.env` or provider credentials into an image. Docker builds exclude
local secrets and database files through `.dockerignore`.

## Production topology

The Compose stack is a local demo, not a hardened production manifest. A sensible
production deployment has:

1. An HTTPS load balancer or API gateway performing OIDC/JWT authentication and
   rate limiting.
2. Independently scalable API workers with strict request timeouts.
3. A managed PostgreSQL service with encrypted storage, point-in-time recovery,
   least-privilege roles, and tested migrations.
4. A private secrets manager for provider and database credentials.
5. Central structured logs, metrics, traces, and alerting with prompt/content
   redaction.
6. Egress controls limiting model traffic to the configured provider endpoints.
7. A separately authenticated MCP gateway, or one private MCP instance per tenant.

Do not use demo identity headers as production authentication. See
[`security.md`](security.md) for the required trust-boundary change.
Application configuration also rejects `APP_ENV=production` while SQLite, automatic
synthetic seeding, or demo-header authentication remains enabled. The fixed-identity MCP
entry point refuses production mode entirely.

## Release procedure

1. Run `ruff check .`, `ruff format --check .`, `mypy app dashboard evals scripts`, and
   `pytest -m "not live" -q`.
2. Run the full deterministic scenario evaluation and compare quality/security metrics to
   the accepted baseline. The CI smoke contract is:

   ```bash
   python -m evals.runner --dataset evals/cases/v1.json --backend scenario --mode optimized --limit 3 --output evals/reports/ci-scenario.actual.json
   ```
3. Generate platform-appropriate dependency lock data for the release, then build the image
   using an immutable commit SHA and scan both the lock and image. The portfolio repository
   intentionally keeps broad compatible dependency ranges and does not claim reproducible
   production resolution by itself.
4. Apply reviewed database migrations before switching application traffic.
5. Deploy to staging using demo or restricted provider credentials; run smoke and
   tenant-isolation checks.
6. Promote the same image, observe errors/latency/cost, and keep the prior image
   available for rollback.

The GitHub workflow performs lint, formatting, static type checking, non-live tests, a
three-case scenario smoke, and an image build. Add registry publishing, signing, deployment
credentials, and environment approvals in the repository settings for a real delivery pipeline.
